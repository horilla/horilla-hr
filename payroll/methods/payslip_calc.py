"""
This module contains various functions for calculating payroll-related information for employees.
It includes functions for calculating gross pay, taxable gross pay, allowances, tax deductions,
pre-tax deductions, and post-tax deductions.

"""

import contextlib
import operator

from django.apps import apps

# from attendance.models import Attendance
from horilla.methods import get_horilla_model_class
from payroll.methods.component_engine import (
    EARNED,
    accumulate,
    component_applies_to,
    eligible_allowances,
    new_context,
    record,
    structure_components,
)
from payroll.methods.deductions import update_compensation_deduction
from payroll.methods.limits import compute_limit
from payroll.methods.proration import flat_amount
from payroll.models import models
from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    LoanAccount,
    MultipleCondition,
)


def return_none(a, b):
    return None


operator_mapping = {
    "equal": operator.eq,
    "notequal": operator.ne,
    "lt": operator.lt,
    "gt": operator.gt,
    "le": operator.le,
    "ge": operator.ge,
    "icontains": operator.contains,
    "range": return_none,
}
filter_mapping = {
    "work_type_id": {
        "filter": lambda employee, allowance, start_date, end_date: {
            "employee_id": employee,
            "work_type_id__id": allowance.work_type_id.id,
            "attendance_date__range": (start_date, end_date),
            "attendance_validated": True,
        }
    },
    "shift_id": {
        "filter": lambda employee, allowance, start_date, end_date: {
            "employee_id": employee,
            "shift_id__id": allowance.shift_id.id,
            "attendance_date__range": (start_date, end_date),
            "attendance_validated": True,
        }
    },
    "overtime": {
        "filter": lambda employee, allowance, start_date, end_date: {
            "employee_id": employee,
            "attendance_date__range": (start_date, end_date),
            "attendance_overtime_approve": True,
            "attendance_validated": True,
        }
    },
    "week_off_overtime": {
        "filter": lambda employee, allowance, start_date, end_date: {
            "employee_id": employee,
            "attendance_date__range": (start_date, end_date),
            "attendance_overtime_approve": True,
            "attendance_validated": True,
        }
    },
    "holiday_overtime": {
        "filter": lambda employee, allowance, start_date, end_date: {
            "employee_id": employee,
            "attendance_date__range": (start_date, end_date),
            "attendance_overtime_approve": True,
            "attendance_validated": True,
        }
    },
    "attendance": {
        "filter": lambda employee, allowance, start_date, end_date: {
            "employee_id": employee,
            "attendance_date__range": (start_date, end_date),
            "attendance_validated": True,
        }
    },
}


tets = {
    "net_pay": 35140.905000000006,
    "employee": 1,
    "allowances": [
        {
            "allowance_id": 5,
            "title": "Low Basic Pay Assistance",
            "is_taxable": True,
            "amount": 0,
        },
        {
            "allowance_id": 13,
            "title": "Bonus point Redeem for Adam Luis ",
            "is_taxable": True,
            "amount": 75.0,
        },
        {
            "allowance_id": 17,
            "title": "Motorcycle",
            "is_taxable": True,
            "amount": 5000.0,
        },
        {
            "allowance_id": 2,
            "title": "Meal Allowance",
            "is_taxable": False,
            "amount": 800.0,
        },
    ],
    "gross_pay": 39284.09090909091,
    "contract_wage": 35000.0,
    "basic_pay": 33409.09090909091,
    "paid_days": 21.0,
    "unpaid_days": 1.0,
    "taxable_gross_pay": {"taxable_gross_pay": 35848.47727272727},
    "basic_pay_deductions": [],
    "gross_pay_deductions": [],
    "pretax_deductions": [
        {
            "deduction_id": 1,
            "title": "Social Security (FICA)",
            "is_pretax": True,
            "amount": 2435.6136363636365,
            "employer_contribution_rate": 6.2,
        },
        {
            "deduction_id": 62,
            "title": "Late Come penalty",
            "is_pretax": True,
            "amount": 200.0,
            "employer_contribution_rate": 0.0,
        },
    ],
    "post_tax_deductions": [
        {
            "deduction_id": 2,
            "title": "Medicare tax",
            "is_pretax": False,
            "amount": 484.43181818181824,
            "employer_contribution_rate": 1.45,
        },
        {
            "deduction_id": 55,
            "title": "ESI",
            "is_pretax": False,
            "amount": 0,
            "employer_contribution_rate": 3.25,
        },
        {
            "deduction_id": 73,
            "title": "Test",
            "is_pretax": False,
            "amount": 0.0,
            "employer_contribution_rate": 0.0,
        },
    ],
    "tax_deductions": [
        {
            "deduction_id": 75,
            "title": "test tax netpay",
            "is_tax": True,
            "amount": 668.1818181818182,
            "employer_contribution_rate": 3.0,
        }
    ],
    "net_deductions": [
        {
            "deduction_id": 74,
            "title": "Test Netpay",
            "is_pretax": False,
            "amount": 354.9586363636364,
            "employer_contribution_rate": 2.0,
        }
    ],
    "total_deductions": 3788.227272727273,
    "loss_of_pay": 1590.909090909091,
    "federal_tax": 0,
    "start_date": "2024-02-01",
    "end_date": "2024-02-29",
    "range": "Feb 01 2024 - Feb 29 2024",
}


def dynamic_attr(obj, attribute_path):
    """
    Retrieves the value of a nested attribute from a related object dynamically.

    Args:
        obj: The base object from which to start accessing attributes.
        attribute_path (str): The path of the nested attribute to retrieve, using
        double underscores ('__') to indicate relationship traversal.

    Returns:
        The value of the nested attribute if it exists, or None if it doesn't exist.
    """
    attributes = attribute_path.split("__")

    for attr in attributes:
        with contextlib.suppress(Exception):
            if isinstance(obj.first(), Contract):
                obj = obj.filter(is_active=True).first()

        obj = getattr(obj, attr, None)
        if obj is None:
            break
    return obj


