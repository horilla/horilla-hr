import datetime
from datetime import timedelta

from django.utils import timezone

from base.backends import logger
from horilla.scheduling import register_job


def auto_punch_out():
    from attendance.methods.utils import Request
    from attendance.models import Attendance, AttendanceActivity
    from attendance.views.clock_in_out import clock_out
    from base.models import EmployeeShiftSchedule

    automatic_check_out_shifts = EmployeeShiftSchedule.objects.filter(
        is_auto_punch_out_enabled=True
    )

    for shift_schedule in automatic_check_out_shifts:
        activities = AttendanceActivity.objects.filter(
            shift_day=shift_schedule.day,
            clock_out_date=None,
            clock_out=None,
        ).order_by("-created_at")

        for activity in activities:
            attendance = Attendance.objects.filter(
                employee_id=activity.employee_id,
                attendance_clock_out=None,
                attendance_clock_out_date=None,
                shift_id=shift_schedule.shift_id,
                attendance_day=shift_schedule.day,
                attendance_date=activity.attendance_date,
            ).first()

            if attendance:
                date = activity.attendance_date
                if (
                    shift_schedule.is_night_shift
                    and shift_schedule.start_time
                    and shift_schedule.end_time
                    and shift_schedule.start_time > shift_schedule.end_time
                ):
                    date += timedelta(days=1)

                combined_datetime = timezone.make_aware(
                    datetime.datetime.combine(date, shift_schedule.auto_punch_out_time)
                )

                if combined_datetime < timezone.now():
                    try:
                        clock_out(
                            Request(
                                user=attendance.employee_id.employee_user_id,
                                date=date,
                                time=shift_schedule.auto_punch_out_time,
                                datetime=combined_datetime,
                            )
                        )
                    except Exception as e:
                        logger.error(f"auto_punch_out error: {e}")


def create_work_record():
    from attendance.models import WorkRecords
    from employee.models import Employee

    date = datetime.date.today()
    work_records = WorkRecords.objects.filter(date=date).values_list(
        "employee_id", flat=True
    )
    employees = Employee.objects.exclude(id__in=work_records)
    records_to_create = []

    for employee in employees:
        try:
            shift_schedule = employee.get_shift_schedule()
            if shift_schedule is None:
                continue

            shift = employee.get_shift()
            record = WorkRecords(
                employee_id=employee,
                date=date,
                work_record_type="DFT",
                shift_id=shift,
                message="",
            )
            records_to_create.append(record)
        except Exception as e:
            # Employee.__str__ is "Name (BADGE)", so interpolating the
            # object writes a real name into the log. The id is enough to
            # find the row, and logger.exception keeps the traceback.
            logger.exception(
                "Error preparing work record for employee_id=%s",
                getattr(employee, "pk", employee),
            )

    if records_to_create:
        try:
            WorkRecords.objects.bulk_create(records_to_create, ignore_conflicts=True)
        except Exception as e:
            logger.error(f"Failed to bulk create work records: {e}")


register_job(create_work_record, "interval", minutes=30, misfire_grace_time=3600 * 3)
register_job(
    create_work_record,
    "cron",
    job_id="create_daily_work_record",
    hour=0,
    minute=30,
    misfire_grace_time=3600 * 9,
)
register_job(
    auto_punch_out,
    "interval",
    job_id="auto_punch_out",
    minutes=5,
    misfire_grace_time=600,
)
