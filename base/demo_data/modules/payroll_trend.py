"""Give underrepresented companies a fairer share of demo Payslip coverage.

normalize_demo_payslips() (base/views.py) correctly re-anchors every
existing "Demo Payroll M-<n>"-tagged Payslip onto whatever months it is
already tagged for, but it never creates new ones. Two of the three demo
companies have full Contract coverage yet only ~4 employees ever get paid,
while the largest company pays a meaningfully larger share of its own staff
-- most contracted employees in the smaller companies never appear on a
payslip at all.

This creates real payslips, computed through the same calculation engine
the app's own scheduled payslip generation uses (payroll_calculation +
save_payslip), for a handful more contracted employees per company -- one
for the current month if it has actually closed (today is its last day),
otherwise one each for the two months before it (see _target_periods) --
tagged the same "Demo Payroll M-<n>" convention so normalize_demo_payslips
keeps re-anchoring them on every future run.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date

from django.apps import apps
from django.db import transaction
from django.db.models import Q

logger = logging.getLogger(__name__)

DEMO_PAYROLL_GROUP_PREFIX = "Demo Payroll M-"
# base/views.py's normalize_demo_payslips() renames this prefix to
# "Demo Payroll - <Mon Year>" for a human-readable label, every load -- the
# "already paid" check below must recognize both forms, or a payslip that's
# already been through that rename becomes invisible to this check and a
# brand-new cohort gets backfilled on top of it every reload.
DEMO_PAYROLL_RENAMED_PREFIX = "Demo Payroll - "
TARGET_PAID_PER_COMPANY = 12


def _target_periods(today: date) -> list[tuple[int, date, date]]:
    """
    Which month(s) to backfill a payslip for, and their real boundaries.

    A payslip is only generated for a month that has actually closed: if
    today is that month's own last day, the current month counts as closed
    and is the only one generated (M-0). On any other day the current month
    is still in progress, so it is skipped entirely and the two months
    before it -- both fully in the past -- are generated instead (M-1, M-2).
    Either way the period's own end is that month's real last day, not a
    fixed 28th (which undershoots every month with 29+ days).
    """
    last_day_of_month = calendar.monthrange(today.year, today.month)[1]
    offsets = [0] if today.day == last_day_of_month else [1, 2]

    periods = []
    for offset in offsets:
        year, month = today.year, today.month - offset
        while month < 1:
            month += 12
            year -= 1
        end_day = calendar.monthrange(year, month)[1]
        periods.append((offset, date(year, month, 1), date(year, month, end_day)))
    return periods


@transaction.atomic
def backfill_payroll_coverage(today: date | None = None) -> int:
    """Ensure at least TARGET_PAID_PER_COMPANY employees per company have a
    demo payslip for the month(s) _target_periods selects, computed against
    their real attendance monthly summary -- the same engine and the same
    attendance data path the payroll batch run uses -- so the generated data
    is genuinely valid rather than falling back to a plain day count."""
    if not apps.is_installed("payroll"):
        return 0

    today = today or date.today()

    from attendance.methods.utils import get_employee_attendance_summary
    from employee.models import Employee, EmployeeWorkInformation
    from payroll.methods.methods import payslip_fields, save_payslip
    from payroll.models.models import Contract, Payslip
    from payroll.views.component_views import payroll_calculation

    contracted_employee_ids = set(
        Contract._base_manager.filter(contract_status="active").values_list(
            "employee_id", flat=True
        )
    )
    company_by_employee = dict(
        EmployeeWorkInformation._base_manager.values_list("employee_id", "company_id")
    )

    already_paid_by_company: dict[int, set[int]] = {}
    paid_employee_ids = (
        Payslip._base_manager.filter(
            Q(group_name__startswith=DEMO_PAYROLL_GROUP_PREFIX)
            | Q(group_name__startswith=DEMO_PAYROLL_RENAMED_PREFIX)
        )
        .values_list("employee_id", flat=True)
        .distinct()
    )
    for employee_id in paid_employee_ids:
        company_id = company_by_employee.get(employee_id)
        already_paid_by_company.setdefault(company_id, set()).add(employee_id)

    candidates_by_company: dict[int, list[int]] = {}
    for employee_id in sorted(contracted_employee_ids):
        company_id = company_by_employee.get(employee_id)
        if company_id is not None:
            candidates_by_company.setdefault(company_id, []).append(employee_id)

    created = 0
    for company_id, candidate_ids in candidates_by_company.items():
        already_paid = already_paid_by_company.get(company_id, set())
        need = TARGET_PAID_PER_COMPANY - len(already_paid)
        if need <= 0:
            continue
        new_targets = [e for e in candidate_ids if e not in already_paid][:need]
        employees = {e.pk: e for e in Employee._base_manager.filter(pk__in=new_targets)}

        for offset, period_start, period_end in _target_periods(today):
            # Fetched once per period across this company's whole cohort,
            # not once per employee: same real attendance-summary path the
            # payroll batch run uses.
            try:
                summaries = get_employee_attendance_summary(
                    list(employees.values()), period_start, period_end
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Attendance summary unavailable while backfilling demo payslips"
                )
                summaries = {}

            for employee_id in new_targets:
                if Payslip._base_manager.filter(
                    employee_id=employee_id,
                    start_date=period_start,
                    end_date=period_end,
                ).exists():
                    continue

                employee = employees[employee_id]
                result = payroll_calculation(
                    employee,
                    period_start,
                    period_end,
                    month_summary=summaries.get(employee_id, {}),
                )
                if not result:
                    # No active contract for this exact period (a mid-window
                    # end date, an already-expired contract) -- a payslip
                    # cannot exist for someone it cannot be computed for.
                    continue

                fields = payslip_fields(
                    result,
                    employee,
                    status="paid",
                    group_name=f"{DEMO_PAYROLL_GROUP_PREFIX}{offset}",
                )
                save_payslip(**fields)
                created += 1

    logger.info(
        "Payroll backfill: created %s payslip(s) to rebalance per-company coverage",
        created,
    )
    return created