def calculate_gross_pay(*_args, **kwargs):
    """
    Calculate the gross pay for an employee within a given date range.

    Args:
        employee: The employee object for whom to calculate the gross pay.
        start_date: The start date of the period for which to calculate the gross pay.
        end_date: The end date of the period for which to calculate the gross pay.

    Returns:
        A dictionary containing the gross pay as the "gross_pay" key.

    """
    basic_pay = kwargs["basic_pay"]
    total_allowance = kwargs["total_allowance"]
    # basic_pay = compute_salary_on_period(employee, start_date, end_date)["basic_pay"]
    gross_pay = total_allowance + basic_pay

    employee, start_date, end_date = (
        kwargs[key] for key in ("employee", "start_date", "end_date")
    )

    updated_gross_pay_data = update_compensation_deduction(
        employee, gross_pay, "gross_pay", start_date, end_date
    )
    return {
        "gross_pay": updated_gross_pay_data["compensation_amount"],
        "basic_pay": basic_pay,
        "deductions": updated_gross_pay_data["deductions"],
    }


def calculate_taxable_gross_pay(*_args, **kwargs):
    """
    Calculate the taxable gross pay for an employee within a given date range.

    Args:
        employee: The employee object for whom to calculate the taxable gross pay.
        start_date: The start date of the period for which to calculate the taxable gross pay.
        end_date: The end date of the period for which to calculate the taxable gross pay.

    Returns:
        A dictionary containing the taxable gross pay as the "taxable_gross_pay" key.

    """
    allowances = kwargs["allowances"]
    gross_pay = calculate_gross_pay(**kwargs)
    gross_pay = gross_pay["gross_pay"]
    pre_tax_deductions = calculate_pre_tax_deduction(**kwargs)
    non_taxable_allowance_total = sum(
        allowance["amount"]
        for allowance in allowances["allowances"]
        if not allowance["is_taxable"]
    )
    pretax_deduction_total = sum(
        deduction["amount"]
        for deduction in pre_tax_deductions["pretax_deductions"]
        if deduction["is_pretax"]
    )
    # Loss of pay, when the contract deducts it separately instead of taking
    # it off basic pay. It is not a Deduction row -- the engine computes it --
    # so it was in neither total above, and the employee was taxed on pay they
    # did not receive. Whether it comes off here follows the "Loss of pay"
    # standard component's own pre-tax setting, which is the only thing that
    # setting controls.
    #
    # Zero when the contract takes it off basic pay: it is already out of
    # gross, and subtracting it again would take the same days off twice.
    loss_of_pay = float(kwargs.get("loss_of_pay_amount") or 0)
    loss_of_pay_total = 0.0
    if loss_of_pay:
        # Read from the contract, not from a component: loss of pay is never a
        # component row -- the engine works it out from attendance -- and the
        # rest of how it behaves (what a day is a share of, how many days it
        # is shared between, whether it comes off basic) is already decided
        # per contract. One place, not two.
        contract = (
            Contract.objects.filter(
                employee_id=kwargs.get("employee"), contract_status="active"
            ).first()
            if kwargs.get("employee")
            else None
        )
        if contract is None or contract.loss_of_pay_is_pretax:
            loss_of_pay_total = loss_of_pay

    # Taxable gross = taxable earnings - pre-tax deductions (- loss of pay when
    # it is a separate pre-tax deduction). Taxable earnings are gross less the
    # earnings that are not taxable. The payslip's tax panel and the edit form
    # lay it out in exactly these terms.
    taxable_earnings = gross_pay - non_taxable_allowance_total
    taxable_gross_pay = taxable_earnings - pretax_deduction_total - loss_of_pay_total
    # There is no such thing as negative taxable pay. Pre-tax deductions and
    # loss of pay together can come to more than was earned -- most of a month
    # unpaid against a part month worked -- and the raw subtraction then goes
    # below zero. Left negative it is fed straight to the tax brackets, shown
    # on the payslip as a negative "taxable gross", and summed into any report
    # that totals it. Nothing was earned to tax, so the answer is zero.
    return {
        "taxable_gross_pay": max(0.0, taxable_gross_pay),
    }


