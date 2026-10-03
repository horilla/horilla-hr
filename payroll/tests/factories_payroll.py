"""
Factories for the payroll engine's golden suite.

These build *real* Allowance/Deduction/Contract/FilingStatus rows rather than
``SimpleNamespace`` fakes. That distinction matters: the existing payroll unit
tests fake their components, which is why none of them catch the parallel-list
``zip()`` misattribution in ``calculate_post_tax_deduction`` — that bug only
shows up when several real components are gathered and re-paired.

Layered over ``horilla.testkit.factories``, which already provides
``make_company`` / ``make_employee`` / ``make_contract``.
"""

from __future__ import annotations

from datetime import date

from payroll.models.models import Allowance, Contract, Deduction, FilingStatus
from payroll.models.tax_models import TaxBracket

# Every component is gated on a hidden "if basic pay > 0" condition by default
# (Allowance.if_choice / if_condition / if_amount). Tests that want a component
# to actually apply must leave those defaults alone and keep basic pay > 0.
PERIOD_START = date(2024, 1, 1)
PERIOD_END = date(2024, 1, 31)


def make_active_contract(employee, **overrides) -> Contract:
    """An *active* contract. The engine only ever looks at active ones."""
    defaults = dict(
        contract_name="Golden Contract",
        employee_id=employee,
        contract_start_date=PERIOD_START,
        wage_type="monthly",
        wage=30000.0,
        contract_status="active",
        deduct_leave_from_basic_pay=True,
        calculate_daily_leave_amount=True,
        deduction_for_one_leave_amount=0,
    )
    defaults.update(overrides)
    return Contract.objects.create(**defaults)


def make_allowance(employee, title, **overrides) -> Allowance:
    """
    An allowance targeted at exactly one employee.

    ``specific_employees`` rather than ``include_active_employees`` so a
    scenario's components can never leak into another scenario's payslip.
    """
    defaults = dict(
        title=title,
        is_taxable=True,
        is_fixed=True,
        amount=1000.0,
        is_condition_based=False,
        has_max_limit=False,
        include_active_employees=False,
    )
    defaults.update(overrides)
    allowance = Allowance.objects.create(**defaults)
    allowance.specific_employees.add(employee)
    return allowance


def make_deduction(employee, title, **overrides) -> Deduction:
    """
    A deduction targeted at one employee.

    Which phase it lands in is decided by the flags, not by a phase argument:
      * ``is_pretax=True``                -> pretax_deductions
      * ``is_tax=True``                   -> tax_deductions
      * both False                        -> post_tax_deductions
      * ``update_compensation`` set       -> basic/gross/net compensation pass
    """
    defaults = dict(
        title=title,
        is_fixed=True,
        amount=500.0,
        is_pretax=False,
        is_tax=False,
        is_condition_based=False,
        has_max_limit=False,
        include_active_employees=False,
    )
    defaults.update(overrides)
    deduction = Deduction.objects.create(**defaults)
    deduction.specific_employees.add(employee)
    return deduction


def make_filing_status(
    title="Golden Status", brackets=None, **overrides
) -> FilingStatus:
    """
    A filing status plus its bands.

    ``brackets`` is a list of ``(min_income, max_income, tax_rate)``. Pass
    ``max_income=None`` for the unbounded top band — today the engine stores
    ``math.inf`` there, which is one of the things the tax work replaces.
    """
    defaults = dict(
        filing_status=title,
        based_on="taxable_gross_pay",
        use_py=False,
    )
    defaults.update(overrides)
    status = FilingStatus.objects.create(**defaults)
    for min_income, max_income, rate in brackets or []:
        TaxBracket.objects.create(
            filing_status_id=status,
            min_income=min_income,
            max_income=max_income,
            tax_rate=rate,
        )
    return status
