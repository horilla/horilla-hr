"""
Running payroll for a group of people, as a reviewable operation.

Generation used to be one button: a modal with a batch name, a list of
employees and two dates, which wrote payslips straight to the database. There
was no way to see who was included, nothing said why someone was left out, and
nothing was checked first — so the first sight of a problem was a wrong
payslip.

This splits it into the three steps a payroll run actually has:

  1. **Scope** — the period and who is in it.
  2. **Review** — what the engine will read for each person, and what is wrong
     with it. Some problems stop the run; others are worth seeing but not
     blocking.
  3. **Generate** — in slices, so progress is real and an interrupted run can
     be resumed rather than restarted.

The blocking check that matters most is an unresolved attendance conflict. In
``compute_salary_on_period`` a single unresolved conflict day makes the
employee's **entire month** unpaid::

    if month_summary.get("unresolved_conflicts", 0):
        unpaid_days = total_days

and that only fires on the batch path, because it is the only one that passes
a summary. So the same employee gets a different payslip depending on which
button was pressed, and the difference is their whole salary. Blocking here
does not change that rule — it makes it impossible to hit by accident.
"""

import logging

from django.db import transaction
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# How many employees one request generates. Small enough that a slice returns
# quickly on a slow database, large enough that a 500-person run is not 500
# round trips.
SLICE_SIZE = 10

BLOCKING = "blocking"
WARNING = "warning"

# Below this many paid days, a payslip is worth looking at before it is
# generated rather than after. It is not a blocker -- somebody who joined
# mid-month or was off sick legitimately has few paid days -- but on a list of
# two hundred it is the handful you would want to check.
LOW_PAID_DAYS = 10


def eligible_employees(employees, start_date, end_date):
    """
    Split the chosen employees into those a payslip can be made for and those
    it cannot, with the reason.

    Returns ``(ok, excluded)`` where excluded is a list of
    ``(employee, reason)``. Nothing here reads attendance — this is only about
    whether a payslip is possible at all.
    """
    from payroll.models.models import Contract, Payslip

    ok, excluded = [], []
    for employee in employees:
        contract = employee.contract_set.filter(contract_status="active").first()
        if contract is None:
            excluded.append((employee, _("No active contract")))
            continue
        if contract.contract_start_date and contract.contract_start_date > end_date:
            excluded.append((employee, _("Contract starts after this period")))
            continue
        # The model refuses a second payslip for the same employee and period,
        # so catching it here is the difference between a listed exclusion and
        # an exception halfway through a run.
        if Payslip.objects.filter(
            employee_id=employee, start_date=start_date, end_date=end_date
        ).exists():
            excluded.append((employee, _("Already has a payslip for this period")))
            continue
        ok.append(employee)
    return ok, excluded


def _exceptions_for(row, employee, contract):
    """
    What is wrong with one employee's inputs, most serious first.

    Each is ``(severity, message)``. Blocking ones stop the run; warnings are
    shown and proceeded past, because "this person has no overtime approved
    yet" is worth knowing and is not a reason to hold up everybody's pay.
    """
    problems = []

    unresolved = row.get("unresolved_conflicts", 0)
    if unresolved:
        problems.append(
            (
                BLOCKING,
                _(
                    "%(count)s day(s) with both attendance and leave, unresolved. "
                    "Payroll treats an unresolved conflict as the whole month "
                    "unpaid, so this must be resolved first."
                )
                % {"count": unresolved},
            )
        )

    if not contract.pay_rate:
        from payroll.methods.basic_pay_source import basic_pay_component

        structure = contract.salary_structure_id
        flagged = basic_pay_component(structure.allowances.all()) if structure else None
        if flagged is None:
            # Named for the wage type the contract is on: telling a monthly
            # employee there is no "hourly rate" sends them looking for a
            # field that does not apply to them.
            wage_name = {
                "monthly": _("monthly wage"),
                "daily": _("daily wage"),
                "hourly": _("hourly wage"),
            }.get(contract.wage_type, _("wage"))
            problems.append(
                (
                    BLOCKING,
                    _(
                        "No %(wage)s on the contract, and no earning marked as "
                        "basic pay. There is nothing to work pay out from."
                    )
                    % {"wage": wage_name},
                )
            )

    if contract.salary_structure_id is None:
        problems.append(
            (
                WARNING,
                _("No salary structure. Only components targeted directly apply."),
            )
        )

    if row.get("absent", 0) and not row.get("present", 0):
        problems.append(
            (
                WARNING,
                _("No attendance recorded in this period."),
            )
        )

    return problems