def calculate_allowance(**kwargs):
    """
    Calculate the allowances for an employee within the specified payroll period.

    Args:
        employee (Employee): The employee object for which to calculate the allowances.
        start_date (datetime.date): The start date of the payroll period.
        end_date (datetime.date): The end date of the payroll period.

    """
    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    basic_pay = kwargs["basic_pay"]
    day_dict = kwargs["day_dict"]
    # Ordered by (sequence, pk) so evaluation order is defined rather than
    # whatever the database returns for a union of three querysets. The
    # membership rules are unchanged; see component_engine.eligible_allowances.
    allowances = eligible_allowances(employee, start_date, end_date)

    # An earning marked as basic pay is skipped when the contract already
    # states a wage: basic is then already in basic_pay, and paying the earning
    # as well would put a second basic into gross. payroll_run decides which
    # source wins and passes the loser here — see basic_pay_source.py.
    skip = kwargs.get("skip_allowance")
    if skip is not None:
        allowances = allowances.exclude(pk=skip.pk)

    # Carried through the pass so a later component can be expressed in terms
    # of an earlier one. kwargs is what every strategy function receives, so
    # putting it there is what makes it reachable from them.
    context = kwargs.get("component_context")
    if context is None:
        context = new_context(basic_pay)
        kwargs["component_context"] = context

    employee_allowances = []
    tax_allowances = []
    no_tax_allowances = []
    tax_allowances_amt = []
    no_tax_allowances_amt = []
    # Append allowances based on condition, or unconditionally to employee
    for allowance in allowances:
        if allowance.is_condition_based:
            if component_applies_to(allowance, employee):
                employee_allowances.append(allowance)
        else:
            if allowance.based_on in filter_mapping:
                filter_params = filter_mapping[allowance.based_on]["filter"](
                    employee, allowance, start_date, end_date
                )
                if apps.is_installed("attendance"):
                    Attendance = get_horilla_model_class(
                        app_label="attendance", model="attendance"
                    )
                    if Attendance.objects.filter(**filter_params):
                        employee_allowances.append(allowance)
            else:
                employee_allowances.append(allowance)
    # One ordered pass. The amounts used to be computed in two separate loops
    # (taxable, then non-taxable) and only paired with their components
    # afterwards, which meant nothing was published until every amount already
    # existed — so a component could never see one computed earlier in the
    # same phase, only the seeded period figures. Recording as we go is what
    # makes "50% of DA" work at all.
    computed = []
    for allowance in employee_allowances:
        if allowance.is_fixed:
            amount = flat_amount(allowance, day_dict)
        else:
            calculation_function = calculation_mapping.get(allowance.based_on)
            amount = calculation_function(
                **{
                    "employee": employee,
                    "start_date": start_date,
                    "end_date": end_date,
                    "component": allowance,
                    "allowances": None,
                    "total_allowance": None,
                    "basic_pay": basic_pay,
                    "day_dict": day_dict,
                    # Forwarded so a component/formula strategy can see what
                    # earlier components computed.
                    "component_context": context,
                    # Only a CTC Down run supplies this; the balance earning
                    # takes the employer's contributions off the package.
                    "employer_deductions": kwargs.get("employer_deductions"),
                }
            )
        kwargs["amount"] = amount
        kwargs["component"] = allowance
        amount = if_condition_on(**kwargs)

        # Loss of pay comes off the earning that IS basic pay, before anything
        # reads it -- so a percentage of BASIC and a deduction based on basic pay
        # both see the adjusted figure. Never below zero.
        lop_cut = float(kwargs.get("basic_lop_reduction") or 0)
        if lop_cut and allowance.is_basic_pay and "_basic_lop" not in context:
            cut = min(float(amount or 0), lop_cut)
            amount = float(amount or 0) - cut
            context["_basic_lop"] = cut

        record(context, allowance, amount)
        accumulate(context, amount)
        computed.append((allowance, amount))

    # Taxable first, then non-taxable — the order the two-list implementation
    # produced and payslip templates render. Existing rows keep it through the
    # sequence backfill (taxable 100, non-taxable 200); new ones order by their
    # own sequence within each group.
    serialized_allowances = [
        {
            "allowance_id": allowance.id,
            "title": allowance.title,
            "is_taxable": allowance.is_taxable,
            "amount": amount,
        }
        for taxable in (True, False)
        for allowance, amount in computed
        if allowance.is_taxable is taxable
    ]
    return {"allowances": serialized_allowances}


def calculate_tax_deduction(*_args, **kwargs):
    """
    Calculates the tax deductions for the specified employee within the given date range.

    Args:
        employee (Employee): The employee for whom the tax deductions are being calculated.
        start_date (date): The start date of the tax deduction period.
        end_date (date): The end date of the tax deduction period.
        allowances (dict): Dictionary containing the calculated allowances.
        total_allowance (float): The total amount of allowances.
        basic_pay (float): The basic pay amount.
        day_dict (dict): Dictionary containing working day details.

    Returns:
        dict: A dictionary containing the serialized tax deductions.
    """
    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    specific_deductions = models.Deduction.objects.filter(
        specific_employees=employee, is_pretax=False, is_tax=True
    )
    active_employee_deduction = models.Deduction.objects.filter(
        include_active_employees=True, is_pretax=False, is_tax=True
    ).exclude(exclude_employees=employee)
    deductions = (
        specific_deductions
        | active_employee_deduction
        | structure_components(models.Deduction, employee).filter(
            is_pretax=False, is_tax=True
        )
    ).distinct()
    deductions = (
        deductions.exclude(one_time_date__lt=start_date)
        .exclude(one_time_date__gt=end_date)
        .exclude(update_compensation__isnull=False)
        # Templates say how their kind behaves; they are never deducted. See
        # payroll/system_components.py.
        .exclude(is_system=True)
    )
    deductions_amt = []
    serialized_deductions = []
    for deduction in deductions:
        # The is_fixed branch that calculate_pre_tax_deduction,
        # calculate_post_tax_deduction and calculate_allowance all have, and
        # this one was missing. Without it a fixed-amount tax deduction --
        # ``is_fixed`` defaults to True and ``based_on`` has no default at all
        # (null=True), so a flat Professional Tax is exactly this shape --
        # reached calculation_mapping.get(None), and every payslip run died
        # with "'NoneType' object is not callable".
        if deduction.is_fixed:
            amount = flat_amount(deduction, kwargs["day_dict"])
        else:
            calculation_function = calculation_mapping.get(deduction.based_on)
            amount = calculation_function(
                **{
                    "employee": employee,
                    "start_date": start_date,
                    "end_date": end_date,
                    "component": deduction,
                    "allowances": kwargs["allowances"],
                    "total_allowance": kwargs["total_allowance"],
                    "basic_pay": kwargs["basic_pay"],
                    "day_dict": kwargs["day_dict"],
                    "component_context": kwargs.get("component_context"),
                }
            )
        kwargs["amount"] = amount
        kwargs["component"] = deduction
        amount = if_condition_on(**kwargs)
        deductions_amt.append(amount)
    for deduction, amount in zip(deductions, deductions_amt):
        serialized_deduction = {
            "deduction_id": deduction.id,
            "title": deduction.title,
            "is_tax": deduction.is_tax,
            "amount": amount,
            "employer_contribution_rate": deduction.employer_rate,
        }
        serialized_deductions.append(serialized_deduction)
    return {"tax_deductions": serialized_deductions}


