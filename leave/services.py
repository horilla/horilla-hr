"""
leave/services.py

Centralised business-logic helpers for the leave app.
Condition evaluation follows the same pattern as payroll allowance eligibility checks.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from leave import forecast


def evaluate_leave_type_conditions(leave_type, employee):
    """
    Evaluate all conditions configured on a LeaveType against an employee.

    Returns a (is_eligible, error_message) tuple.  When all conditions pass,
    returns (True, None).  On the first failing condition it returns
    (False, <translated error string>).

    Usage::

        is_eligible, msg = evaluate_leave_type_conditions(leave_type, employee)
        if not is_eligible:
            raise ValidationError(msg)
    """
    from leave.models import AvailableLeave

    for condition in leave_type.conditions.all():
        ctype = condition.condition_type

        if ctype == "gender":
            emp_gender = (getattr(employee, "gender", None) or "").lower()
            required_gender = (condition.value or "").lower()
            if emp_gender and required_gender and emp_gender != required_gender:
                return False, _(
                    "This leave type is restricted to {gender} employees only."
                ).format(gender=condition.value)

        elif ctype == "once_per_employment":
            already_assigned = AvailableLeave.objects.filter(
                employee_id=employee,
                leave_type_id=leave_type,
            ).exists()
            if already_assigned:
                return False, _(
                    "'{leave_type}' can only be assigned once per employment and has already been assigned to this employee."
                ).format(leave_type=leave_type.name)

        elif ctype == "marital_status":
            emp_status = (getattr(employee, "marital_status", None) or "").lower()
            required_status = (condition.value or "").lower()
            if emp_status and required_status and emp_status != required_status:
                return False, _(
                    "This leave type is restricted to employees with marital status: {status}."
                ).format(status=condition.value)

        elif ctype == "nationality":
            emp_country = (getattr(employee, "country", None) or "").lower()
            required_country = (condition.value or "").lower()
            if emp_country and required_country and emp_country != required_country:
                return False, _(
                    "This leave type is restricted to employees with nationality: {nationality}."
                ).format(nationality=condition.value)

        elif ctype == "department":
            dept = None
            work_info = getattr(employee, "employee_work_info", None)
            if work_info:
                dept_obj = getattr(work_info, "department_id", None)
                if dept_obj:
                    dept = str(dept_obj).lower()
            required_dept = (condition.value or "").lower()
            if dept and required_dept and dept != required_dept:
                return False, _(
                    "This leave type is restricted to employees in the {department} department."
                ).format(department=condition.value)

        elif ctype == "employment_type":
            emp_type = None
            work_info = getattr(employee, "employee_work_info", None)
            if work_info:
                emp_type_obj = getattr(work_info, "employee_type_id", None)
                if emp_type_obj:
                    emp_type = str(emp_type_obj).lower()
            required_type = (condition.value or "").lower()
            if emp_type and required_type and emp_type != required_type:
                return False, _(
                    "This leave type is restricted to employees with employment type: {emp_type}."
                ).format(emp_type=condition.value)

        elif ctype == "grade":
            grade = None
            work_info = getattr(employee, "employee_work_info", None)
            if work_info:
                grade_obj = getattr(work_info, "job_position_id", None)
                if grade_obj:
                    grade = str(grade_obj).lower()
            required_grade = (condition.value or "").lower()
            if grade and required_grade and grade != required_grade:
                return False, _(
                    "This leave type is restricted to employees with grade: {grade}."
                ).format(grade=condition.value)

    return True, None


def has_sufficient_leave_balance(available_leave, requested_days) -> bool:
    """
    Gate used by leave_request_approve before deducting balance.

    Returns True when available_days + carryforward_days covers requested_days.
    """
    total = (available_leave.available_days or 0) + (
        available_leave.carryforward_days or 0
    )
    return total >= float(requested_days or 0)


def get_condition_display_choices():
    """
    Returns a dict of {condition_type: suggested value choices} for UI hints.
    """
    return {
        "gender": [("male", _("Male")), ("female", _("Female")), ("other", _("Other"))],
        "marital_status": [
            ("single", _("Single")),
            ("married", _("Married")),
            ("divorced", _("Divorced")),
        ],
        "once_per_employment": [],
        "nationality": [],
        "department": [],
        "employment_type": [],
        "grade": [],
        "service_duration": [],
    }


PROVIDED_RESET = "Leave reset provided"
PROVIDED_EXPIRY = "Carryforward expired provided"
PROVIDED_TAKEN = "Forecasted leave taken"
PROVIDED_REFUND = "Forecasted leave refunded"
PROVIDED_UNDONE = "Leave approval undone"


def provide_resets(available_leave, balance):
    """
    Bring a balance forward to the cycle of a later date, in memory: every reset (and carryforward expiry) between
    now and then is applied, the way the scheduler would on each of those days, and the next reset moves to the
    one after that cycle. The scheduler therefore never runs them again. The resets are written to the balance's
    history, one row each, when the balance is saved (see ``AvailableLeave.save``).
    """
    steps = balance.steps
    if not steps:
        return
    resets = [step["date"] for step in steps if step["kind"] == "reset"]
    following = forecast.reset_after(available_leave, resets[-1]) if resets else None
    available_leave._provided_steps = [
        {
            "date": step["date"],
            "reason": f"{PROVIDED_RESET if step['kind'] == 'reset' else PROVIDED_EXPIRY}: {step['date'].isoformat()}",
            "available": step["allowance"],
            "carryforward": step["carryforward"],
        }
        for step in steps
    ]
    last = steps[-1]
    available_leave.available_days = last["allowance"]
    available_leave.carryforward_days = last["carryforward"]
    if following:
        available_leave.reset_date = following
    if last["kind"] == "expiry" or any(step["kind"] == "expiry" for step in steps):
        expiry = next(step["date"] for step in steps if step["kind"] == "expiry")
        available_leave.expired_date = available_leave.next_expiry_date(expiry)


def charge_leave_request(
    leave_request, available_leave, carryforward_first=False, result=None
):
    """
    Take the days of an approved request from the balance.

    A leave that ends after the balance's next reset is charged to the cycle that reset starts, so the balance is
    first brought forward to that cycle (``provide_resets``) and the days come out of it; the request remembers the
    cycle in ``provided_cycle``. Anything else comes out of the balance now. Available days go first (carryforward
    first with ``carryforward_first``) and the split is kept on the request for a refund. Nothing is saved: the
    caller saves both. Returns the ``forecast.Check`` that decided it.
    """
    days = leave_request.requested_days or 0
    result = result or forecast.check(
        available_leave, leave_request.end_date, days, exclude=leave_request
    )
    leave_request.provided_cycle = None
    if result.ahead:
        provide_resets(available_leave, result.balance)
        leave_request.provided_cycle = result.balance.cycle_start
        available_leave._change_reason = (
            f"{PROVIDED_TAKEN}: {result.balance.cycle_start.isoformat()}"
        )
    if carryforward_first:
        from_carryforward = min(days, available_leave.carryforward_days)
        available_leave.carryforward_days -= from_carryforward
        available_leave.available_days -= days - from_carryforward
        leave_request.approved_carryforward_days = from_carryforward
        leave_request.approved_available_days = days - from_carryforward
    elif days > available_leave.available_days:
        rest = days - available_leave.available_days
        leave_request.approved_available_days = available_leave.available_days
        available_leave.available_days = 0
        available_leave.carryforward_days -= rest
        leave_request.approved_carryforward_days = rest
    else:
        available_leave.available_days -= days
        leave_request.approved_available_days = days
    return result


def refund_leave_days(leave_request, available_leave):
    """
    Give the days of a rejected or cancelled leave back to its balance (in memory; the caller saves it).

    A leave that was approved ahead of its cycle brought the balance forward, so when nothing has touched the
    balance since and that cycle has not started, the balance goes back to what it was before the approval: the
    resets taken in advance are taken back with it. Otherwise the days are simply added back.
    """
    if not rewind_provided(leave_request, available_leave):
        available_leave.available_days += leave_request.approved_available_days
        available_leave.carryforward_days += leave_request.approved_carryforward_days
        if leave_request.provided_cycle:
            # Dated by the cycle it was charged to, so the ledger puts it after that leave's own row.
            available_leave._change_reason = (
                f"{PROVIDED_REFUND}: {leave_request.provided_cycle.isoformat()}"
            )
    leave_request.approved_available_days = 0
    leave_request.approved_carryforward_days = 0


def rewind_provided(leave_request, available_leave):
    """
    Put a balance back as it was before the approval of ``leave_request`` brought it forward. Only when that
    approval is the latest thing in the balance's history, so nothing later is lost. Returns whether it did.
    """
    cycle = leave_request.provided_cycle
    if not cycle or cycle <= timezone.localdate():
        return False
    rows = list(available_leave.history.order_by("-history_id"))
    if (
        not rows
        or rows[0].history_change_reason != f"{PROVIDED_TAKEN}: {cycle.isoformat()}"
    ):
        return False
    index = 1
    while index < len(rows) and (rows[index].history_change_reason or "").startswith(
        (PROVIDED_RESET, PROVIDED_EXPIRY)
    ):
        index += 1
    if index == 1 or index >= len(rows):
        return False  # nothing was brought forward, or no earlier state to go back to
    before = rows[index]
    available_leave.available_days = before.available_days
    available_leave.carryforward_days = before.carryforward_days
    available_leave.expired_date = before.expired_date
    # The next reset was the first one the approval brought forward. (The old history row can hold an earlier
    # date if the schedule was changed since, because that change is not a save of the balance.)
    from leave.models import provided_date

    first_reset = next(
        (
            provided_date(row.history_change_reason)
            for row in reversed(rows[1:index])
            if (row.history_change_reason or "").startswith(PROVIDED_RESET)
        ),
        None,
    )
    available_leave.reset_date = first_reset or before.reset_date
    available_leave._change_reason = (
        f"{PROVIDED_UNDONE}: resets brought forward were taken back"
    )
    return True
