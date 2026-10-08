"""
Module: payroll.tax_calc

This module contains a function for calculating the taxable amount for an employee
based on their contract details and income information.
"""

import datetime
import logging

from payroll.methods.methods import (
    compute_yearly_taxable_amount,
    convert_year_tax_to_period,
)
from payroll.methods.payslip_calc import (
    calculate_gross_pay,
    calculate_taxable_gross_pay,
)
from payroll.methods.safe_tax_code import run_tax_code
from payroll.models.models import Contract
from payroll.models.tax_models import TaxBracket

logger = logging.getLogger(__name__)


class TaxComputationError(Exception):
    """
    Raised when a filing status is configured to compute tax but cannot.

    Deliberately not swallowed. The previous behaviour here was
    ``except Exception: logger.error(e)``, which left ``federal_tax`` at 0 and
    produced a payslip that looked entirely normal while under-withholding —
    the employee is overpaid, the employer owes the difference, and nothing on
    the payslip says so. A log line nobody reads is not a control.

    This fires only for a filing status that *is* configured to compute tax and
    failed. A contract with no filing status at all still yields 0, because
    that legitimately means "no income tax configured for this employee" — many
    tenants model income tax with ``Deduction(is_tax=True)`` instead and never
    set one.
    """


def compute_yearly_tax(filing, yearly_income, employee=None):
    """
    Tax on a yearly income under ``filing``, plus a breakdown of how it got there.

    This is the whole of what a filing status *means*, and it is deliberately
    the only implementation: ``calculate_taxable_amount`` calls it for real
    payslips and the configuration preview calls it for a hypothetical income.
    A preview that computes its own way agrees with payroll right up until the
    day it doesn't, and then it is actively misleading about a number people
    are paid by.

    Order matters and is not arbitrary:

      1. the standard deduction comes off income, so slabs and a Python formula
         both see the reduced figure;
      2. slabs or the formula compute the tax;
      3. a rebate forgives up to a fixed amount when income is at or below its
         limit (India's 87A);
      4. cess is applied last, because it is levied on the tax actually payable
         after relief, not before it.

    Every adjustment is a no-op at its default, so a filing status that
    predates them computes exactly as it did.

    ``employee`` is only used to name who a failure belongs to; the preview has
    nobody and passes None.
    """
    gross_yearly_income = yearly_income
    standard_deduction = float(filing.standard_deduction or 0)
    if standard_deduction:
        yearly_income = round(max(yearly_income - standard_deduction, 0.0), 2)

    tax_brackets = TaxBracket.objects.filter(filing_status_id=filing).order_by(
        "min_income"
    )

    federal_tax = 0
    slab_rows = []
    if not filing.use_py:
        # The top band is open-ended, and there are two spellings of that in
        # the data: NULL (what the slab grid saves) and math.inf (what the
        # older per-bracket forms wrote). inf cannot be stored by MySQL and is
        # not valid JSON, so NULL is the one to keep — but both have to compute
        # for as long as either exists in a tenant's database.
        brackets = [
            {
                "rate": item["tax_rate"],
                "min": item["min_income"],
                "max": (
                    yearly_income
                    if item["max_income"] is None
                    else min(item["max_income"], yearly_income)
                ),
            }
            for item in tax_brackets.values("tax_rate", "min_income", "max_income")
        ]
        filterd_brackets = []
        slab_rows = []
        for bracket in brackets:
            if bracket["max"] > bracket["min"]:
                bracket["diff"] = bracket["max"] - bracket["min"]
                bracket["calculated_rate"] = (bracket["rate"] / 100) * bracket["diff"]
                filterd_brackets.append(bracket)
                slab_rows.append(
                    {
                        "from": round(float(bracket["min"]), 2),
                        "to": round(float(bracket["max"]), 2),
                        "rate": float(bracket["rate"]),
                        "tax": round(bracket["calculated_rate"], 2),
                    }
                )
                continue
            break
        federal_tax = sum(bracket["calculated_rate"] for bracket in filterd_brackets)
    else:
        try:
            federal_tax = run_tax_code(filing.python_code, yearly_income)
        except Exception as exc:
            # The empty-code case is the common one and deserves its own
            # wording: the editor used to write python_code via a postMessage
            # callback, so saving before it fired stored "" while use_py stayed
            # on, and every payslip then silently taxed at 0.
            detail = (
                "its Python code is empty"
                if not (filing.python_code or "").strip()
                else f"{type(exc).__name__}: {exc}"
            )
            whose = f" for {employee}" if employee is not None else ""
            logger.error(
                "Tax computation failed for filing status %s (employee %s): %s",
                filing.filing_status,
                employee,
                exc,
            )
            raise TaxComputationError(
                f"Filing status '{filing.filing_status}' could not compute tax"
                f"{whose} — {detail}. Fix the filing status, or switch "
                f"it off Python mode, then generate the payslip again."
            ) from exc

    tax_before_relief = federal_tax

    rebate_limit = filing.rebate_income_limit
    rebate_max = filing.rebate_max_amount
    rebate_applied = 0.0
    if (
        federal_tax
        and rebate_limit is not None
        and yearly_income <= float(rebate_limit)
    ):
        rebate_applied = min(float(rebate_max or 0), federal_tax)
        federal_tax = max(federal_tax - float(rebate_max or 0), 0.0)

    cess_percent = float(filing.cess_percent or 0)
    cess_applied = 0.0
    if federal_tax and cess_percent:
        cess_applied = federal_tax * cess_percent / 100
        federal_tax = federal_tax + cess_applied

    breakdown = {
        "gross_yearly_income": round(gross_yearly_income, 2),
        "standard_deduction": round(standard_deduction, 2),
        "taxable_income": round(yearly_income, 2),
        "tax_before_relief": round(tax_before_relief, 2),
        "rebate_applied": round(rebate_applied, 2),
        "cess_applied": round(cess_applied, 2),
        "tax": round(federal_tax, 2),
        "mode": "formula" if filing.use_py else "slabs",
        # The bands the income fell into: where it starts, where it stopped (the
        # income itself in the top band), the rate and what that band came to.
        "slabs": slab_rows,
    }
    return federal_tax, breakdown


