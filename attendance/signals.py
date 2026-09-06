# attendance/signals.py

import logging
from datetime import datetime, timedelta

from django.apps import apps
from django.db.models.signals import post_migrate, post_save, pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from attendance.methods.utils import strtime_seconds
from attendance.models import Attendance, AttendanceGeneralSetting, WorkRecords
from base.models import Company, PenaltyAccounts
from employee.models import Employee
from horilla.methods import get_horilla_model_class

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Attendance)
def attendance_post_save(sender, instance, **kwargs):
    """
    Handle post-save actions for Attendance model.
    """
    if kwargs.get("raw"):
        # Fixture loading (loaddata) already ships its own explicit
        # WorkRecords row for every Attendance row, computed the same way
        # this signal would compute it. Running this anyway shadow-creates
        # a second WorkRecords row (auto-assigned pk) for the same
        # (employee, date) *before* the fixture's own explicit row gets
        # inserted, which then collides on the (employee_id, date) unique
        # constraint -- masked on a full --flush (pk sequences reset, so
        # the auto-assigned pk often coincidentally matches the fixture's),
        # but a guaranteed collision on any subsequent non-flush reload
        # once the sequence has advanced.
        return
    min_hour_second = strtime_seconds(instance.minimum_hour)
    at_work_second = strtime_seconds(instance.attendance_worked_hour)

    if not instance.attendance_validated:
        status, message = "CONF", _("Validate the attendance")
    elif at_work_second >= min_hour_second:
        status, message = "FDP", _("Present")
    elif at_work_second >= min_hour_second / 2:
        status, message = "HDP", _("Incomplete minimum hour")
    else:
        status, message = "ABS", _("Incomplete half minimum hour")
    try:
        work_record, created = WorkRecords.objects.get_or_create(
            date=instance.attendance_date,
            employee_id=instance.employee_id,
        )
    except WorkRecords.MultipleObjectsReturned:
        work_records = WorkRecords.objects.filter(
            date=instance.attendance_date,
            employee_id=instance.employee_id,
        ).order_by("id")

        work_record = work_records.first()

        if work_records.count() > 1:
            ids = work_records.exclude(id=work_record.id).values_list("id", flat=True)
            WorkRecords._base_manager.filter(id__in=ids).delete()

    except Exception as e:
        logger.exception("Work record signal failed")

    work_record.employee_id = instance.employee_id
    work_record.date = instance.attendance_date
    work_record.at_work = instance.attendance_worked_hour
    work_record.min_hour = instance.minimum_hour
    work_record.min_hour_second = min_hour_second
    work_record.at_work_second = at_work_second
    work_record.work_record_type = status
    work_record.message = message
    work_record.is_attendance_record = True
    work_record.attendance_id = instance
    work_record.shift_id = instance.shift_id

    if instance.attendance_validated:
        work_record.day_percentage = (
            1.00 if at_work_second > min_hour_second / 2 else 0.50
        )

    if work_record.is_leave_record:
        message = (
            _("Half day leave") if status == "HDP" else _("An approved leave exists")
        )

    if not instance.attendance_clock_out:
        status, message = "FDP", _("Currently working")

    work_record.work_record_type = status
    work_record.message = message
    work_record.save()


@receiver(pre_delete, sender=Attendance)
def handle_attendance_deletion(sender, instance, **kwargs):
    for workrecord in instance.workrecords_set.all():
        if not workrecord.leave_request_id:
            workrecord.delete()


# @receiver(post_migrate)
def add_missing_attendance_to_workrecord(sender, **kwargs):
    if sender.label not in ["attendance", "leave"]:
        return

    from attendance.models import Attendance, WorkRecords

    try:
        work_records = WorkRecords.objects.filter(
            is_attendance_record=True, attendance_id__isnull=True
        )

        if not work_records.exists():
            return

        attendances = Attendance.objects.all()
        attendance_map = {
            (att.employee_id, att.attendance_date): att for att in attendances
        }

        records_to_update = []
        for record in work_records:
            attendance = attendance_map.get((record.employee_id, record.date))
            if attendance:
                record.attendance_id = attendance
                records_to_update.append(record)
            else:
                record.delete()

        if records_to_update:
            WorkRecords.objects.bulk_update(
                records_to_update, ["attendance_id"], batch_size=500
            )
            logger.info(
                "Updated %s work records with attendance information",
                len(records_to_update),
            )

    except Exception as e:
        logger.exception("Error updating work records with attendance")


# @receiver(post_migrate)
def add_missing_shift_to_work_record(sender, **kwargs):
    if sender.label not in ["attendance", "leave"]:
        return

    try:
        work_records = WorkRecords.objects.filter(
            is_attendance_record=True, shift_id__isnull=True
        )

        if not work_records.exists():
            return

        records_to_update = []

        for record in work_records:
            if record.attendance_id:
                record.shift_id = record.attendance_id.shift_id
            else:
                record.shift_id = record.employee_id.employee_work_info.shift_id

            records_to_update.append(record)

        if records_to_update:
            WorkRecords.objects.bulk_update(
                records_to_update, ["shift_id"], batch_size=500
            )
            logger.info(
                "Updated %s work records with shift information",
                len(records_to_update),
            )

    except Exception as e:
        logger.exception("Error updating work records with shift information")


@receiver(post_save, sender=Company)
def create_attendance_setting(sender, instance, created, raw, **kwargs):
    """
    Signal receiver that automatically creates an AttendanceGeneralSetting object
    whenever a new Company is created. This does NOT skip creation during
    loaddata, so the object will also be created when fixture data is loaded.
    """
    AttendanceGeneralSetting.objects.get_or_create(company_id=None)
    if created:
        AttendanceGeneralSetting.objects.get_or_create(company_id=instance)


# @receiver(post_migrate)
def create_missing_work_records(sender, **kwargs):
    if sender.label not in ["attendance"]:
        return

    employees = Employee.objects.all()
    work_records = WorkRecords.objects.all()

    if work_records.exists():
        st_date = work_records.earliest("date").date

        for employee in employees:
            try:
                start_date = employee.employee_work_info.date_joining or st_date
                end_date = datetime.today().date()

                existing_dates = set(
                    WorkRecords.objects.filter(employee_id=employee.id).values_list(
                        "date", flat=True
                    )
                )

                all_dates = {
                    start_date + timedelta(days=i)
                    for i in range((end_date - start_date).days)
                }
                missing_dates = all_dates - existing_dates

                work_records_to_create = [
                    WorkRecords(
                        employee_id=employee,
                        date=missing_date,
                        work_record_type="DFT",
                        shift_id=employee.employee_work_info.shift_id,
                    )
                    for missing_date in missing_dates
                ]

                if work_records_to_create:
                    WorkRecords.objects.bulk_create(
                        work_records_to_create, batch_size=500, ignore_conflicts=True
                    )

            except Exception as e:
                logger.exception(
                    "Error creating missing work records for employee_id=%s",
                    getattr(employee, "pk", employee),
                )
