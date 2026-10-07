"""
payroll/methods/payroll_run.py

The payslip computation entry point.

``payroll_calculation()`` used to live in ``payroll/views/component_views.py``,
which meant every caller — the scheduler, the CBV, the demo-data generator and
any test — had to import a 2900-line view module (and through it pandas,
openpyxl and the whole notification stack) just to compute a payslip. It is not
a view and never was; this module is its home.

Behaviour here is deliberately identical to the version that lived in the view
module. Callers keep working through the re-export left behind in
``component_views``.
"""

import json
import logging

from django.apps import apps

from horilla.methods import get_horilla_model_class
from payroll.methods.basic_pay_source import COMPONENT as BASIC_FROM_COMPONENT
from payroll.methods.basic_pay_source import CONTRACT as BASIC_FROM_CONTRACT
from payroll.methods.basic_pay_source import NEITHER as BASIC_FROM_NEITHER
from payroll.methods.basic_pay_source import resolve_basic_pay_source
from payroll.methods.component_engine import (
    add_service_years,
    eligible_allowances,
    new_context,
)
from payroll.methods.deductions import update_compensation_deduction
from payroll.methods.methods import compute_net_pay, compute_salary_on_period
from payroll.methods.payslip_calc import (
    calculate_allowance,
    calculate_gross_pay,
    calculate_net_pay_deduction,
    calculate_post_tax_deduction,
    calculate_pre_tax_deduction,
    calculate_tax_deduction,
    calculate_taxable_gross_pay,
)
from payroll.methods.tax_calc import calculate_taxable_amount


def get_pending_attendance(employee, start_date, end_date):
    """
    Attendance records in the payslip period that still need validation
    and/or overtime approval — surfaced on the payslip so HR can act on
    them without leaving the page. Unvalidated attendance doesn't count
    toward pay (see get_attendance() in payroll/methods/methods.py).
    """
    if not apps.is_installed("attendance"):
        return []
    Attendance = get_horilla_model_class(app_label="attendance", model="attendance")
    records = Attendance.objects.filter(
        employee_id=employee,
        attendance_date__range=(start_date, end_date),
    ).order_by("attendance_date")

    pending = []
    for att in records:
        needs_validation = not att.attendance_validated
        needs_ot_approval = (
            bool(att.overtime_second) and not att.attendance_overtime_approve
        )
        if not needs_validation and not needs_ot_approval:
            continue
        worked = att.at_work_second or 0
        overtime = att.overtime_second or 0
        pending.append(
            {
                "id": att.id,
                "date_label": att.attendance_date.strftime("%d %b %Y"),
                "worked_label": f"{worked // 3600}h {(worked % 3600) // 60:02d}m",
                "overtime_label": f"{overtime // 3600}h {(overtime % 3600) // 60:02d}m",
                "needs_validation": needs_validation,
                "needs_ot_approval": needs_ot_approval,
            }
        )
    return pending


logger = logging.getLogger(__name__)


class StructureConfigurationError(Exception):
    """
    A salary structure that cannot produce a coherent payslip.

    Raised rather than returned so a caller generating a batch cannot mistake it
    for a valid result. payroll_calculation's callers already handle a
    per-employee failure this way for tax (TaxComputationError).
    """