def calculate_pre_tax_deduction(*_args, **kwargs):
    """
    This function retrieves pre-tax deductions applicable to the employee and calculates
    their amounts

    Args:
        employee: The employee object for whom to calculate the pre-tax deductions.
        start_date: The start date of the period for which to calculate the pre-tax deductions.
        end_date: The end date of the period for which to calculate the pre-tax deductions.

    Returns:
        A dictionary containing the pre-tax deductions as the "pretax_deductions" key.

    """
    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]

    specific_deductions = models.Deduction.objects.filter(
        specific_employees=employee, is_pretax=True, is_tax=False
    )
    conditional_deduction = models.Deduction.objects.filter(
        is_condition_based=True, is_pretax=True, is_tax=False
    ).exclude(exclude_employees=employee)
    active_employee_deduction = models.Deduction.objects.filter(
        include_active_employees=True, is_pretax=True, is_tax=False
    ).exclude(exclude_employees=employee)

    deductions = (
        specific_deductions
        | conditional_deduction
        | active_employee_deduction
        | structure_components(models.Deduction, employee).filter(
            is_pretax=True, is_tax=False
        )
    ).distinct()
    deductions = (
        deductions.exclude(one_time_date__lt=start_date)
        .exclude(one_time_date__gt=end_date)
        .exclude(update_compensation__isnull=False)
        # Templates say how their kind behaves; they are never deducted. See
        # payroll/system_components.py.
        .exclude(is_system=True)
    )
    # Installment deductions
    installments = deductions.filter(is_installment=True)

    pre_tax_deductions = []
    pre_tax_deductions_amt = []
    serialized_deductions = []

    for deduction in deductions:
        if deduction.is_condition_based:
            if component_applies_to(deduction, employee):
                pre_tax_deductions.append(deduction)
        else:
            pre_tax_deductions.append(deduction)

    for deduction in pre_tax_deductions:
        if deduction.is_fixed:
            kwargs["amount"] = flat_amount(deduction, kwargs["day_dict"])
            kwargs["component"] = deduction
            pre_tax_deductions_amt.append(if_condition_on(**kwargs))
        else:
            calculation_function = calculation_mapping.get(deduction.based_on)
            amount = calculation_function(
                **{
                    "employee": employee,
                    "start_date": start_date,
                    "end_date": end_date,
                    "component": deduction,
                    "allowances": kwargs["allowances"],
                    "total_allowance": kwargs["total_allowance"],
                    "basic_pay": kwargs["basic_pay"],
                    "day_dict": kwargs["day_dict"],
                    "component_context": kwargs.get("component_context"),
                }
            )
            kwargs["amount"] = amount
            kwargs["component"] = deduction
            pre_tax_deductions_amt.append(if_condition_on(**kwargs))
    for deduction, amount in zip(pre_tax_deductions, pre_tax_deductions_amt):
        serialized_deduction = {
            "deduction_id": deduction.id,
            "title": deduction.title,
            "is_pretax": deduction.is_pretax,
            "amount": amount,
            "employer_contribution_rate": deduction.employer_rate,
        }
        serialized_deductions.append(serialized_deduction)
    return {"pretax_deductions": serialized_deductions, "installments": installments}


def calculate_post_tax_deduction(*_args, **kwargs):
    """
    This function retrieves post-tax deductions applicable to the employee and calculates
    their amounts

    Args:
        employee: The employee object for whom to calculate the pre-tax deductions.
        start_date: The start date of the period for which to calculate the pre-tax deductions.
        end_date: The end date of the period for which to calculate the pre-tax deductions.

    Returns:
        A dictionary containing the pre-tax deductions as the "post_tax_deductions" key.

    """
    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    allowances = kwargs["allowances"]
    total_allowance = kwargs["total_allowance"]
    basic_pay = kwargs["basic_pay"]
    day_dict = kwargs["day_dict"]
    specific_deductions = models.Deduction.objects.filter(
        specific_employees=employee, is_pretax=False, is_tax=False
    )
    conditional_deduction = models.Deduction.objects.filter(
        is_condition_based=True, is_pretax=False, is_tax=False
    ).exclude(exclude_employees=employee)
    active_employee_deduction = models.Deduction.objects.filter(
        include_active_employees=True, is_pretax=False, is_tax=False
    ).exclude(exclude_employees=employee)
    # .distinct(): see calculate_pre_tax_deduction's identical fan-out note.
    deductions = (
        specific_deductions
        | conditional_deduction
        | active_employee_deduction
        | structure_components(models.Deduction, employee).filter(
            is_pretax=False, is_tax=False
        )
    ).distinct()
    deductions = (
        deductions.exclude(one_time_date__lt=start_date)
        .exclude(one_time_date__gt=end_date)
        .exclude(update_compensation__isnull=False)
        # Templates say how their kind behaves; they are never deducted. See
        # payroll/system_components.py.
        .exclude(is_system=True)
    )
    # Installment deductions
    installments = deductions.filter(is_installment=True)

    post_tax_deductions = []
    post_tax_deductions_amt = []
    serialized_deductions = []
    serialized_net_pay_deductions = []

    for deduction in deductions:
        if deduction.is_condition_based:
            # This copy previously ignored other_conditions entirely, so a
            # deduction with extra conditions applied on the strength of its
            # first one alone.
            if component_applies_to(deduction, employee):
                post_tax_deductions.append(deduction)
        else:
            post_tax_deductions.append(deduction)
    # Each deduction belongs to exactly one phase, and its amount is produced
    # in the same step that records it.
    #
    # It used to append the component to one list and the amount to another,
    # then re-pair them with zip() -- which only holds while both are appended
    # in lockstep, and a net_pay-based deduction appended a component and no
    # amount. With one sitting before two others, the payslip recorded the
    # second deduction's amount against the first, the third's against the
    # second, and dropped the third entirely; the net_pay one was then charged
    # a second time by the net-pay phase, which also emitted it. Misattributed,
    # short by one line, and double-counted at once.
    for deduction in post_tax_deductions:
        # A percentage of net pay cannot be computed until net pay exists, so
        # it belongs solely to the net-pay phase. is_fixed wins over based_on:
        # a fixed amount is a fixed amount whatever the field says, and is an
        # ordinary post-tax line.
        if not deduction.is_fixed and deduction.based_on == "net_pay":
            serialized_net_pay_deductions.append({"deduction": deduction})
            continue

        if deduction.is_fixed:
            amount = flat_amount(deduction, day_dict)
        else:
            calculation_function = calculation_mapping.get(deduction.based_on)
            amount = calculation_function(
                **{
                    "employee": employee,
                    "start_date": start_date,
                    "end_date": end_date,
                    "component": deduction,
                    "allowances": allowances,
                    "total_allowance": total_allowance,
                    "basic_pay": basic_pay,
                    "day_dict": day_dict,
                    # Forwarded so a component/formula strategy can see what
                    # earlier components computed.
                    "component_context": kwargs.get("component_context"),
                }
            )
        kwargs["amount"] = amount
        kwargs["component"] = deduction
        amount = if_condition_on(**kwargs)

        record(kwargs.get("component_context") or {}, deduction, amount)
        serialized_deductions.append(
            {
                "deduction_id": deduction.id,
                "title": deduction.title,
                "is_pretax": deduction.is_pretax,
                "amount": amount,
                "employer_contribution_rate": deduction.employer_rate,
            }
        )
    return {
        "post_tax_deductions": serialized_deductions,
        "net_pay_deduction": serialized_net_pay_deductions,
        "installments": installments,
    }


