"""
Keeping the Daily Work Status (work records) in step with the last regularisation of a day.

A regularisation (``AttendanceConflictResolution``) is one row per employee and day, replaced each
time the day is regularised again, so the last one is the only one there is. The monthly summary
reads it directly. The work records are written by other things (a clock-out, an approved leave),
so the regularisation is applied to them: when it is saved, and again whenever one of those
rewrites the day. Deleting it (undo) puts the day back as the attendance and leaves have it.
"""

SPLIT_PREFIX = "split:"

# resolution -> (work record type, message, day percentage, is a leave record)
_SPECS = {
    "full_present": ("FDP", "Regularised: Present", 1.0, False),
    "attendance": ("FDP", "Regularised: Present", 1.0, False),
    "half_present": ("HDP", "Regularised: Half Day", 0.5, False),
    "half_absent": ("HDP", "Regularised: Half Absent", 0.5, False),
    "partial_hours": ("HDP", "Regularised: Partial Hours", 0.5, False),
    # "DFT" with a shift is what the Daily Work Status draws as an absent day ("A").
    "absent": ("DFT", "Regularised: Absent", 0.0, False),
    "paid_leave": ("ABS", "Regularised: Leave", 0.0, True),
    "unpaid_leave": ("ABS", "Regularised: Leave", 0.0, True),
    "leave": ("ABS", "Regularised: Leave", 0.0, True),
    "holiday": ("HD", "Regularised: Day off", 0.0, False),
    "week_off": ("HD", "Regularised: Day off", 0.0, False),
}


def record_spec(resolution):
    """``(type, message, day_percentage, is_leave)`` for a resolution, or None when it changes nothing."""
    if resolution in _SPECS:
        return _SPECS[resolution]
    if resolution and resolution.startswith(SPLIT_PREFIX):
        halves = resolution[len(SPLIT_PREFIX) :].split("+")
        present = halves.count("P")
        if present == 2:
            return ("FDP", "Regularised: Split Day", 1.0, False)
        if present == 1:
            return ("HDP", "Regularised: Split Day", 0.5, False)
        if all(h in ("PL", "UL") for h in halves):
            return ("ABS", "Regularised: Leave", 0.0, True)
        return ("DFT", "Regularised: Split Day", 0.0, False)
    return None  # e.g. approve_ot: nothing to show on the work record


def apply_resolution(resolution):
    """Write a regularisation onto its day's work record, making one when there is none."""
    from attendance.models import WorkRecords

    spec = record_spec(resolution.resolution)
    if spec is None:
        return None
    record_type, message, percentage, is_leave = spec
    employee = resolution.employee_id
    record = WorkRecords._base_manager.filter(
        employee_id=employee, date=resolution.date
    ).first()
    if record is None:
        record = WorkRecords(employee_id=employee, date=resolution.date)
    record.work_record_type = record_type
    record.message = message
    record.day_percentage = percentage
    record.is_leave_record = is_leave
    if not is_leave:
        record.leave_request_id = None
    if record.shift_id is None:
        work_info = getattr(employee, "employee_work_info", None)
        record.shift_id = getattr(work_info, "shift_id", None)
    record.save()
    return record


def apply_resolution_for(employee, date):
    """Apply the day's regularisation, if it has one. True when there was one."""
    from attendance.models import AttendanceConflictResolution

    resolution = AttendanceConflictResolution._base_manager.filter(
        employee_id=employee, date=date
    ).first()
    if resolution is None:
        return False
    return apply_resolution(resolution) is not None


def restore_natural(employee, date):
    """A regularisation was removed: show the day as its attendance and leaves have it."""
    from attendance.models import Attendance, WorkRecords

    attendance = Attendance._base_manager.filter(
        employee_id=employee, attendance_date=date
    ).first()
    if attendance is not None:
        from attendance.signals import update_work_record_from_attendance

        update_work_record_from_attendance(attendance)
        return
    record = WorkRecords._base_manager.filter(employee_id=employee, date=date).first()
    if record is None:
        return
    leave = _leave_covering(employee, date)
    if leave is not None:
        record.is_leave_record = True
        record.leave_request_id = leave
        record.work_record_type = "ABS"
        record.message = "Leave"
        record.day_percentage = 0.0
        record.save()
    elif record.message and record.message.startswith("Regularised"):
        record.delete()  # made by the regularisation alone: nothing else puts it there


def _leave_covering(employee, date):
    """An approved leave that counts ``date`` as leave, or None."""
    try:
        from leave.models import LeaveRequest
    except Exception:
        return None
    from attendance.methods.leave_days import leave_counted_dates

    candidates = LeaveRequest._base_manager.filter(
        employee_id=employee,
        status__in=["approved", "cancel_requested"],
        start_date__lte=date,
    )
    for leave in candidates:
        if (leave.end_date or leave.start_date) >= date and date in leave_counted_dates(
            leave
        ):
            return leave
    return None
