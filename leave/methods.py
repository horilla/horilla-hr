import calendar
from datetime import date, datetime, timedelta

import pandas as pd
from django.apps import apps
from django.db.models import Q
from django.utils import timezone

from employee.models import Employee
from horilla.methods import get_horilla_model_class


def calculate_requested_days(
    start_date, end_date, start_date_breakdown, end_date_breakdown
):
    if start_date == end_date:
        return (
            1
            if start_date_breakdown == "full_day" and end_date_breakdown == "full_day"
            else 0.5
        )

    # Count full days between the two dates, excluding start and end
    middle_days = (end_date - start_date).days - 1

    # Count start and end days
    start_day_value = 1 if start_date_breakdown == "full_day" else 0.5
    end_day_value = 1 if end_date_breakdown == "full_day" else 0.5

    return middle_days + start_day_value + end_day_value


def holiday_dates_list(holidays):
    """
    :return: This function returns a list of all holiday dates.
    """
    holiday_dates = []
    for holiday in holidays:
        holiday_start_date = holiday.start_date
        holiday_end_date = holiday.end_date or holiday_start_date
        holiday_dates.extend(
            holiday_start_date + timedelta(i)
            for i in range((holiday_end_date - holiday_start_date).days + 1)
        )
    return holiday_dates


def company_leave_dates_list(company_leaves, start_date, end_date=None):
    """
    :return: This function returns a list of all company leave dates for every
    year from the start date to the end date
    """
    company_leave_dates = set()
    end_year = (end_date or start_date).year
    for year in range(start_date.year, max(end_year, start_date.year) + 1):
        for company_leave in company_leaves:
            based_on_week = company_leave.based_on_week
            based_on_week_day = company_leave.based_on_week_day

            for month in range(1, 13):
                month_calendar = calendar.monthcalendar(year, month)

                if based_on_week is not None:
                    # Set Sunday as the first day of the week
                    calendar.setfirstweekday(6)
                    try:
                        week_days = [
                            day
                            for day in month_calendar[int(based_on_week)]
                            if day != 0
                        ]
                        for day in week_days:
                            date = datetime(year, month, day)
                            if date.weekday() == int(based_on_week_day):
                                company_leave_dates.add(date.date())
                    except IndexError:
                        pass
                else:
                    # Set Monday as the first day of the week
                    calendar.setfirstweekday(0)
                    for week in month_calendar:
                        if week[int(based_on_week_day)] != 0:
                            date = datetime(year, month, week[int(based_on_week_day)])
                            company_leave_dates.add(date.date())

    return list(company_leave_dates)


def get_leave_day_attendance(employee, comp_id=None):
    """
    This function returns a queryset of attendance on leave dates
    """
    Attendance = get_horilla_model_class(app_label="attendance", model="attendance")
    from leave.models import CompensatoryLeaveRequest

    attendances_to_exclude = Attendance.objects.none()  # Empty queryset to start with
    # Check for compensatory leave requests that are not rejected and not the current one
    if (
        CompensatoryLeaveRequest.objects.filter(employee_id=employee)
        .exclude(Q(id=comp_id) | Q(status="rejected"))
        .exists()
    ):
        comp_leave_reqs = CompensatoryLeaveRequest.objects.filter(
            employee_id=employee
        ).exclude(Q(id=comp_id) | Q(status="rejected"))
        for req in comp_leave_reqs:
            attendances_to_exclude |= req.attendance_id.all()
    # Filter holiday attendance excluding the attendances in attendances_to_exclude
    holiday_attendance = Attendance.objects.filter(
        is_holiday=True, employee_id=employee, attendance_validated=True
    ).exclude(id__in=attendances_to_exclude.values_list("id", flat=True))
    return holiday_attendance


def attendance_days(employee, attendances):
    """
    This function returns count of workrecord from the attendance
    """
    attendance_days = 0
    if apps.is_installed("attendance"):
        from attendance.models import WorkRecords

        for attendance in attendances:
            if WorkRecords.objects.filter(
                employee_id=employee, date=attendance.attendance_date
            ).exists():
                work_record_type = (
                    WorkRecords.objects.filter(
                        employee_id=employee, date=attendance.attendance_date
                    )
                    .first()
                    .work_record_type
                )
                if work_record_type == "HDP":
                    attendance_days += 0.5
                elif work_record_type == "FDP":
                    attendance_days += 1
    return attendance_days