def review(employees, start_date, end_date):
    """
    What the engine will read for each employee, and what is wrong with it.

    Read-only as far as payroll is concerned — no payslip is created and no
    batch is written. Note that ``build_monthly_summary`` underneath does
    upsert its own AttendanceSummaryHours cache rows; that is its existing
    behaviour and is not payroll data.
    """
    from attendance.methods.utils import get_employee_attendance_summary

    ok, excluded = eligible_employees(employees, start_date, end_date)

    summaries = {}
    if ok:
        # The queryset form, which batches the whole set into a handful of
        # queries. The v2 engine called it once per employee; on a few hundred
        # people that is the difference between one page load and several.
        summaries = get_employee_attendance_summary(ok, start_date, end_date)

    rows = []
    for employee in ok:
        row = summaries.get(employee.pk, {}) or {}
        contract = employee.contract_set.filter(contract_status="active").first()
        problems = _exceptions_for(row, employee, contract)
        rows.append(
            {
                "employee": employee,
                "contract": contract,
                "summary": row,
                "present": row.get("present", 0),
                "paid_leave": row.get("paid_leave", 0),
                "unpaid_leave": row.get("unpaid_leave", 0),
                "absent": row.get("absent", 0),
                "week_off": row.get("week_off", 0),
                "holiday": row.get("holiday", 0),
                # This employee's working days, not the company-wide count.
                # get_working_days() is called without an employee, so on anyone
                # whose roster differs from the default the two disagree -- and a
                # row showing 23 working days beside 24 days of present/leave/
                # absent does not reconcile with itself.
                "total_working": row.get("working_days", row.get("total_working", 0)),
                "unresolved_conflicts": row.get("unresolved_conflicts", 0),
                # Present + paid leave + holiday + week off, as the attendance
                # summary counts it: the days this period actually pays for.
                "paid_days": row.get("paid_days", 0),
                "overtime_label": row.get("overtime_label", ""),
                # The label reads "44h 30m", which sorts as text into nonsense.
                # The seconds are what the column is ordered by.
                "overtime_seconds": row.get("overtime_seconds", 0),
                "problems": problems,
                "blocked": any(level == BLOCKING for level, _m in problems),
            }
        )

    for row in rows:
        row["low_paid"] = not row["blocked"] and row["paid_days"] < LOW_PAID_DAYS

    rows.sort(key=lambda r: (not r["blocked"], str(r["employee"])))
    return {
        "rows": rows,
        "excluded": excluded,
        "blocked_count": sum(1 for r in rows if r["blocked"]),
        "ready_count": sum(1 for r in rows if not r["blocked"]),
        "low_paid_count": sum(1 for r in rows if r["low_paid"]),
        "low_paid_threshold": LOW_PAID_DAYS,
    }


@transaction.atomic
def create_batch(*, name, start_date, end_date, employees, user=None, settings=None):
    """
    Record the run and queue everyone in it. Generates nothing.

    Separate from generation so that the batch exists — and is listed, and can
    be resumed — from the moment it is started, rather than only once it has
    finished successfully.
    """
    from payroll.models.models import PayPeriodSettings, PayrollBatch, PayrollBatchLine

    settings = settings or PayPeriodSettings()
    batch = PayrollBatch(
        batch_name=name,
        period_start=start_date,
        period_end=end_date,
        pay_date=settings.pay_date_for(end_date),
        created_by_user=user if (user and user.is_authenticated) else None,
        employee_count=len(employees),
        progress_state=PayrollBatch.PENDING,
    )
    batch.save()

    PayrollBatchLine.objects.bulk_create(
        [
            PayrollBatchLine(payroll_batch=batch, employee_id=employee)
            for employee in employees
        ]
    )
    return batch