def preview_yearly_tax(filing, yearly_income):
    """Breakdown only, for the configuration screen. Saves nothing."""
    _tax, breakdown = compute_yearly_tax(filing, yearly_income)
    return breakdown


def calculate_taxable_amount(**kwargs):
    """Calculate the taxable amount for a given employee within a specific period.

    Args:
        employee (int): The ID of the employee.
        start_date (datetime.date): The start date of the period.
        end_date (datetime.date): The end date of the period.
        allowances (int): The number of allowances claimed by the employee.
        total_allowance (float): The total allowance amount.
        basic_pay (float): The basic pay amount.
        day_dict (dict): A dictionary containing specific day-related information.

    Returns:
        float: The federal tax amount for the specified period.
    """
    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    basic_pay = kwargs["basic_pay"]
    contract = Contract.objects.filter(
        employee_id=employee, contract_status="active"
    ).first()
    filing = contract.filing_status
    if not filing:
        return 0
    num_days = (end_date - start_date).days + 1
    calculation_functions = {
        "taxable_gross_pay": calculate_taxable_gross_pay,
        "gross_pay": calculate_gross_pay,
    }
    based = filing.based_on
    if based in calculation_functions:
        calculation_function = calculation_functions[based]
        income = calculation_function(**kwargs)
        income = float(income[based])
    else:
        income = float(basic_pay)

    return period_tax(
        filing,
        income,
        start_date,
        end_date,
        employee=employee,
        pay_frequency=contract.pay_frequency,
    )


# How many pay periods make a year, per contract pay frequency. Payroll
# withholding is worked per pay period, not per day: the period's taxable pay is
# annualised by the number of periods (monthly x 12, semi-monthly x 24, weekly
# x 52), tax is worked out on that yearly figure through the slabs, and one
# period carries 1/N of it. This is the percentage / annualised method used by
# US withholding, Indian TDS projections and most payroll packages.
PERIODS_PER_YEAR = {"monthly": 12, "semi_monthly": 24, "weekly": 52}