def calculate_net_pay_deduction(net_pay, net_pay_deductions, **kwargs):
    """
    Calculates the deductions based on the net pay amount.

    Args:
        net_pay (float): The net pay amount.
        net_pay_deductions (list): List of net pay deductions.
        day_dict (dict): Dictionary containing working day details.

    Returns:
        dict: A dictionary containing the serialized deductions and deduction amount.
    """
    day_dict = kwargs["day_dict"]
    serialized_net_pay_deductions = []
    deductions = [item["deduction"] for item in net_pay_deductions]
    deduction_amt = []
    for deduction in deductions:
        amount = calculate_based_on_net_pay(deduction, net_pay, day_dict)
        kwargs["amount"] = amount
        kwargs["component"] = deduction
        amount = if_condition_on(**kwargs)
        deduction_amt.append(amount)
    net_deduction = 0
    for deduction, amount in zip(deductions, deduction_amt):
        serialized_deduction = {
            "deduction_id": deduction.id,
            "title": deduction.title,
            "is_pretax": deduction.is_pretax,
            "amount": amount,
            "employer_contribution_rate": deduction.employer_rate,
        }
        net_deduction = amount + net_deduction
        serialized_net_pay_deductions.append(serialized_deduction)
    return {
        "net_pay_deductions": serialized_net_pay_deductions,
        "net_deduction": net_deduction,
    }


def if_condition_on(*_args, **kwargs):
    """
    This method is used to check the allowance or deduction through the the conditions

    Args:
        employee (obj): Employee instance
        amount (float): calculated amount of the component
        component (obj): Allowance or Deduction instance
        start_date (obj): Start date of the period
        end_date (obj): End date of the period

    Returns:
        _type_: _description_
    """
    component = kwargs["component"]
    amount = float(kwargs["amount"])

    measure = _apply_measures(component, kwargs)

    # The rule on the component itself, then any extra rows. All of them have
    # to hold: a component with two conditions is being narrowed by both, not
    # offered two ways to qualify.
    #
    # With one exception. Every component carries a default "basic pay > 0"
    # rule, which asks whether the employee is being paid at all — but the
    # earning that DEFINES basic pay cannot be asked that. It only runs when
    # the contract states no wage, so basic is 0 at that moment by definition,
    # and the gate would zero the very component that was about to set it.
    # Any rule someone actually configured still applies.
    rules = []
    if not (getattr(component, "is_basic_pay", False) and _is_default_gate(component)):
        rules.append(component)
    rules.extend(_extra_apply_conditions(component))
    for rule in rules:
        if not _apply_rule_holds(rule, measure):
            return 0
    return amount


def _is_default_gate(component):
    """
    Whether the component's own rule is the untouched default, rather than
    something a person chose. "basic pay > 0" is what every component starts
    with.
    """
    return (
        (getattr(component, "if_choice", "") or "") == "basic_pay"
        and (getattr(component, "if_condition", "") or "") == "gt"
        and (getattr(component, "if_amount", None) in (0, 0.0, None))
    )


def _extra_apply_conditions(component):
    """The extra rows, or nothing on a component that predates them."""
    related = getattr(component, "apply_conditions", None)
    if related is None or not getattr(component, "pk", None):
        return []
    return related.all()


