"""
scheduler.py

This module is used to register scheduled tasks
"""

import json
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from horilla.scheduling import register_job
from payroll.methods.methods import calculate_employer_contribution, save_payslip
from payroll.views.component_views import payroll_calculation

from .models.models import Contract, Payslip


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

    # Filter out employees who don't have a contract_set or whose contract status is not active
    active_employees = employees.filter(
        contract_set__isnull=False, contract_set__contract_status="active"
    )

    # Remove duplicates if an employee has multiple active contracts
    active_employees = active_employees.distinct()
    # find the date range
    period_start = date - relativedelta(months=1)
    period_end = date - timedelta(days=1)
    # Payslip creation
    for employee in active_employees:
        payslip = Payslip.objects.filter(
            employee_id=employee, start_date=period_start, end_date=period_end
        ).first()
        if payslip:
            continue
        contract = Contract.objects.filter(
            employee_id=employee, contract_status="active"
        ).first()
        if period_end < contract.contract_start_date:
            continue
        # A contract starting mid-period shortens only that employee's payslip,
        # so the adjusted start must stay local to this iteration.
        start_date = max(period_start, contract.contract_start_date)
        payslip_data = payroll_calculation(employee, start_date, period_end)
        payslip_data["payslip"] = payslip
        data = {}
        data["employee"] = employee
        data["start_date"] = payslip_data["start_date"]
        data["end_date"] = payslip_data["end_date"]
        data["status"] = "draft"
        data["contract_wage"] = payslip_data["contract_wage"]
        data["basic_pay"] = payslip_data["basic_pay"]
        data["gross_pay"] = payslip_data["gross_pay"]
        data["deduction"] = payslip_data["total_deductions"]
        data["net_pay"] = payslip_data["net_pay"]
        data["pay_data"] = json.loads(payslip_data["json_data"])
        calculate_employer_contribution(data)
        data["installments"] = payslip_data["installments"]
        payslip_data["instance"] = save_payslip(**data)


def is_last_day_of_month(date):
    next_day = date + timedelta(days=1)
    return next_day.month != date.month


def auto_payslip_generate():
    """
    Generating payslips for active contract employees
    """
    from base.models import Company

    from .models.models import PayslipAutoGenerate

    # from payroll.models import PayslipAutoGenerate
    if PayslipAutoGenerate.objects.filter(auto_generate=True).exists():
        today = date.today()
        day_today = today.day
        last_day = (today + timedelta(days=1)).replace(day=1) - timedelta(days=1)
        auto_payslips = PayslipAutoGenerate.objects.filter(auto_generate=True)
        companies = []
        auto_companies = [auto.company_id for auto in auto_payslips]
        for auto in auto_payslips:
            generate_day = auto.generate_day
            if generate_day == "last day":
                if is_last_day_of_month(today):
                    companies.append(auto.company_id)
            else:
                generate_day = int(generate_day)
                if generate_day >= last_day.day and day_today == last_day.day:
                    companies.append(auto.company_id)
                elif generate_day == day_today:
                    companies.append(auto.company_id)

        companies = list(set(companies))  # Remove duplicates
        # Check if 'All company' case exists, i.e., None is in companies
        if companies:
            if None in companies:
                company_all = Company.objects.all()
                generate_companies = []
                # Append the companies that are not in PayslipAutoGenerate
                for company in company_all:
                    if company not in auto_companies:
                        generate_companies.append(company)
                generate_payslip(
                    date=date.today(), companies=generate_companies, all=True
                )
            else:
                generate_payslip(date=date.today(), companies=companies, all=False)


register_job(expire_contract, "interval", hours=4)
register_job(auto_payslip_generate, "interval", hours=3)