# The longest a payslip period can be and still count as one pay period of that
# frequency. Anything longer (a run covering several months, say) is not one
# period, so it falls back to scaling by days.
_MAX_PERIOD_DAYS = {"monthly": 31, "semi_monthly": 16, "weekly": 7}


def periods_in_year(pay_frequency, start_date, end_date):
    """
    The pay periods per year this payslip's tax is annualised by, or None when
    the dates do not describe a single pay period of that frequency.

    A part period (someone joined mid-month) still counts as the period: its
    smaller pay is annualised like a full one, because withholding follows the
    pay actually received in the period, not the days it spans.
    """
    frequency = pay_frequency or "monthly"
    periods = PERIODS_PER_YEAR.get(frequency)
    if not periods:
        return None
    days = (end_date - start_date).days + 1
    if days > _MAX_PERIOD_DAYS[frequency]:
        return None
    if frequency == "monthly" and (start_date.year, start_date.month) != (
        end_date.year,
        end_date.month,
    ):
        return None
    return periods


def period_tax(filing, income, start_date, end_date, employee=None, pay_frequency=None):
    """
    The tax for one period, given the figure the filing status taxes.

    ``income`` is already the right basis (taxable gross, gross or basic -- see
    ``filing.based_on``). Split out of ``calculate_taxable_amount`` so a payslip
    whose figures were edited by hand can have its tax worked out the same way
    the engine did, instead of keeping the number from before the edit.
    """
    tax_brackets = TaxBracket.objects.filter(filing_status_id=filing).order_by(
        "min_income"
    )
    num_days = (end_date - start_date).days + 1
    year = end_date.year
    check_start_date = datetime.date(year, 1, 1)
    check_end_date = datetime.date(year, 12, 31)
    total_days = (check_end_date - check_start_date).days + 1
    periods = periods_in_year(pay_frequency, start_date, end_date)
    if periods:
        yearly_income = income * periods
    else:
        yearly_income = income / num_days * total_days
    yearly_income = compute_yearly_taxable_amount(income, yearly_income)
    yearly_income = round(yearly_income, 2)

    federal_tax, _breakdown = compute_yearly_tax(
        filing, yearly_income, employee=employee
    )

    federal_tax_for_period = 0
    if federal_tax and (tax_brackets.exists() or filing.use_py):
        if periods:
            federal_tax_for_period = federal_tax / periods
        else:
            daily_federal_tax = federal_tax / total_days
            federal_tax_for_period = daily_federal_tax * num_days

    federal_tax_for_period = convert_year_tax_to_period(
        federal_tax_for_period=federal_tax_for_period,
        yearly_tax=federal_tax,
        total_days=total_days,
        start_date=start_date,
        end_date=end_date,
    )
    return federal_tax_for_period


def explain_period_tax(
    filing, income, start_date, end_date, employee=None, pay_frequency=None
):
    """
    Everything between a period's taxable pay and its tax, step by step.

    Built from the same pieces ``period_tax`` is: ``periods_in_year`` for the
    annualisation and ``compute_yearly_tax`` for the yearly figure, so what is
    laid out here cannot differ from what was charged. Used to show someone how
    their Income Tax line came to be.
    """
    periods = periods_in_year(pay_frequency, start_date, end_date)
    num_days = (end_date - start_date).days + 1
    total_days = 366 if _is_leap(end_date.year) else 365
    if periods:
        yearly_income = income * periods
        method = "periods"
    else:
        yearly_income = income / num_days * total_days
        method = "days"
    yearly_income = round(compute_yearly_taxable_amount(income, yearly_income), 2)
    yearly_tax, breakdown = compute_yearly_tax(filing, yearly_income, employee=employee)
    if periods:
        tax = yearly_tax / periods
    else:
        tax = yearly_tax / total_days * num_days
    return {
        "filing_status": filing.filing_status,
        "based_on": filing.based_on,
        "income": round(float(income), 2),
        "method": method,
        "periods": periods,
        "days": num_days,
        "year_days": total_days,
        "yearly_income": yearly_income,
        "breakdown": breakdown,
        "yearly_tax": round(float(yearly_tax), 2),
        "period_tax": round(float(tax), 2),
        "rules_pk": filing.pk,
    }


def _is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
