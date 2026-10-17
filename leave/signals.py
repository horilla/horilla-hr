# leave/signals.py

import threading

from django.apps import apps
from django.db.models.signals import post_migrate, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from horilla.methods import get_horilla_model_class
from leave.models import LeaveRequest, LeaveRequestConditionApproval

if apps.is_installed("attendance"):

    @receiver(post_save, sender=LeaveRequest)
    def leaverequest_pre_save(sender, instance, **_kwargs):
        """
        Overriding LeaveRequest model save method
        """
        WorkRecords = get_horilla_model_class(
            app_label="attendance", model="workrecords"
        )
        if (
            instance.start_date == instance.end_date
            and instance.end_date_breakdown != instance.start_date_breakdown
        ):
            instance.end_date_breakdown = instance.start_date_breakdown
            super(LeaveRequest, instance).save()

        period_dates = instance.requested_dates()
        if instance.status in ["approved", "cancel_requested"]:
            for date in period_dates:
                try:
                    work_entry = (
                        WorkRecords.objects.filter(
                            date=date,
                            employee_id=instance.employee_id,
                        ).first()
                        if WorkRecords.objects.filter(
                            date=date,
                            employee_id=instance.employee_id,
                        ).exists()
                        else WorkRecords()
                    )
                    work_entry.employee_id = instance.employee_id
                    work_entry.is_leave_record = True
                    work_entry.leave_request_id = instance
                    work_entry.day_percentage = (
                        0.50
                        if instance.start_date == date
                        and instance.start_date_breakdown == "first_half"
                        or instance.end_date == date
                        and instance.end_date_breakdown == "second_half"
                        else 0.00
                    )
                    status = (
                        "CONF"
                        if instance.start_date == date
                        and instance.start_date_breakdown == "first_half"
                        or instance.end_date == date
                        and instance.end_date_breakdown == "second_half"
                        else "ABS"
                    )
                    work_entry.work_record_type = status
                    work_entry.date = date
                    # WorkRecords.message is max_length=30; the previous
                    # 36-char text raised DataError on PostgreSQL and
                    # aborted the transaction for every half-day leave.
                    work_entry.message = (
                        "Leave" if status == "ABS" else _("Half day: needs validation")
                    )
                    work_entry.save()

                except Exception as e:
                    print(e)

        else:
            for date in period_dates:
                WorkRecords._base_manager.filter(
                    is_leave_record=True,
                    date=date,
                    employee_id=instance.employee_id,
                ).delete()

    @receiver(pre_delete, sender=LeaveRequest)
    def leaverequest_pre_delete(sender, instance, **kwargs):
        from attendance.models import WorkRecords

        work_records = WorkRecords._base_manager.filter(
            leave_request_id=instance
        ).delete()


# @receiver(post_migrate)
def add_missing_leave_to_workrecords(sender, **kwargs):
    if sender.label not in ["attendance", "leave"]:
        return

    if not apps.is_installed("attendance"):
        return
    try:
        from attendance.models import WorkRecords
        from leave.models import LeaveRequest

        work_records = WorkRecords.objects.filter(
            is_leave_record=True, leave_request_id__isnull=True
        )
        if not work_records.exists():
            return

        leave_requests = LeaveRequest.objects.all()
        date_leave_map = {}

        for leave in leave_requests:
            for date in leave.requested_dates():
                key = (leave.employee_id, date)
                date_leave_map[key] = leave

        records_to_update = []
        for record in work_records:
            leave_request = date_leave_map.get((record.employee_id, record.date))
            if leave_request:
                record.leave_request_id = leave_request
                records_to_update.append(record)

        if records_to_update:
            WorkRecords.objects.bulk_update(
                records_to_update, ["leave_request_id"], batch_size=500
            )
            print(
                f"Successfully updated {len(records_to_update)} work records with leave information"
            )

    except Exception as e:
        print(f"Error in leave/work records sync: {e}")


@receiver(post_save, sender=LeaveRequestConditionApproval)
def auto_approve_self_approval_stage(sender, instance, created, **kwargs):
    """
    When an approver in the multiple-approval chain is the same employee who
    submitted the leave request, automatically approve their stage so the
    request is not stuck and can progress to the next approver.
    """
    if created and instance.manager_id == instance.leave_request_id.employee_id:
        sender.objects.filter(pk=instance.pk).update(is_approved=True)