def payroll_calculation(employee, start_date, end_date, month_summary=None):
    """
    Calculate payroll components for the specified employee within the given date range.


    Args:
        employee (Employee): The employee for whom the payroll is calculated.
        start_date (date): The start date of the payroll period.
        end_date (date): The end date of the payroll period.


    Returns:
        dict: A dictionary containing the calculated payroll components:
    """
    basic_pay_details = compute_salary_on_period(
        employee, start_date, end_date, month_summary=month_summary
    )

    if not basic_pay_details:
        return None
    contract = basic_pay_details["contract"]
    contract_wage = basic_pay_details["contract_wage"]
    basic_pay = basic_pay_details["basic_pay"]
    loss_of_pay = basic_pay_details["loss_of_pay"]
    custom_leave_deduction = basic_pay_details.get("custom_leave_deduction", 0.0)
    custom_leave_breakdown = basic_pay_details.get("custom_leave_breakdown", [])
    paid_days = basic_pay_details["paid_days"]
    unpaid_days = basic_pay_details["unpaid_days"]
    partial_pay_days = basic_pay_details.get("partial_pay_days", 0)
    # The actual numbers get_daily_salary divided, not just which contract
    # settings chose them -- absent from the hourly/daily branches, which
    # price a day of leave differently and never call it.
    lop_base_amount = basic_pay_details.get("lop_base_amount")
    lop_divisor_days = basic_pay_details.get("lop_divisor_days")
    lop_daily_rate = basic_pay_details.get("lop_daily_rate")

    def _secs_to_label(secs):
        secs = int(secs or 0)
        return f"{secs // 3600}h {(secs % 3600) // 60:02d}m"

    regular_seconds = basic_pay_details.get("regular_seconds")
    ot_seconds = basic_pay_details.get("ot_seconds")
    regular_hours_label = (
        _secs_to_label(regular_seconds) if regular_seconds is not None else None
    )
    ot_hours_label = _secs_to_label(ot_seconds) if ot_seconds is not None else None

    ot_regular_seconds = basic_pay_details.get("ot_regular_seconds", 0)
    ot_week_off_seconds = basic_pay_details.get("ot_week_off_seconds", 0)
    ot_holiday_seconds = basic_pay_details.get("ot_holiday_seconds", 0)
    ot_regular_hours_label = (
        _secs_to_label(ot_regular_seconds) if ot_regular_seconds else None
    )
    ot_week_off_hours_label = (
        _secs_to_label(ot_week_off_seconds) if ot_week_off_seconds else None
    )
    ot_holiday_hours_label = (
        _secs_to_label(ot_holiday_seconds) if ot_holiday_seconds else None
    )

    pending_attendance = get_pending_attendance(employee, start_date, end_date)

    working_days_details = basic_pay_details["month_data"]

    # How many working days the period held, which is the denominator behind
    # paid days and loss-of-pay days. Without it those two are counts with
    # nothing to be counts OF: "21 loss of pay days" reads very differently
    # against 22 working days than against 30. Summed across the months a
    # period spans, the same way the engine's own proration reads them.
    total_working_days = sum(
        month.get("working_days_on_period", 0) or 0
        for month in (working_days_details or [])
    )

    updated_basic_pay_data = update_compensation_deduction(
        employee, basic_pay, "basic_pay", start_date, end_date
    )
    basic_pay = updated_basic_pay_data["compensation_amount"]
    basic_pay_deductions = updated_basic_pay_data["deductions"]

    loss_of_pay_amount = 0
    if not contract.deduct_leave_from_basic_pay:
        loss_of_pay_amount = loss_of_pay
    else:
        basic_pay = basic_pay - loss_of_pay_amount

    # One evaluation context for the whole run, owned here rather than by any
    # one phase. Each component publishes its amount into it by code, so a
    # later component — in this phase or a subsequent one — can be expressed in
    # terms of an earlier one. Created here because a gatherer receives kwargs
    # unpacked into a fresh dict, so a context it created itself would never
    # reach the phases that follow it.
    # What the contract wage MEANS depends on the structure the employee is on.
    # This single read is the only way SalaryStructure enters the calculation;
    # eligibility still comes from each component's own specific_employees, so
    # an employee with no structure follows exactly the path they always did.
    structure = contract.salary_structure_id
    structure_mode = (
        structure.structure_mode if structure else "gross_up"
    ) or "gross_up"

    # The pot a CTC Down structure divides. Stated outright on the contract as
    # Monthly CTC; when that is empty the wage is divided instead, which is what
    # structures configured before the field existed have always done.
    ctc_stated = bool(structure_mode == "ctc_down" and contract.monthly_ctc)
    # In CTC Down the wage is never basic pay: it is either the package being
    # divided (no Monthly CTC stated) or simply not used (one is). Basic comes
    # from the earning flagged as basic pay, always. Deciding it from whether a
    # CTC is stated got the second case wrong: a contract left holding a wage
    # from an earlier Gross Up structure read as "basic is the wage", the flagged
    # Basic was skipped, and basic_pay is zero under CTC Down -- so basic and
    # everything that is a percentage of it came out zero and the balance paid
    # the whole package.
    wage_is_the_pot = structure_mode == "ctc_down"

    # A stated CTC on a contract that also holds a wage is prorated by the
    # wage's own ratio below, and that ratio already carries the loss of pay, so
    # the package arrives here with it taken off. Everything that would take it
    # off again has to know.
    pot_prorated_by_wage = ctc_stated and bool(contract.wage)

    period_ctc = basic_pay
    if ctc_stated:
        # Prorated by the same factor the wage was, so a part-month payslip
        # divides a part-month package. Derived from the ratio rather than
        # re-prorated from scratch, so it cannot disagree with the wage.
        ratio = basic_pay / float(contract.wage) if contract.wage else 1.0
        period_ctc = float(contract.monthly_ctc) * ratio

    # Where basic pay comes from: the contract if it states a wage, otherwise
    # the earning flagged as basic pay. Resolved once, here, because the answer
    # decides two things that have to agree — what basic_pay is, and whether the
    # flagged earning is paid at all. See payroll/methods/basic_pay_source.py.
    # contract.pay_rate, NOT the period's basic_pay. They differ in exactly
    # the case that matters: an hourly contract states a rate of 10/hour, and
    # in a period with no attendance yet its computed basic is 0. Keying on
    # the computed figure read that as "the contract states nothing" and
    # refused the payslip outright -- for a correctly configured contract
    # whose employee simply had not logged hours.
    #
    # The question this asks is "does the contract name a figure to read basic
    # from", which is a property of the contract, not of how much was earned
    # this period. A monthly contract on full loss of pay is the same case: it
    # states a wage, and this period it comes to zero.
    basic_source, basic_component = resolve_basic_pay_source(
        contract.pay_rate,
        eligible_allowances(employee, start_date, end_date),
        wage_is_the_pot=wage_is_the_pot,
    )

    if structure_mode == "ctc_down":
        # The pot is the whole package, not basic pay. Basic comes from a
        # component here, so it starts at zero; leaving the wage in basic_pay
        # as well would count it twice, once as basic and again inside the
        # components that divide the package.
        #
        # It is seeded as GROSS as well as CTC, and that is the point of the
        # mode rather than a convenience: with the total known up front, a
        # structure can say "basic is 50% of gross", which is impossible while
        # gross is only discovered by adding basic to everything on top of it.
        component_context = new_context(0.0, total_gross=period_ctc)
        basic_pay = 0.0
    else:
        component_context = new_context(basic_pay)

    # Exposed so a custom formula (based_on="formula") can react to
    # attendance/LOP directly -- e.g. "(BASIC - LOP) * 0.12" for a
    # deduction that should follow the reduced basic without payroll_run
    # itself ever reducing basic_pay. LOP is provisional here for a
    # gross_pay-based contract (the real figure isn't known until gross
    # exists below) and is corrected in place once it is; PAID_DAYS/
    # UNPAID_DAYS don't depend on gross, so they're already final.
    component_context["PAID_DAYS"] = paid_days
    component_context["UNPAID_DAYS"] = unpaid_days
    component_context["LOP"] = loss_of_pay
    add_service_years(component_context, employee, contract, end_date)

    # The flagged earning is skipped when the contract already states basic.
    # Paying it as well would add a second basic on top of the one that is
    # already in gross.
    skip_component = (
        basic_component
        if basic_source == BASIC_FROM_CONTRACT and basic_component is not None
        else None
    )

    kwargs = {
        "employee": employee,
        "start_date": start_date,
        "end_date": end_date,
        "basic_pay": basic_pay,
        "day_dict": working_days_details,
        "component_context": component_context,
        "skip_allowance": skip_component,
        # Non-zero only when this contract deducts loss of pay separately
        # rather than taking it off basic pay. calculate_taxable_gross_pay
        # needs it: loss of pay is not a Deduction row, so without this it
        # was taxed as though it had been paid.
        "loss_of_pay_amount": loss_of_pay_amount,
    }
    # Loss of pay taken off the earning that IS basic pay, the way it comes off a
    # contract wage under Gross Up. The earning is cut right where it is worked
    # out, so everything that follows reads the adjusted basic: a percentage of
    # BASIC, a deduction based on basic pay, and the balance (which is worked
    # out from CTC less this cut, or it would simply win the money back).
    # Only where the LOP does not itself depend on gross, which includes basic.
    kwargs["basic_lop_reduction"] = (
        float(loss_of_pay)
        if (
            # Only when the package is stated on the contract. When the wage is
            # the pot being divided, the loss of pay has already come off it
            # (compute_salary_on_period reduces the wage), so cutting basic as
            # well would take it twice.
            #
            # The same goes for a stated CTC on a contract that also holds a
            # wage: the package was prorated by the wage's own ratio above, and
            # that ratio already carries the loss of pay.
            ctc_stated
            and not pot_prorated_by_wage
            and basic_source == BASIC_FROM_COMPONENT
            and contract.deduct_leave_from_basic_pay
            and not basic_pay_details.get("lop_from_gross")
        )
        else 0.0
    )
    if structure_mode == "ctc_down":
        # CTC is the whole cost to the employer, so the balance earning needs to
        # know which employer contributions are coming. See employer_cost.py.
        from payroll.methods.employer_cost import eligible_deductions

        kwargs["employer_deductions"] = eligible_deductions(
            employee, start_date, end_date
        )
    # basic pay will be basic_pay = basic_pay - update_compensation_amount
    # Overtime pay (regular/week-off/holiday) comes from the configurable
    # "Regular Overtime" / "Week Off Overtime" / "Holiday Overtime"
    # Allowance types — see calculate_based_on_overtime and friends in
    # payroll/methods/payslip_calc.py. Nothing to inject here; it's just
    # part of whatever calculate_allowance() returns below.
    allowances = calculate_allowance(**kwargs)

    # Basic pay as the flagged earning worked it out. Held back until after
    # gross is computed: gross is total_allowance + basic_pay, and when basic
    # comes from an earning it is already inside total_allowance, so feeding it
    # in as well would count it twice.
    derived_basic_pay = (
        float(component_context.get("BASIC", 0) or 0)
        if basic_source == BASIC_FROM_COMPONENT
        else None
    )
    # How much of the loss of pay the basic earning actually took (see above).
    basic_lop_applied = float(component_context.get("_basic_lop", 0) or 0)

    # Nobody said where basic pay comes from: no contract wage, and no earning
    # marked as basic pay. A zero basic is not a harmless display problem — a
    # filing status based on basic pay would tax nothing — so refuse the payslip
    # and say so, the same stance TaxComputationError takes.
    if basic_source == BASIC_FROM_NEITHER:
        # Still a refusal, but now only for what it was written for: nothing
        # anywhere states a rate. An employee who worked no hours this period
        # has a configured contract and gets a payslip of zero, which is the
        # truthful answer.
        raise StructureConfigurationError(
            f"{employee} has no basic pay: their contract states no wage or "
            "hourly rate, and no earning on their salary structure is marked "
            "as basic pay. Set a wage on the contract, or mark the earning "
            "that works basic out."
        )

    # finding the total allowance
    total_allowance = sum(allowance["amount"] for allowance in allowances["allowances"])

    kwargs["allowances"] = allowances
    kwargs["total_allowance"] = total_allowance
    updated_gross_pay_data = calculate_gross_pay(**kwargs)
    gross_pay = updated_gross_pay_data["gross_pay"]
    gross_pay_deductions = updated_gross_pay_data["deductions"]
    kwargs["gross_pay"] = gross_pay

    # Loss of pay as a share of GROSS, finished here because this is the first
    # point gross exists. compute_salary_on_period deferred it and left basic
    # whole, so the gross above is the full figure rather than one already
    # carrying the deduction -- taking a share of a reduced gross would charge
    # the same days twice over.
    #
    # It is always a separate deduction in this mode. It cannot come off basic
    # pay: basic is an input to gross, so subtracting it there would change the
    # very number the share is taken of.
    if basic_pay_details.get("lop_from_gross"):
        import calendar as _calendar

        divisor = getattr(contract, "daily_leave_amount_divisor", "working_days")
        if divisor == "calendar_days":
            days = _calendar.monthrange(start_date.year, start_date.month)[1]
        else:
            days = total_working_days
        gross_day = (gross_pay / days) if days else 0.0
        gross_lop = float(basic_pay_details.get("lop_unpaid_days", 0) or 0) * gross_day

        # custom_leave_deduction is already inside loss_of_pay from the
        # deferral, and is worked out per day from the wage rather than from
        # gross, so it is kept as it is and the gross part added to it.
        loss_of_pay = loss_of_pay + gross_lop
        loss_of_pay_amount = loss_of_pay
        # The provisional LOP seeded into the context above is now final --
        # deduction formulas (which run after this point) see the real figure.
        component_context["LOP"] = loss_of_pay

    # The earning that IS basic pay is not listed again beside it. Under CTC
    # Down basic comes from a component, so the same money is in two places at
    # once: the payslip's own basic_pay, and that component's row among the
    # allowances. Every reader of the rows then showed it twice -- and any that
    # added basic to the rows, which is what gross means under Gross Up, added
    # it twice as well.
    #
    # Gross is not affected. It was worked out from the full list above, where
    # the row belongs, and basic_pay was deliberately held at zero until after
    # that sum for this exact reason. Taking the row out of what gets STORED is
    # what makes the two modes store the same shape: allowances are the
    # earnings on top of basic pay, in either of them.
    basic_pay_row_id = (
        basic_component.id
        if basic_source == BASIC_FROM_COMPONENT and basic_component is not None
        else None
    )
    serialized_allowances = [
        row
        for row in allowances["allowances"]
        if basic_pay_row_id is None or row.get("allowance_id") != basic_pay_row_id
    ]

    if derived_basic_pay is not None:
        # Safe now that gross is fixed. Everything downstream — the tax base
        # when a filing status is "based on basic pay", the payslip's own basic
        # figure — wants the real derived number, not the zero that was only
        # there to keep gross from double-counting.
        basic_pay = derived_basic_pay
        kwargs["basic_pay"] = basic_pay

        # deduct_leave_from_basic_pay's reduction (in compute_salary_on_period)
        # landed on the wage-sourced basic_pay this line just discarded --
        # component-sourced basic never had a wage figure to subtract from in
        # the first place. Same reasoning as lop_from_gross just above: there
        # is no slot to subtract from without corrupting a number (here,
        # the component's own formula result) that was already relied on.
        # Left unhandled, the deduction simply vanished -- computed, then
        # thrown away with the basic_pay it never actually reduced.
        # Whatever part of the loss of pay the basic earning could not absorb
        # (it cannot go below zero) is still deducted, separately.
        if (
            contract.deduct_leave_from_basic_pay
            and not loss_of_pay_amount
            and not pot_prorated_by_wage
        ):
            leftover = loss_of_pay - basic_lop_applied
            if leftover > 0.005:
                loss_of_pay_amount = leftover

    # Whether Basic Pay above already carries the reduction, for the payslip's
    # own "already reflected" note -- true only when the deduction actually
    # has a basic_pay figure to have landed in.
    lop_reflected_in_basic = (
        contract.deduct_leave_from_basic_pay
        and not basic_pay_details.get("lop_from_gross")
        and (derived_basic_pay is None or basic_lop_applied > 0 or pot_prorated_by_wage)
    )

    pretax_deductions = calculate_pre_tax_deduction(**kwargs)
    post_tax_deductions = calculate_post_tax_deduction(**kwargs)

    installments = (
        pretax_deductions["installments"] | post_tax_deductions["installments"]
    )

    taxable_gross_pay = calculate_taxable_gross_pay(**kwargs)
    tax_deductions = calculate_tax_deduction(**kwargs)
    federal_tax = calculate_taxable_amount(**kwargs)

    total_allowance = sum(item["amount"] for item in allowances["allowances"])
    total_pretax_deduction = sum(
        item["amount"] for item in pretax_deductions["pretax_deductions"]
    )
    total_post_tax_deduction = sum(
        item["amount"] for item in post_tax_deductions["post_tax_deductions"]
    )
    total_tax_deductions = sum(
        item["amount"] for item in tax_deductions["tax_deductions"]
    )

    total_deductions = (
        total_pretax_deduction
        + total_post_tax_deduction
        + total_tax_deductions
        + federal_tax
        + loss_of_pay_amount  # 1022
    )

    # Nobody is deducted more than they earned. The components can total more
    # than gross -- most of a month unpaid against a part month worked, a loan
    # instalment larger than the pay it comes out of -- and the uncapped total
    # was being stored on the payslip and summed into every report, so a run's
    # "total deductions" could exceed its own gross.
    #
    # What the lines come to is kept as well, because the payslip has to show
    # both: the column lists its lines, then what could not be taken, then the
    # total. Otherwise the figures on screen do not add up.
    deduction_before_cap = total_deductions
    uncovered_deduction = 0.0
    if total_deductions > gross_pay:
        uncovered_deduction = round(total_deductions - gross_pay, 2)
        total_deductions = gross_pay
        logger.warning(
            "Deductions for %s came to %s against gross %s; %s not taken.",
            employee,
            round(deduction_before_cap, 2),
            round(gross_pay, 2),
            uncovered_deduction,
        )

    net_pay = gross_pay - total_deductions
    # loss_of_pay        -> actual lop amount
    # loss_of_pay_amount -> actual lop amount, but only when it wasn't
    #                       already subtracted from basic_pay above (i.e.
    #                       zero when deduct_leave_from_basic_pay is
    #                       enabled, since basic_pay already reflects it)
    net_pay = compute_net_pay(
        net_pay=net_pay,
        gross_pay=gross_pay,
        total_pretax_deduction=total_pretax_deduction,
        total_post_tax_deduction=total_post_tax_deduction,
        total_tax_deductions=total_tax_deductions,
        federal_tax=federal_tax,
        loss_of_pay_amount=loss_of_pay_amount,
        loss_of_pay=loss_of_pay,
    )
    updated_net_pay_data = update_compensation_deduction(
        employee, net_pay, "net_pay", start_date, end_date
    )
    net_pay = updated_net_pay_data["compensation_amount"]
    update_net_pay_deductions = updated_net_pay_data["deductions"]

    net_pay_deductions = calculate_net_pay_deduction(
        net_pay,
        post_tax_deductions["net_pay_deduction"],
        **kwargs,
    )
    net_pay_deduction_list = net_pay_deductions["net_pay_deductions"]
    for deduction in update_net_pay_deductions:
        net_pay_deduction_list.append(deduction)
    net_pay = net_pay - net_pay_deductions["net_deduction"]

    # An employee cannot be paid a negative amount. More was owed than was
    # earned -- a month of loss of pay against a part month of work, a loan
    # instalment bigger than the pay it comes out of -- and paying it would
    # mean billing them.
    #
    # Floored rather than left negative, and the shortfall is carried on the
    # payslip rather than dropped: it is money the employer is still owed, and
    # a payslip that silently swallowed it would make the arithmetic above
    # unexplainable. What to do with it -- carry it to next period, write it
    # off -- is a decision for a person, and this refuses to make it quietly.
    # A backstop behind the cap above. The deductions taken off net pay are
    # applied after it -- they are a share of net, so they cannot be known
    # earlier -- and they can still take the figure below zero on their own.
    # Anything they could not take is added to the same shortfall, because
    # from the employee's side it is one number: what was owed and not
    # collected.
    if net_pay < 0:
        uncovered_deduction = round(uncovered_deduction - net_pay, 2)
        logger.warning(
            "Net pay deductions exceeded pay for %s; net floored at zero.",
            employee,
        )
        net_pay = 0.0

    payslip_data = {
        # Every component code this payslip resolved, and to what. Carried so
        # the employer-contribution pass -- which runs after payroll_calculation
        # returns -- can evaluate an employer formula against the same names
        # the employee-side formulas were evaluated against. Without it the
        # two sides of one component would be reading different numbers.
        #
        # The engine's own lowercase bookkeeping keys are dropped: they are
        # not codes, nothing can reference them, and they would only be noise
        # in the stored payload.
        "component_context": {
            code: value
            for code, value in component_context.items()
            if not code.startswith("_")
        },
        # What was not taken, and what the lines came to before the cap. The
        # payslip needs both to show a column that adds up.
        "uncovered_deduction": uncovered_deduction,
        "deduction_before_cap": round(deduction_before_cap, 2),
        "employee": employee,
        "contract_wage": contract_wage,
        "basic_pay": basic_pay,
        "gross_pay": gross_pay,
        "taxable_gross_pay": taxable_gross_pay["taxable_gross_pay"],
        "net_pay": net_pay,
        "allowances": serialized_allowances,
        # Which component worked basic pay out, when one did. The row itself
        # is not stored (see above), so without this nothing downstream could
        # say how the figure was arrived at -- and under CTC Down "50% of CTC"
        # is the most worth saying of any line on the payslip.
        "basic_pay_component_id": basic_pay_row_id,
        "paid_days": paid_days,
        "unpaid_days": unpaid_days,
        "working_days": total_working_days,
        # What the daily figure was a share of, and what it was divided by, so
        # the payslip can say where loss of pay came from rather than leaving
        # an amount nobody can reproduce.
        "lop_base": (
            contract.get_daily_leave_amount_base_display()
            if contract.calculate_daily_leave_amount
            else None
        ),
        # The raw code (rather than the model's own display string) lets the
        # template pick "Basic pay" only for "wage" and its own name
        # ("Monthly CTC" / "Gross pay") for the other two bases.
        "lop_base_code": (
            contract.daily_leave_amount_base
            if contract.calculate_daily_leave_amount
            else None
        ),
        "lop_divisor": (
            contract.get_daily_leave_amount_divisor_display()
            if contract.calculate_daily_leave_amount
            else None
        ),
        "lop_flat_amount": (
            None
            if contract.calculate_daily_leave_amount
            else contract.deduction_for_one_leave_amount
        ),
        # The actual figures behind lop_base/lop_divisor's labels, so a
        # payslip can show the real equation (base ÷ days = daily rate)
        # instead of only naming which contract settings were used. None on
        # the hourly/daily wage-type branches, which price a day of leave
        # differently and never compute these.
        "lop_base_amount": lop_base_amount,
        "lop_divisor_days": lop_divisor_days,
        "lop_daily_rate": lop_daily_rate,
        # Was never added to this dict before, despite the template reading
        # it -- so `{% if lop_from_gross %}` was silently always false,
        # regardless of the contract's actual daily_leave_amount_base.
        "lop_from_gross": bool(basic_pay_details.get("lop_from_gross")),
        # For the payslip's own wording -- "Contract wage" IS "Contract
        # Basic" only under Gross Up (CTC Down's wage reads as the whole
        # package, not basic, so relabeling it the same way would lie).
        "structure_mode": structure_mode,
        # The package a CTC Down payslip divides, for the strip at its top: the
        # contract wage is zero there, and "Contract wage 0.00" says nothing.
        "monthly_ctc": float(contract.monthly_ctc) if ctc_stated else None,
        "lop_reflected_in_basic": lop_reflected_in_basic,
        "partial_pay_days": partial_pay_days,
        "regular_hours_label": regular_hours_label,
        "ot_hours_label": ot_hours_label,
        "ot_regular_hours_label": ot_regular_hours_label,
        "ot_week_off_hours_label": ot_week_off_hours_label,
        "ot_holiday_hours_label": ot_holiday_hours_label,
        "pending_attendance": pending_attendance,
        "basic_pay_deductions": basic_pay_deductions,
        "gross_pay_deductions": gross_pay_deductions,
        "pretax_deductions": pretax_deductions["pretax_deductions"],
        "post_tax_deductions": post_tax_deductions["post_tax_deductions"],
        "tax_deductions": tax_deductions["tax_deductions"],
        "net_deductions": net_pay_deduction_list,
        "total_deductions": total_deductions,
        "loss_of_pay": loss_of_pay,
        "custom_leave_deduction": custom_leave_deduction,
        "custom_leave_breakdown": custom_leave_breakdown,
        "federal_tax": federal_tax,
        "start_date": start_date,
        "end_date": end_date,
        "range": f"{start_date.strftime('%b %d %Y')} - {end_date.strftime('%b %d %Y')}",
    }
    data_to_json = payslip_data.copy()
    data_to_json["employee"] = employee.id
    data_to_json["start_date"] = start_date.strftime("%Y-%m-%d")
    data_to_json["end_date"] = end_date.strftime("%Y-%m-%d")
    json_data = json.dumps(data_to_json)

    payslip_data["json_data"] = json_data
    payslip_data["installments"] = installments
    return payslip_data