def _apply_measures(component, kwargs):
    """
    What each "when it applies" choice is measured against, for this component.

    Returns a callable so nothing is computed that no rule asks for — gross is
    a full pass over the components, and the default rule on every component
    only ever looks at basic pay.
    """
    context = kwargs.get("component_context") or {}
    basic_pay = kwargs["basic_pay"]
    cache = {}

    def gross():
        # An allowance is part of gross, so gross does not exist yet while one
        # is being worked out. In a CTC Down structure the wage IS the gross and
        # is known up front, which the context carries; in a Gross Up structure
        # there is no answer to give and the rule cannot be offered.
        if isinstance(component, Allowance):
            return float(context.get("GROSS") or 0)
        return calculate_gross_pay(**kwargs)["gross_pay"]

    def taxable_gross():
        if isinstance(component, Allowance):
            return float(context.get("GROSS") or 0)
        return calculate_taxable_gross_pay(**kwargs)["taxable_gross_pay"]

    sources = {
        # Every component carries a hidden "basic pay > 0" rule by default,
        # which is really asking "is this employee being paid this period". In
        # a CTC Down run basic is derived FROM the components, so it is still 0
        # while they are being computed and the rule would zero every one of
        # them. Fall back to the basic computed so far, then to the CTC the
        # structure started from.
        "basic_pay": lambda: (
            basic_pay
            or float(context.get("BASIC") or 0)
            or float(context.get("CTC") or 0)
        ),
        "ctc": lambda: float(context.get("CTC") or 0),
        "gross_pay": gross,
        "taxable_gross_pay": taxable_gross,
    }

    def measure(choice, code=""):
        if choice == "component":
            return float(context.get((code or "").strip().upper(), 0) or 0)
        if choice not in cache:
            cache[choice] = float(sources.get(choice, sources["basic_pay"])() or 0)
        return cache[choice]

    return measure


def _apply_rule_holds(rule, measure):
    """
    One comparison. `rule` is either the component itself, whose rule lives in
    if_choice / if_condition / if_amount, or an ApplyCondition row.
    """
    choice = getattr(rule, "if_choice", None) or getattr(rule, "choice", "basic_pay")
    condition = getattr(rule, "if_condition", None) or getattr(rule, "condition", "gt")
    code = getattr(rule, "if_component_code", "") or getattr(rule, "component_code", "")
    value = measure(choice, code)

    if condition == "range":
        start = rule.start_range
        end = rule.end_range
        if start is None or end is None:
            return True
        return start <= value <= end

    target = getattr(rule, "if_amount", None)
    if target is None:
        target = getattr(rule, "amount", 0)
    operator_func = operator_mapping.get(condition)
    if operator_func is None:
        return True
    return bool(operator_func(value, target or 0))


def calculate_based_on_basic_pay(*_args, **kwargs):
    """
    Calculate the amount of an allowance or deduction based on the employee's
    basic pay with rate provided in the allowance or deduction object

    Args:
        employee (Employee): The employee object for whom to calculate the amount.
        start_date (datetime.date): The start date of the period for which to calculate the amount.
        end_date (datetime.date): The end date of the period for which to calculate the amount.
        component (Component): The allowance or deduction object that defines the rate or percentage
        to apply.

    Returns:
        The calculated allowance or deduction amount based on the employee's basic pay.

    """
    component = kwargs["component"]
    basic_pay = kwargs["basic_pay"]
    day_dict = kwargs["day_dict"]
    rate = component.rate
    # Under CTC Down basic_pay is 0; the basic is the structure's flagged component.
    if not basic_pay:
        basic_pay = float((kwargs.get("component_context") or {}).get("BASIC") or 0)
    amount = basic_pay * rate / 100
    amount = compute_limit(component, amount, day_dict)

    return amount


def calculate_based_on_gross_pay(*_args, **kwargs):
    """
    Calculate the amount of an allowance or deduction based on the employee's gross pay with rate
    provided in the allowance or deduction object

    Args:
        employee (Employee): The employee object for whom to calculate the amount.
        start_date (datetime.date): The start date of the period for which to calculate the amount.
        end_date (datetime.date): The end date of the period for which to calculate the amount.
        component (Component): The allowance or deduction object that defines the rate or percentage
        to apply.

    Returns:+-
        The calculated allowance or deduction amount based on the employee's gross pay.

    """

    component = kwargs["component"]
    day_dict = kwargs["day_dict"]
    gross_pay = calculate_gross_pay(**kwargs)
    rate = component.rate
    amount = gross_pay["gross_pay"] * rate / 100
    amount = compute_limit(component, amount, day_dict)
    return amount


def calculate_based_on_taxable_gross_pay(*_args, **kwargs):
    """
    Calculate the amount of an allowance or deduction based on the employee's taxable gross pay with
    rate provided in the allowance or deduction object

    Args:
        employee (Employee): The employee object for whom to calculate the amount.
        start_date (datetime.date): The start date of the period for which to calculate the amount.
        end_date (datetime.date): The end date of the period for which to calculate the amount.
        component (Component): The allowance or deduction object that defines the rate or percentage
        to apply.

    Returns:
        The calculated component amount based on the employee's taxable gross pay.

    """
    component = kwargs["component"]
    day_dict = kwargs["day_dict"]
    taxable_gross_pay = calculate_taxable_gross_pay(**kwargs)
    taxable_gross_pay = taxable_gross_pay["taxable_gross_pay"]
    rate = component.rate
    amount = taxable_gross_pay * rate / 100
    amount = compute_limit(component, amount, day_dict)
    return amount


def calculate_based_on_net_pay(component, net_pay, day_dict):
    """
    Calculates the amount of an allowance or deduction based on the net pay of an employee.

    Args:
        component (Allowance or Deduction): The allowance or deduction object.
        net_pay (float): The net pay of the employee.
        day_dict (dict): Dictionary containing working day details.

    Returns:
        float: The calculated amount of the component based on the net pay.
    """
    rate = float(component.rate)
    amount = net_pay * rate / 100
    amount = compute_limit(component, amount, day_dict)
    return amount


def calculate_based_on_attendance(*_args, **kwargs):
    """
    Calculates the amount of an allowance or deduction based on the attendance of an employee.

    Args:
        employee (Employee): The employee for whom the attendance is being calculated.
        start_date (date): The start date of the attendance period.
        end_date (date): The end date of the attendance period.
        component (Allowance or Deduction): The allowance or deduction object.
        day_dict (dict): Dictionary containing working day details.

    Returns:
        float: The calculated amount of the component based on the attendance.
    """

    if not apps.is_installed("attendance"):
        return 0

    Attendance = get_horilla_model_class(app_label="attendance", model="attendance")
    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    component = kwargs["component"]
    day_dict = kwargs["day_dict"]

    count = Attendance.objects.filter(
        employee_id=employee,
        attendance_date__range=(start_date, end_date),
        attendance_validated=True,
    ).count()
    amount = count * component.per_attendance_fixed_amount
    amount = compute_limit(component, amount, day_dict)
    return amount


