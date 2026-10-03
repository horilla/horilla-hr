"""Connect fully-built Payroll features to real demo data.

SalaryStructure and the Federal Tax Bracket system are complete, live
features with real business logic (Contract.set_salary_structure(),
progressive tax computation in payroll_calculation()) but ship with zero
demo data connecting them to any employee -- a demo walkthrough that opens
either page sees a working feature with nothing in it.
"""

from __future__ import annotations

import logging
from datetime import date

from django.apps import apps
from django.db import transaction

logger = logging.getLogger(__name__)

# Reuses the existing Allowance/Deduction catalog (see payroll_data.json)
# rather than inventing new lookup data.
SALARY_STRUCTURE_ALLOWANCE_TITLES = ("House Rent Allowance (HRA)", "Meal Allowance")
SALARY_STRUCTURE_DEDUCTION_TITLES = ("Provident Fund (PF)", "Professional Tax")
CONTRACTS_PER_COMPANY = 5

# A minority, taken from the contracts right after the ones above rather than
# reused from them: the two modes need separate contracts to each show up as
# themselves, and Gross Up is meant to stay the common case a demo walkthrough
# sees first.
CTC_DOWN_CONTRACTS_PER_COMPANY = 2
CTC_DOWN_WAGE_TO_CTC_MULTIPLIER = 2.2


def _get_or_create_ctc_down_components(flat_earnings):
    """
    The component set CTC Down requires, reusing the recipe already proven
    in create_payroll_fixtures.py rather than inventing a second one:
    validate_component_set refuses a CTC Down structure without exactly one
    is_basic_pay earning, and refuses one where a based_on="balance" earning
    is not last, so this is not a free choice.

    Global rows shared across every company's own CTC Down SalaryStructure,
    the same way SALARY_STRUCTURE_ALLOWANCE_TITLES already are for Gross Up
    -- get_or_create makes this safe to call on every reload.
    """
    from payroll.models.models import Allowance

    basic, _ = Allowance._base_manager.get_or_create(
        code="BASIC",
        defaults=dict(
            title="Basic Pay",
            sequence=5,
            is_basic_pay=True,
            is_fixed=False,
            based_on="formula",
            formula="CTC * 0.4",
            is_taxable=True,
            include_active_employees=False,
            is_condition_based=False,
        ),
    )
    ctc_hra, _ = Allowance._base_manager.get_or_create(
        code="CHRA",
        defaults=dict(
            title="House Rent Allowance",
            sequence=10,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=40.0,
            is_taxable=True,
            include_active_employees=False,
            is_condition_based=False,
        ),
    )
    ctc_da, _ = Allowance._base_manager.get_or_create(
        code="CDA",
        defaults=dict(
            title="Dearness Allowance",
            sequence=20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=12.0,
            is_taxable=True,
            include_active_employees=False,
            is_condition_based=False,
        ),
    )
    # Absorbs whatever the fixed and percentage earnings before it did not use
    # up. Only meaningful in CTC Down, and only as the last component --
    # structure_problems() refuses one that is not.
    balance, _ = Allowance._base_manager.get_or_create(
        code="FLEX",
        defaults=dict(
            title="Flexible Benefits (Balance)",
            sequence=90,
            is_fixed=False,
            based_on="balance",
            is_taxable=True,
            include_active_employees=False,
            is_condition_based=False,
        ),
    )
    return [basic, ctc_hra, ctc_da, *flat_earnings, balance]