def filter_conditional_leave_request(request):
    """
    Filters and returns LeaveRequest objects that have been conditionally approved by the previous sequence of approvals.
    """
    approval_manager = Employee.objects.filter(employee_user_id=request.user).first()
    leave_request_ids = []
    if apps.is_installed("leave"):
        from leave.models import LeaveRequest, LeaveRequestConditionApproval

        multiple_approval_requests = LeaveRequestConditionApproval.objects.filter(
            manager_id=approval_manager
        )

    else:
        multiple_approval_requests = None
    for instance in multiple_approval_requests:
        if instance.sequence > 1:
            pre_sequence = instance.sequence - 1
            leave_request_id = instance.leave_request_id
            instance = LeaveRequestConditionApproval.objects.filter(
                leave_request_id=leave_request_id, sequence=pre_sequence
            ).first()
            if instance and instance.is_approved:
                leave_request_ids.append(instance.leave_request_id.id)
        else:
            leave_request_ids.append(instance.leave_request_id.id)
    return LeaveRequest.objects.filter(pk__in=leave_request_ids)


def parse_excel_date(value):
    """
    Convert Excel date values into a valid Python date object.
    Supports multiple formats: YYYY-MM-DD, DD-MM-YYYY, DD Month YYYY, MM/DD/YYYY, etc.
    """
    if not value or pd.isna(value):
        return None

    if isinstance(value, date):
        # Already a date (from Excel or pandas)
        return value

    if isinstance(value, datetime):
        # Datetime object → convert to date
        return value.date()

    if isinstance(value, str):
        value = value.strip()
        # Try multiple formats
        date_formats = [
            "%Y-%m-%d",  # 2025-07-22
            "%d-%m-%Y",  # 22-07-2025
            "%d/%m/%Y",  # 22/07/2025
            "%m/%d/%Y",  # 07/22/2025
            "%d %B %Y",  # 22 July 2025
            "%d %B, %Y",  # 22 July, 2025
            "%d-%b-%Y",  # 22-Jul-2025
        ]
        for fmt in date_formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

    # If nothing matches, return None (caller should handle error)
    return None


def request_leave_cancellation(leave_request_id, reason, employee):
    """
    Move an approved leave to "cancel_requested". The leave stays in force
    until a manager decides on the cancellation.

    The row is locked so two submissions can't both pass the status check.
    Returns (leave_request, error_message); error_message is None on success.
    """
    from django.db import transaction
    from django.utils.translation import gettext as _

    from leave.models import LeaveRequest, LeaverequestComment

    with transaction.atomic():
        leave_request = (
            LeaveRequest._base_manager.select_for_update()
            .filter(id=leave_request_id)
            .first()
        )
        if leave_request is None:
            return None, _("Leave request not found.")
        if leave_request.status == "cancel_requested":
            return leave_request, _(
                "A cancellation request is already pending for this leave."
            )
        if leave_request.cancellation_requested:
            return leave_request, _(
                "A cancellation has already been requested for this leave."
            )
        if leave_request.status != "approved" or leave_request.end_date < date.today():
            return leave_request, _("You can't cancel this leave request.")
        leave_request.cancellation_requested = True
        leave_request.reject_reason = reason
        leave_request.status = "cancel_requested"
        leave_request.save()
        LeaverequestComment.objects.create(
            request_id=leave_request,
            employee_id=employee,
            comment=_("Cancellation requested: %(reason)s") % {"reason": reason},
        )
    return leave_request, None


