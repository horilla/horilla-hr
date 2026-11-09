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
import time
from contextvars import ContextVar

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from payroll.methods.component_catalog import use_catalog
from payroll.methods.contract_periods import (
    PAYABLE_STATUSES,
    contracts_in_period,
    use_contract,
)

logger = logging.getLogger(__name__)

# How many employees one request generates. Each request carries its own overhead (login check,
# attendance summary, rendering the bar), so too small a slice spends more time on round trips than
# on payslips; this still moves the bar every couple of seconds.
SLICE_SIZE = 20

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
        # Payroll is for people who work here now, and on a contract that is in
        # force: an inactive employee or one with no active contract is left out.
        if not employee.is_active:
            excluded.append((employee, _("Employee is inactive")))
            continue
        if not contracts_in_period(employee, start_date, end_date):
            later = employee.contract_set.filter(
                contract_status__in=PAYABLE_STATUSES, contract_start_date__gt=end_date
            ).exists()
            excluded.append(
                (
                    employee,
                    (
                        _("Contract starts after this period")
                        if later
                        else _("No contract in force in this period")
                    ),
                )
            )
            continue
        # The model refuses a second payslip for the same employee and period,
        # so catching it here is the difference between a listed exclusion and
        # an exception halfway through a run. Any payslip that overlaps the
        # period counts, not only an identical one: a period may begin on any
        # day and cross a month, so 1-30 September and 15 September-14 October
        # would otherwise both be paid for the same fortnight.
        if Payslip.objects.filter(
            employee_id=employee, start_date__lte=end_date, end_date__gte=start_date
        ).exists():
            excluded.append((employee, _("Already has a payslip for this period")))
            continue
        ok.append(employee)
    return ok, excluded


def recovery_over_pay(employee, contract, start_date, end_date):
    """
    ``(due, pay, titles)`` when the confirmed recoveries falling in this period come to more than
    the employee's monthly pay, otherwise ``None``.

    A payslip can only take what the pay covers: the deductions are capped at gross, and whatever is
    left is neither taken nor carried to the next period. Seen here, before anything is generated,
    the entry can still be sent back to Draft and corrected; on a payslip it can not.
    """
    from payroll.models.models import PayAdjustment

    if not (start_date and end_date):
        return None
    # The package for a CTC contract, else the monthly wage; nothing to compare with on a daily or
    # hourly wage, where the month's pay is not known until the days are counted.
    pay = float(contract.monthly_ctc or 0) or (
        float(contract.wage or 0) if contract.wage_type == "monthly" else 0.0
    )
    if pay <= 0:
        return None
    due = list(
        PayAdjustment.objects.filter(
            employee_id=employee,
            kind="recovery",
            status="approved",
            pay_date__range=(start_date, end_date),
        ).order_by("pay_date", "pk")
    )
    total = round(sum(entry.amount for entry in due), 2)
    if total <= pay:
        return None
    return total, pay, [entry.title for entry in due]


def _exceptions_for(row, employee, contract, start_date=None, end_date=None):
    """
    What is wrong with one employee's inputs, most serious first.

    Each is ``(severity, message)``. Blocking ones stop the run; warnings are
    shown and proceeded past, because "this person has no overtime approved
    yet" is worth knowing and is not a reason to hold up everybody's pay.
    """
    problems = []

    over = recovery_over_pay(employee, contract, start_date, end_date)
    if over:
        due, pay, titles = over
        problems.append(
            (
                BLOCKING,
                _(
                    "Recoveries Due This Period Come To %(due)s, More Than The Monthly Pay Of %(pay)s, "
                    "So Only Part Could Be Taken (%(titles)s). Send Them Back To Draft In Arrears & "
                    "Recovery And Spread Them Over More Months."
                )
                % {
                    "due": f"{due:,.2f}",
                    "pay": f"{pay:,.2f}",
                    "titles": ", ".join(titles),
                },
            )
        )

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
        contract = contracts_in_period(employee, start_date, end_date)[-1][0]
        problems = _exceptions_for(row, employee, contract, start_date, end_date)
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


# Set while a slice is being written: the batch row is then not touched per payslip, because that
# row lock would make parallel slices wait for each other. The totals are refreshed once the slice commits.
defer_batch_totals = ContextVar("defer_batch_totals", default=False)