@transaction.atomic
def backfill_payroll_feature_coverage(today: date | None = None) -> dict[str, int]:
    """Ensure one Gross Up and one CTC Down SalaryStructure per company (each
    attached to a few real active contracts) and a FilingStatus assigned to a
    few contracts per company."""
    if not apps.is_installed("payroll"):
        return {
            "salary_structures": 0,
            "contracts_with_structure": 0,
            "contracts_with_filing_status": 0,
            "ctc_down_structures": 0,
            "ctc_down_contracts": 0,
            "contracts_to_calendar_days": 0,
        }

    from base.models import Company
    from employee.models import EmployeeWorkInformation
    from payroll.models.models import (
        Allowance,
        Contract,
        Deduction,
        FilingStatus,
        SalaryStructure,
    )

    allowances = list(
        Allowance._base_manager.filter(title__in=SALARY_STRUCTURE_ALLOWANCE_TITLES)
    )
    deductions = list(
        Deduction._base_manager.filter(title__in=SALARY_STRUCTURE_DEDUCTION_TITLES)
    )
    # Only the fixed one (Meal Allowance): the HRA in this list is
    # based_on="basic_pay", which reads 0 throughout a CTC Down pass -- see
    # create_payroll_fixtures.py's own note on why CTC Down restates HRA/DA
    # against the flagged component instead of reusing this set as-is.
    flat_earnings = [a for a in allowances if a.is_fixed]
    ctc_down_components = _get_or_create_ctc_down_components(flat_earnings)
    default_filing_status = FilingStatus._base_manager.order_by("id").first()

    company_ids = list(
        Company._base_manager.order_by("id").values_list("id", flat=True)
    )

    structures_created = 0
    contracts_with_structure = 0
    contracts_with_filing_status = 0
    ctc_down_structures_created = 0
    ctc_down_contracts = 0

    for company_id in company_ids:
        structure, created = SalaryStructure._base_manager.get_or_create(
            title="Standard Compensation Package",
            company_id_id=company_id,
            defaults={"structure_mode": "gross_up"},
        )
        if created:
            structures_created += 1
        if allowances:
            structure.allowances.add(*allowances)
        if deductions:
            structure.deductions.add(*deductions)

        company_contract_ids = list(
            Contract._base_manager.filter(
                contract_status="active",
                employee_id__in=EmployeeWorkInformation._base_manager.filter(
                    company_id=company_id
                ).values_list("employee_id", flat=True),
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        contract_ids = company_contract_ids[:CONTRACTS_PER_COMPANY]
        for contract in Contract._base_manager.filter(pk__in=contract_ids):
            if contract.salary_structure_id_id != structure.pk:
                contract.set_salary_structure(structure)
                contracts_with_structure += 1
            if default_filing_status and not contract.filing_status_id:
                Contract._base_manager.filter(pk=contract.pk).update(
                    filing_status_id=default_filing_status.pk
                )
                contracts_with_filing_status += 1

        # A separate, later slice of the same company's contracts -- not the
        # ones just given the Gross Up structure above, so each mode shows up
        # as itself rather than one overwriting the other.
        ctc_down_structure, ctc_created = SalaryStructure._base_manager.get_or_create(
            title="CTC Down Compensation Package",
            company_id_id=company_id,
            defaults={"structure_mode": "ctc_down"},
        )
        if ctc_created:
            ctc_down_structures_created += 1
        ctc_down_structure.allowances.add(*ctc_down_components)
        if deductions:
            ctc_down_structure.deductions.add(*deductions)

        ctc_contract_ids = company_contract_ids[
            CONTRACTS_PER_COMPANY : CONTRACTS_PER_COMPANY
            + CTC_DOWN_CONTRACTS_PER_COMPANY
        ]
        for contract in Contract._base_manager.filter(pk__in=ctc_contract_ids):
            if contract.salary_structure_id_id != ctc_down_structure.pk:
                contract.set_salary_structure(ctc_down_structure)
                # Monthly CTC stated instead of a wage -- resolve_basic_pay_
                # source reads contract.pay_rate, and a nonzero wage there
                # would double-count basic pay on top of the flagged
                # component, per create_payroll_fixtures.py's own note.
                Contract._base_manager.filter(pk=contract.pk).update(
                    monthly_ctc=round(
                        (contract.wage or 0) * CTC_DOWN_WAGE_TO_CTC_MULTIPLIER, 2
                    )
                    or 50000.0,
                    wage=0,
                )
                ctc_down_contracts += 1
            if default_filing_status and not contract.filing_status_id:
                Contract._base_manager.filter(pk=contract.pk).update(
                    filing_status_id=default_filing_status.pk
                )
                contracts_with_filing_status += 1

    # LOP priced against the whole month, not only its working days -- the
    # same "count the whole period" direction the payslip's own paid/LOP
    # day figures already moved to, on every demo contract still sitting at
    # the model's own default. One left deliberately otherwise (the
    # create_payroll_fixtures.py dev tool tests both divisors on purpose) is
    # not touched by this filter.
    contracts_to_calendar_days = Contract._base_manager.filter(
        daily_leave_amount_divisor="working_days"
    ).update(daily_leave_amount_divisor="calendar_days")

    logger.info(
        "Payroll feature backfill: %s structure(s), %s contract(s) attached, "
        "%s contract(s) given a filing status, %s CTC Down structure(s), "
        "%s CTC Down contract(s), %s contract(s) switched to calendar-day LOP",
        structures_created,
        contracts_with_structure,
        contracts_with_filing_status,
        ctc_down_structures_created,
        ctc_down_contracts,
        contracts_to_calendar_days,
    )
    return {
        "salary_structures": structures_created,
        "contracts_with_structure": contracts_with_structure,
        "contracts_with_filing_status": contracts_with_filing_status,
        "ctc_down_structures": ctc_down_structures_created,
        "ctc_down_contracts": ctc_down_contracts,
        "contracts_to_calendar_days": contracts_to_calendar_days,
    }