def calculate_based_on_shift(*_args, **kwargs):
    """
    Calculates the amount of an allowance or deduction based on the employee's shift attendance.

    Args:
        employee (Employee): The employee for whom the shift attendance is being calculated.
        start_date (date): The start date of the attendance period.
        end_date (date): The end date of the attendance period.
        component (Allowance or Deduction): The allowance or deduction object.
        day_dict (dict): Dictionary containing working day details.

    Returns:
        float: The calculated amount of the component based on the shift attendance.
    """
    if not apps.is_installed("attendance"):
        return 0

    Attendance = get_horilla_model_class(app_label="attendance", model="attendance")
    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    component = kwargs["component"]
    day_dict = kwargs["day_dict"]

    shift_id = component.shift_id.id
    count = Attendance.objects.filter(
        employee_id=employee,
        shift_id=shift_id,
        attendance_date__range=(start_date, end_date),
        attendance_validated=True,
    ).count()
    amount = count * component.shift_per_attendance_amount

    amount = compute_limit(component, amount, day_dict)
    return amount


def _classify_approved_overtime_seconds(employee, start_date, end_date):
    """
    Splits APPROVED overtime attendance in the period into three mutually
    exclusive buckets, so "Regular Overtime", "Week Off Overtime", and
    "Holiday Overtime" allowances never double-pay the same hours:
      - regular:  overtime_second on a normal scheduled working day
      - week_off: at_work_second on a week-off day (entirely overtime)
      - holiday:  at_work_second on a holiday (entirely overtime)

    A holiday/week-off day HR has regularized away from that classification
    (Full Present/Half Day via AttendanceConflictResolution) is treated as
    a normal working day here too — matching build_monthly_summary's same
    rule, so the payslip's overtime allowance stays consistent with what
    the monthly attendance summary displays for that day.
    """
    if not apps.is_installed("attendance"):
        return 0, 0, 0

    from attendance.models import AttendanceConflictResolution
    from base.methods import get_holiday_dates, get_working_days

    Attendance = get_horilla_model_class(app_label="attendance", model="attendance")
    working_day_dates = set(
        get_working_days(start_date, end_date, employee)["working_days_on"]
    )
    holiday_dates = set(get_holiday_dates(start_date, end_date, employee))
    regularized_dates = set(
        AttendanceConflictResolution.objects.filter(
            employee_id=employee,
            date__range=(start_date, end_date),
            resolution__in=("full_present", "half_present"),
        ).values_list("date", flat=True)
    )

    attendances = Attendance.objects.filter(
        employee_id=employee,
        attendance_date__range=(start_date, end_date),
        attendance_overtime_approve=True,
    )
    regular_ot = week_off_ot = holiday_ot = 0
    for attendance in attendances:
        att_date = attendance.attendance_date
        if att_date in working_day_dates or att_date in regularized_dates:
            regular_ot += attendance.overtime_second or 0
        elif att_date in holiday_dates:
            holiday_ot += attendance.at_work_second or 0
        else:
            week_off_ot += attendance.at_work_second or 0
    return regular_ot, week_off_ot, holiday_ot


def _amount_from_seconds(seconds, component, day_dict):
    amount_per_second = component.amount_per_one_hr / (60 * 60)
    amount = round(seconds * amount_per_second, 2)
    return compute_limit(component, amount, day_dict)


def calculate_based_on_overtime(*_args, **kwargs):
    """
    Calculates the amount of an allowance or deduction based on employee's
    REGULAR overtime hours — overtime worked on a normal scheduled working
    day only. Week-off and holiday overtime are paid via the dedicated
    "week_off_overtime" / "holiday_overtime" allowance types instead, so
    they don't get double-counted here.

    Args:
        employee (Employee): The employee for whom the overtime is being calculated.
        start_date (date): The start date of the overtime period.
        end_date (date): The end date of the overtime period.
        component (Allowance or Deduction): The allowance or deduction object.
        day_dict (dict): Dictionary containing working day details.

    Returns:
        float: The calculated amount of the allowance or deduction based on the overtime hours.
    """
    if not apps.is_installed("attendance"):
        return 0

    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    component = kwargs["component"]
    day_dict = kwargs["day_dict"]

    regular_ot, _week_off_ot, _holiday_ot = _classify_approved_overtime_seconds(
        employee, start_date, end_date
    )
    return _amount_from_seconds(regular_ot, component, day_dict)


def calculate_based_on_week_off_overtime(*_args, **kwargs):
    """
    Calculates the allowance/deduction amount for approved overtime worked
    on week-off days (entirely overtime, since week-off days have no
    scheduled hours), at the component's configured hourly rate.
    """
    if not apps.is_installed("attendance"):
        return 0

    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    component = kwargs["component"]
    day_dict = kwargs["day_dict"]

    _regular_ot, week_off_ot, _holiday_ot = _classify_approved_overtime_seconds(
        employee, start_date, end_date
    )
    return _amount_from_seconds(week_off_ot, component, day_dict)


def calculate_based_on_holiday_overtime(*_args, **kwargs):
    """
    Calculates the allowance/deduction amount for approved overtime worked
    on holidays (entirely overtime, since holidays have no scheduled
    hours), at the component's configured hourly rate.
    """
    if not apps.is_installed("attendance"):
        return 0

    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    component = kwargs["component"]
    day_dict = kwargs["day_dict"]

    _regular_ot, _week_off_ot, holiday_ot = _classify_approved_overtime_seconds(
        employee, start_date, end_date
    )
    return _amount_from_seconds(holiday_ot, component, day_dict)