def generate_slice(batch, size=SLICE_SIZE):
    """
    Generate the next few payslips. Returns how many were handled.

    Safe to call from several requests at once: the lines of a slice are claimed with a row lock that
    others skip, and held until the slice commits, so nobody is paid twice and a request that dies
    mid-slice leaves its lines queued for the next one. This is what lets the progress modal run
    several slices side by side.

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

    token = defer_batch_totals.set(True)
    try:
        with transaction.atomic(), use_catalog():
            queued = list(
                batch.lines.select_related("employee_id")
                .select_for_update(skip_locked=True, of=("self",))
                .filter(status=PayrollBatchLine.QUEUED)[:size]
            )
            if not queued:
                handled = 0
            else:
                handled = len(queued)
                employees = [line.employee_id for line in queued]
                summaries = _summaries_for(employees, batch)

                for line in queued:
                    employee = line.employee_id
                    try:
                        # A savepoint per person: a failure undoes that person's half-written rows only.
                        with transaction.atomic():
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
                    except (
                        Exception
                    ) as exc:  # noqa: BLE001 - one bad row must not stop the run
                        logger.exception(
                            "Payroll batch %s failed for %s", batch.pk, employee
                        )
                        line.status = PayrollBatchLine.FAILED
                        line.message = f"{type(exc).__name__}: {exc}"
                        line.save(update_fields=["status", "message"])
    finally:
        defer_batch_totals.reset(token)

    if not handled:
        if batch.lines.filter(status=PayrollBatchLine.QUEUED).exists():
            # Everything left is being written by another slice: wait for it rather than finish early.
            time.sleep(0.3)
        else:
            _finish(batch)
        return 0

    batch.processed_count = batch.lines.exclude(status=PayrollBatchLine.QUEUED).count()
    batch.save(update_fields=["processed_count"])
    batch.refresh_totals()

    if not batch.lines.filter(status=PayrollBatchLine.QUEUED).exists():
        _finish(batch)

    return handled


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

    # Checked again here, not only when the run was scoped: someone can be
    # deactivated, or their contract ended, between reviewing and generating.
    if not employee.is_active:
        line.status = PayrollBatchLine.SKIPPED
        line.message = str(_("Employee is inactive"))
        line.save(update_fields=["status", "message"])
        return

    slices = contracts_in_period(employee, batch.period_start, batch.period_end)
    if not slices:
        line.status = PayrollBatchLine.SKIPPED
        line.message = str(_("No contract in force in this period"))
        line.save(update_fields=["status", "message"])
        return

    # One payslip per contract in force, each for its own days and at its own wage. Dates are
    # worked out per employee and never written back to the batch: the old bulk loop mutated its
    # own start_date for a mid-period contract and never restored it, so one late joiner shifted
    # the period for everybody after them.
    payslip = None
    for contract, start_date, end_date in slices:
        if len(slices) == 1:
            # One contract: the batch's own attendance summary, as it always was. A joiner's or
            # leaver's days outside the contract are unpaid days in it.
            slice_summary, prorate = summary or {}, False
        else:
            # Several: each contract's days are summarised on their own, and its wage is cut to
            # them, because the whole period's summary would charge one contract for the other's days.
            slice_summary, prorate = (
                _slice_summary(employee, start_date, end_date),
                True,
            )
        with use_contract(contract):
            result = payroll_calculation(
                employee,
                start_date,
                end_date,
                month_summary=slice_summary,
                prorate_slice=prorate,
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
    # Done, but not all of it: the deductions came to more than the pay, so part was left untaken.
    uncovered = float(((payslip.pay_head_data or {}).get("uncovered_deduction")) or 0)
    line.message = (
        str(
            _(
                "%(amount)s Could Not Be Deducted: The Deductions Came To More Than The Pay."
            )
            % {"amount": f"{uncovered:,.2f}"}
        )
        if uncovered > 0.005
        else ""
    )
    line.payslip = payslip
    line.save(update_fields=["status", "message", "payslip"])


def _slice_summary(employee, start_date, end_date):
    """The attendance summary for one contract's days, or {} when it cannot be read."""
    from attendance.methods.utils import get_employee_attendance_summary

    try:
        return (
            get_employee_attendance_summary([employee], start_date, end_date).get(
                employee.pk, {}
            )
            or {}
        )
    except Exception:  # noqa: BLE001
        logger.exception("Attendance summary unavailable for %s", employee)
        return {}


def _finish(batch):
    from payroll.models.models import PayrollBatch

    batch.progress_state = PayrollBatch.DONE
    batch.processed_count = batch.employee_count
    batch.save(update_fields=["progress_state", "processed_count"])
    batch.refresh_totals()