def decide_leave_cancellation(leave_request_id, approve, employee, reason=""):
    """
    Approve or reject a pending cancellation request.

    Approve: the leave becomes "cancelled" and its approved days go back to the
    employee's balance (the same refund a rejection makes). Reject: the leave
    returns to "approved", dates and allocation untouched. Locked rows make
    concurrent decisions apply only once.
    Returns (leave_request, error_message); error_message is None on success.
    """
    from django.db import transaction
    from django.utils.translation import gettext as _

    from leave.models import AvailableLeave, LeaveRequest, LeaverequestComment

    with transaction.atomic():
        leave_request = (
            LeaveRequest._base_manager.select_for_update()
            .filter(id=leave_request_id)
            .first()
        )
        if leave_request is None:
            return None, _("Leave request not found.")
        if leave_request.status != "cancel_requested":
            return leave_request, _(
                "This leave request has no pending cancellation request."
            )
        if approve:
            available_leave = (
                AvailableLeave._base_manager.select_for_update()
                .filter(
                    leave_type_id=leave_request.leave_type_id,
                    employee_id=leave_request.employee_id,
                )
                .first()
            )
            if available_leave is None:
                return leave_request, _(
                    "No available leave record found for this employee and leave type."
                )
            available_leave.available_days += leave_request.approved_available_days
            available_leave.carryforward_days += (
                leave_request.approved_carryforward_days
            )
            available_leave.save()
            leave_request.approved_available_days = 0
            leave_request.approved_carryforward_days = 0
            leave_request.status = "cancelled"
            comment_text = _("Cancellation approved")
        else:
            leave_request.status = "approved"
            leave_request.reject_reason = ""
            comment_text = _("Cancellation rejected")
        if reason:
            comment_text = f"{comment_text}: {reason}"
        leave_request.save()
        LeaverequestComment.objects.create(
            request_id=leave_request, employee_id=employee, comment=comment_text
        )
    return leave_request, None


def due_available_leaves(leave_type, today_date=None):
    """
    Available leaves of a leave type whose reset or carryforward expiry date has passed.
    """
    today_date = today_date or timezone.localdate()
    return leave_type.employee_available_leave.filter(
        Q(reset_date__lte=today_date) | Q(expired_date__lte=today_date)
    )


def reset_available_leave(available_leave, today_date, reset_reason, expiry_reason):
    """
    Apply the reset and carryforward expiry already due on one available leave;
    returns True if anything was applied, False if nothing was due.
    """
    reset_date = available_leave.reset_date
    expired_date = available_leave.expired_date
    applied = False
    if reset_date and reset_date <= today_date:
        available_leave.update_carryforward()
        available_leave.reset_date = available_leave.set_reset_date(
            assigned_date=today_date, available_leave=available_leave
        )
        available_leave._change_reason = reset_reason
        available_leave.save()
        applied = True
    # Moves the date forward in the same save (per the leave type's expiry
    # method), so a balance is never expired twice.
    if expired_date and available_leave.expire_carryforward(
        today_date, reason=expiry_reason
    ):
        applied = True
    return applied


def run_missed_resets(leave_type, reset_reason, expiry_reason, today_date=None):
    """
    Apply every reset and expiry already due for a leave type, then roll the
    type's own carryforward expiry date; returns the per-balance outcome as
    {"reset": [...], "failed": [...], "type_expiry_rolled": bool}.
    """
    import logging

    from django.db import transaction

    today_date = today_date or timezone.localdate()
    result = {"reset": [], "failed": [], "type_expiry_rolled": False}
    due_balances = due_available_leaves(leave_type, today_date).select_related(
        "employee_id"
    )
    for available_leave in due_balances:
        before = round(
            (available_leave.available_days or 0)
            + (available_leave.carryforward_days or 0),
            2,
        )
        try:
            with transaction.atomic():
                applied = reset_available_leave(
                    available_leave, today_date, reset_reason, expiry_reason
                )
        except Exception as error:
            logging.getLogger(__name__).exception(
                "Leave reset failed for available leave %s", available_leave.pk
            )
            result["failed"].append(
                {"available_leave": available_leave, "error": str(error)}
            )
            continue
        if applied:
            after = round(
                (available_leave.available_days or 0)
                + (available_leave.carryforward_days or 0),
                2,
            )
            result["reset"].append(
                {"available_leave": available_leave, "before": before, "after": after}
            )
    # The shared date only exists for the "First Expiry Date" method.
    if (
        leave_type.carryforward_expiry_method == "first_expiry_date"
        and leave_type.carryforward_expire_date
        and leave_type.carryforward_expire_date <= today_date
    ):
        leave_type.carryforward_expire_date = leave_type.set_expired_date(today_date)
        leave_type.save()
        result["type_expiry_rolled"] = True
    return result
