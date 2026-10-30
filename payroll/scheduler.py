"""
scheduler.py

This module is used to register scheduled tasks
"""

import logging
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from horilla.scheduling import register_job
from payroll.methods.methods import payslip_fields, save_payslip
from payroll.methods.payroll_run import payroll_calculation
from payroll.methods.tax_calc import TaxComputationError

from .methods.contract_periods import (
    PAYABLE_STATUSES,
    contracts_in_period,
    use_contract,
)
from .models.models import Contract, Payslip

logger = logging.getLogger(__name__)


def expire_contract():
    """
    Finds all active contracts whose end date is earlier than the current date
    and updates their status to "expired".
    """
    Contract.objects.filter(
        contract_status="active", contract_end_date__lt=date.today()
    ).update(contract_status="expired")
    return


def generate_payslip(date, companies, all):
    """Generate payslip for previous month"""

    from employee.models import Employee

    date = date
    employees = Employee.objects.none()
    # Get all employees with in the companies
    if all == True:
        employees = employees | Employee.objects.filter(
            employee_work_info__company_id__isnull=True
        )
    if companies:
        for company in companies:
            employees = employees | Employee.objects.filter(
                employee_work_info__company_id=company
            )

    period_start = date - relativedelta(months=1)
    period_end = date - timedelta(days=1)
    generate_payslips(employees, period_start, period_end)


def generate_payslips(employees, period_start, period_end):
    """
    Create draft payslips for ``employees`` who have an active contract, for one period.
    Returns how many were created.
    """
    created = 0
    # Anyone with a contract that could have days in the period, ended ones included: an ended
    # contract still has its last days to be paid.
    candidates = employees.filter(
        contract_set__contract_status__in=PAYABLE_STATUSES,
        contract_set__contract_start_date__lte=period_end,
    ).distinct()
    for employee in candidates:
        # One payslip per contract in force, each for its own days. A contract that began or ended
        # mid-period shortens only its own slice.
        for contract, start_date, end_date in contracts_in_period(
            employee, period_start, period_end
        ):
            if Payslip.objects.filter(
                employee_id=employee, start_date__lte=end_date, end_date__gte=start_date
            ).exists():
                continue
            try:
                with use_contract(contract):
                    payslip_data = payroll_calculation(employee, start_date, end_date)
            except TaxComputationError as exc:
                # Unattended job: skip the employee whose filing status is broken
                # rather than saving them a 0-tax payslip or aborting the run for
                # everyone else. The next scheduled run picks them up once fixed.
                logger.error("Scheduled payslip skipped: %s", exc)
                continue
            payslip_data["payslip"] = None
            payslip_data["instance"] = save_payslip(
                **payslip_fields(payslip_data, employee, status="draft")
            )
            created += 1
    return created


def is_last_day_of_month(date):
    next_day = date + timedelta(days=1)
    return next_day.month != date.month


def auto_payslip_generate():
    """
    Deprecated: replaced by ``generate_pay_period_payslips``. Kept as a no-op so old callers
    do not break.
    """


def employees_for(setting):
    """The employees a pay period setting covers: its company, or the companies with no row."""
    from employee.models import Employee

    from .models.models import PayPeriodSettings

    if setting.company_id_id:
        return Employee.objects.filter(
            employee_work_info__company_id=setting.company_id_id
        )
    own_companies = (
        PayPeriodSettings.objects.entire()
        .filter(company_id__isnull=False)
        .values_list("company_id", flat=True)
    )
    return Employee.objects.filter(
        employee_work_info__company_id__isnull=True
    ) | Employee.objects.exclude(employee_work_info__company_id__in=list(own_companies))


def generate_for_setting(setting, today, force=False):
    """
    Generate the last completed period's payslips for one setting; returns how many were made,
    or None when this period was already claimed.

    The period is claimed in one UPDATE before any work, so two runs (two processes, or a
    retry) can never both generate it; a failure releases the claim. ``force`` is the manual
    run: it does not need the claim, and payslips that exist are never made twice.
    """
    from .models.models import PayPeriodSettings

    start, end = setting.last_completed_period(today)
    rows = PayPeriodSettings.objects.entire().filter(pk=setting.pk)
    previous = rows.values_list("last_generated_end", flat=True).first()
    if force:
        rows.update(last_generated_end=end)
    elif not rows.exclude(last_generated_end__gte=end).update(last_generated_end=end):
        return None
    try:
        return generate_payslips(employees_for(setting), start, end)
    except Exception:
        rows.update(last_generated_end=previous)
        raise


def generate_pay_period_payslips(today=None):
    """
    For each pay period setting with Generate Payslips Automatically on, create draft payslips
    on the day after its period ends. A setting for all companies covers the companies that
    have none of their own.
    """
    from .models.models import PayPeriodSettings

    today = today or date.today()
    for setting in PayPeriodSettings.objects.entire().filter(auto_generate=True):
        _start, end = setting.last_completed_period(today)
        if today != end + timedelta(days=1):
            continue
        try:
            generate_for_setting(setting, today)
        except Exception:
            # One company's failure must not stop the others; the next run (every 3 hours,
            # still on that day) tries it again.
            logger.exception("Payslip generation failed for %s", setting.get_company())


register_job(expire_contract, "interval", hours=4)
register_job(generate_pay_period_payslips, "interval", hours=3)