def generate_slice(batch, size=SLICE_SIZE):
    """
    Generate the next few payslips. Returns how many were handled.

    Sliced rather than done in one request because a run of any size needs to
    show progress, and because a request that dies halfway should leave a
    resumable run rather than an unknown one. Each line is marked before the
    next begins, so a resumed run never pays the same person twice.

    Failures are recorded against the line and the run continues: one
    misconfigured contract should not stop everybody else being paid, and the
    result table is what tells someone which ones to fix.
    """
    from payroll.methods.methods import payslip_fields, save_payslip
    from payroll.methods.payroll_run import (
        StructureConfigurationError,
        payroll_calculation,
    )
    from payroll.methods.tax_calc import TaxComputationError
    from payroll.models.models import PayrollBatch, PayrollBatchLine

    if batch.progress_state == PayrollBatch.PENDING:
        batch.progress_state = PayrollBatch.RUNNING
        batch.save(update_fields=["progress_state"])

    queued = list(
        batch.lines.filter(status=PayrollBatchLine.QUEUED).select_related(
            "employee_id"
        )[:size]
    )
    if not queued:
        _finish(batch)
        return 0

    employees = [line.employee_id for line in queued]
    summaries = _summaries_for(employees, batch)

    for line in queued:
        employee = line.employee_id
        try:
            _generate_one(
                batch,
                line,
                employee,
                summaries.get(employee.pk, {}),
                payslip_fields,
                save_payslip,
                payroll_calculation,
            )
        except (StructureConfigurationError, TaxComputationError) as exc:
            # Expected, explainable refusals: the engine declining to invent a
            # figure. Recorded against the person so it can be fixed.
            line.status = PayrollBatchLine.FAILED
            line.message = str(exc)
            line.save(update_fields=["status", "message"])
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the run
            logger.exception("Payroll batch %s failed for %s", batch.pk, employee)
            line.status = PayrollBatchLine.FAILED
            line.message = f"{type(exc).__name__}: {exc}"
            line.save(update_fields=["status", "message"])

    batch.processed_count = batch.lines.exclude(status=PayrollBatchLine.QUEUED).count()
    batch.save(update_fields=["processed_count"])

    if not batch.lines.filter(status=PayrollBatchLine.QUEUED).exists():
        _finish(batch)

    return len(queued)


def _summaries_for(employees, batch):
    """
    The attendance summary for this slice, batched.

    Failing to read attendance must not fail the run: the engine falls back to
    its own day counting when no summary is passed, which is what the single
    payslip path has always done.
    """
    from attendance.methods.utils import get_employee_attendance_summary

    try:
        return get_employee_attendance_summary(
            employees, batch.period_start, batch.period_end
        )
    except Exception:  # noqa: BLE001
        logger.exception("Attendance summary unavailable for batch %s", batch.pk)
        return {}


def _generate_one(
    batch, line, employee, summary, payslip_fields, save_payslip, payroll_calculation
):
    """One payslip, attached to the batch."""
    from payroll.models.models import PayrollBatchLine

    contract = employee.contract_set.filter(contract_status="active").first()
    if contract is None:
        line.status = PayrollBatchLine.SKIPPED
        line.message = str(_("No active contract"))
        line.save(update_fields=["status", "message"])
        return

    # Per employee, never reassigning the caller's dates. The old bulk loop
    # mutated its own start_date for a mid-period contract and never restored
    # it, so one late joiner shifted the period for everybody after them.
    start_date = batch.period_start
    if contract.contract_start_date and contract.contract_start_date > start_date:
        start_date = contract.contract_start_date

    result = payroll_calculation(
        employee, start_date, batch.period_end, month_summary=summary or {}
    )
    payslip = save_payslip(
        **payslip_fields(
            result,
            employee,
            status="draft",
            group_name=batch.batch_name,
            payroll_batch=batch,
        )
    )

    line.status = PayrollBatchLine.DONE
    line.message = ""
    line.payslip = payslip
    line.save(update_fields=["status", "message", "payslip"])


def _finish(batch):
    from payroll.models.models import PayrollBatch

    batch.progress_state = PayrollBatch.DONE
    batch.processed_count = batch.employee_count
    batch.save(update_fields=["progress_state", "processed_count"])
    batch.refresh_totals()