def calculate_based_on_work_type(*_args, **kwargs):
    """
    Calculates the amount of an allowance or deduction based on the employee's
    attendance with a specific work type.

    Args:
        employee (Employee): The employee for whom the attendance is being considered.
        start_date (date): The start date of the attendance period.
        end_date (date): The end date of the attendance period.
        component (Allowance or Deduction): The allowance or deduction object.
        day_dict (dict): Dictionary containing working day details.

    Returns:
        float: The calculated amount of the allowance or deduction based on the
               attendance with the specified work type.
    """
    if not apps.is_installed("attendance"):
        return 0

    Attendance = get_horilla_model_class(app_label="attendance", model="attendance")
    employee = kwargs["employee"]
    start_date = kwargs["start_date"]
    end_date = kwargs["end_date"]
    component = kwargs["component"]
    day_dict = kwargs["day_dict"]

    work_type_id = component.work_type_id.id
    count = Attendance.objects.filter(
        employee_id=employee,
        work_type_id=work_type_id,
        attendance_date__range=(start_date, end_date),
        attendance_validated=True,
    ).count()
    amount = count * component.work_type_per_attendance_amount

    amount = compute_limit(component, amount, day_dict)

    return amount


def calculate_based_on_children(*_args, **kwargs):
    """
    Calculates the amount of an allowance or deduction based on the attendance of an employee.

    Args:
        employee (Employee): The employee for whom the attendance is being calculated.
        start_date (date): The start date of the attendance period.
        end_date (date): The end date of the attendance period.
        component (Allowance or Deduction): The allowance or deduction object.
        day_dict (dict): Dictionary containing working day details.

    Returns:
        float: The calculated amount of the component based on the attendance.
    """
    employee = kwargs["employee"]
    component = kwargs["component"]
    day_dict = kwargs["day_dict"]
    count = employee.children
    amount = count * component.per_children_fixed_amount
    amount = compute_limit(component, amount, day_dict)
    return amount


def calculate_based_on_balance(*_args, **kwargs):
    """
    Whatever is left of CTC after every earning that ran before this one.

    This is what makes a CTC Down structure add up: the employer states a total
    cost, named components take their defined shares, and this absorbs the
    remainder so the parts sum exactly to the whole rather than to whatever the
    percentages happen to total.

    It must be the last earning in the order — it can only see what has already
    run — and it never goes negative: if the named components already exceed
    CTC, this contributes nothing rather than paying the difference back.

    CTC is the whole cost to the employer, so what is left means after the
    employer's own contributions too (Deduction.employer_rate / formula), not
    only after the earnings. Without that the package always overshot by the
    employer's share: gross came to exactly CTC and the contributions went on
    top. They are taken off here, through payroll.methods.employer_cost, when
    the caller supplies the deductions that apply.
    """
    from payroll.methods.employer_cost import balance_after_employer_cost

    component = kwargs["component"]
    day_dict = kwargs["day_dict"]
    context = kwargs.get("component_context") or {}

    employer_deductions = kwargs.get("employer_deductions")
    if employer_deductions is None:
        remaining = (
            float(context.get("CTC", 0) or 0)
            - float(context.get("_basic_lop", 0) or 0)
            - float(context.get(EARNED, 0) or 0)
        )
    else:
        remaining = balance_after_employer_cost(employer_deductions, context)
    return compute_limit(component, max(remaining, 0.0), day_dict)


def calculate_based_on_component(*_args, **kwargs):
    """
    A percentage of another component's already-computed amount.

    This is what "HRA = 50% of BASIC" needs and what the legacy strategies
    could not express: every one of them was hardwired to a fixed aggregate
    (basic pay for an allowance; basic/gross/taxable/net for a deduction), so
    one component could never be stated in terms of another.

    The target must have run earlier in the pass. An unknown or not-yet-run
    code contributes 0 rather than raising — the same choice the formula
    evaluator makes, for the same reason: a component referring to something
    absent from this employee's structure should add nothing, not abort their
    payslip.
    """
    component = kwargs["component"]
    day_dict = kwargs["day_dict"]
    context = kwargs.get("component_context") or {}

    target = (component.percentage_of_code or "").strip().upper()
    base = float(context.get(target, 0) or 0)
    amount = base * (component.rate or 0) / 100
    return compute_limit(component, amount, day_dict)


def calculate_based_on_formula(*_args, **kwargs):
    """
    An arithmetic expression over the components that ran before this one.

    A broken formula raises through to payroll_calculation, which reports it
    against this component and refuses the payslip — the same stance the tax
    formula takes. Silently contributing 0 is what made the old tax path pay
    people the wrong amount without saying so.
    """
    from payroll.methods.component_formula import run_component_formula

    component = kwargs["component"]
    day_dict = kwargs["day_dict"]
    context = kwargs.get("component_context") or {}

    amount = run_component_formula(component.formula, context)
    return compute_limit(component, amount, day_dict)


calculation_mapping = {
    "basic_pay": calculate_based_on_basic_pay,
    "gross_pay": calculate_based_on_gross_pay,
    "taxable_gross_pay": calculate_based_on_taxable_gross_pay,
    "net_pay": calculate_based_on_net_pay,
    "attendance": calculate_based_on_attendance,
    "shift_id": calculate_based_on_shift,
    "overtime": calculate_based_on_overtime,
    "week_off_overtime": calculate_based_on_week_off_overtime,
    "holiday_overtime": calculate_based_on_holiday_overtime,
    "work_type_id": calculate_based_on_work_type,
    "children": calculate_based_on_children,
    "component": calculate_based_on_component,
    "formula": calculate_based_on_formula,
    "balance": calculate_based_on_balance,
}
