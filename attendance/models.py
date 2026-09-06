"""
models.py

This module is used to register models for recruitment app

"""

import contextlib
import datetime as dt
import json
from datetime import date, datetime, timedelta

import pandas as pd
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from attendance.methods.utils import (
    MONTH_MAPPING,
    attendance_date_validate,
    format_time,
    get_diff_dict,
    month_date_range,
    strtime_seconds,
    validate_hh_mm_ss_format,
    validate_time_format,
    validate_time_in_minutes,
)
from base.horilla_company_manager import HorillaCompanyManager
from base.methods import is_company_leave, is_holiday
from base.models import Company, EmployeeShift, EmployeeShiftDay, WorkType
from employee.models import Employee

# Create your models here.
from horilla.methods import get_horilla_model_class
from horilla.models import HorillaModel, upload_path
from horilla_audit.models import HorillaAuditInfo, HorillaAuditLog
from horilla_views.cbv_methods import render_template

# to skip the migration issue with the old migrations
_validate_time_in_minutes = validate_time_in_minutes


# Create your models here.


class AttendanceActivity(HorillaModel):
    """
    AttendanceActivity model
    """

    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="employee_attendance_activities",
        verbose_name=_("Employee"),
    )
    attendance_date = models.DateField(
        null=True,
        validators=[attendance_date_validate],
        verbose_name=_("Attendance Date"),
    )
    shift_day = models.ForeignKey(
        EmployeeShiftDay,
        null=True,
        on_delete=models.DO_NOTHING,
        verbose_name=_("Shift Day"),
    )
    in_datetime = models.DateTimeField(null=True)
    clock_in_date = models.DateField(null=True, verbose_name=_("In Date"))
    clock_in = models.TimeField(verbose_name=_("Check In"))
    clock_out_date = models.DateField(null=True, verbose_name=_("Out Date"))
    out_datetime = models.DateTimeField(null=True)
    clock_out = models.TimeField(null=True, verbose_name=_("Check Out"))
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )

    class Meta:
        """
        Meta class to add some additional options
        """

        ordering = ["-attendance_date", "employee_id__employee_first_name", "clock_in"]

    def get_status(self):
        """
        Display status
        """

        DAY = [
            ("monday", _("Monday")),
            ("tuesday", _("Tuesday")),
            ("wednesday", _("Wednesday")),
            ("thursday", _("Thursday")),
            ("friday", _("Friday")),
            ("saturday", _("Saturday")),
            ("sunday", _("Sunday")),
        ]
        return dict(DAY).get(self.shift_day.day)

    def get_delete_attendance(self):
        """
        for delete button
        """

        return render_template(
            path="cbv/attendance_activity/delete_action.html",
            context={"instance": self},
        )

    def attendance_detail_subtitle(self):
        """
        Return subtitle containing both department and job position information.
        """
        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def attendance_detail_view(self):
        """
        for detail view of page
        """
        url = reverse("attendance-activity-single-view", kwargs={"pk": self.pk})
        return url

    def diff_cell(self):
        if self.clock_out == None:
            return 'style="background-color: #FFE4B3"'

    def detail_view_delete_attendance(self):
        """
        for delete button
        """

        return render_template(
            path="cbv/attendance_activity/detail_delete_action.html",
            context={"instance": self},
        )

    def duration_format_time(self, seconds):
        """
        This method is used to format seconds to H:M:S and return it
        args:
            seconds : seconds
        """
        hour = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int((seconds % 3600) % 60)
        return f"{hour:02d}:{minutes:02d}:{seconds:02d}"

    def duration(self):
        """
        Duration calc b/w in-out method
        """

        if not self.clock_out or not self.clock_out_date:
            self.clock_out_date = datetime.today().date()
            self.clock_out = datetime.now().time()

        clock_in_datetime = datetime.combine(self.clock_in_date, self.clock_in)
        clock_out_datetime = datetime.combine(self.clock_out_date, self.clock_out)

        time_difference = clock_out_datetime - clock_in_datetime

        return time_difference.total_seconds()

    def duration_format(self):
        """
        Function to return the duration time in hh:mm:ss
        """
        total_seconds = self.duration()
        formatted_duration = self.duration_format_time(total_seconds)

        return formatted_duration

    def __str__(self):
        return f"{self.employee_id} - {self.attendance_date} - {self.clock_in} - {self.clock_out}"


class BatchAttendance(HorillaModel):
    """
    Batch attendance model
    """

    title = models.CharField(max_length=150, verbose_name=_("Title"))

    def __str__(self):
        return f"{self.title}-{self.id}"


class Attendance(HorillaModel):
    """
    Attendance model
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    status = [
        ("create_request", _("Create Request")),
        ("update_request", _("Update Request")),
        ("created_request", _("Created Request")),
    ]

    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        null=True,
        related_name="employee_attendances",
        verbose_name=_("Employee"),
    )
    attendance_date = models.DateField(
        null=False,
        validators=[attendance_date_validate],
        verbose_name=_("Attendance date"),
    )
    shift_id = models.ForeignKey(
        EmployeeShift, on_delete=models.SET_NULL, null=True, verbose_name=_("Shift")
    )
    work_type_id = models.ForeignKey(
        WorkType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,  # 796
        verbose_name=_("Work Type"),
    )
    attendance_day = models.ForeignKey(
        EmployeeShiftDay,
        on_delete=models.DO_NOTHING,
        null=True,
        verbose_name=_("Attendance day"),
    )
    attendance_clock_in_date = models.DateField(
        null=True, verbose_name=_("Check-In Date")
    )
    attendance_clock_in = models.TimeField(
        null=True, verbose_name=_("Check-In"), help_text=_("First Check-In Time")
    )
    attendance_clock_out_date = models.DateField(
        null=True, verbose_name=_("Check-Out Date")
    )
    attendance_clock_out = models.TimeField(
        null=True, verbose_name=_("Check-Out"), help_text=_("Last Check-Out Time")
    )
    attendance_worked_hour = models.CharField(
        null=True,
        default="00:00",
        max_length=10,
        validators=[validate_time_format],
        verbose_name=_("Worked Hours"),
    )
    minimum_hour = models.CharField(
        max_length=10,
        default="00:00",
        validators=[validate_time_format],
        verbose_name=_("Minimum hour"),
    )
    batch_attendance_id = models.ForeignKey(
        BatchAttendance,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name=_("Batch Attendance"),
    )
    attendance_overtime = models.CharField(
        default="00:00",
        validators=[validate_time_format],
        max_length=10,
        verbose_name=_("Overtime"),
    )
    attendance_overtime_approve = models.BooleanField(
        default=False, verbose_name=_("Overtime Approve")
    )
    attendance_validated = models.BooleanField(
        default=False, verbose_name=_("Attendance Validate")
    )
    at_work_second = models.IntegerField(null=True, blank=True)
    overtime_second = models.IntegerField(
        null=True, blank=True, verbose_name=_("Overtime In Second")
    )
    approved_overtime_second = models.IntegerField(default=0)
    is_validate_request = models.BooleanField(
        default=False, verbose_name=_("Is validate request")
    )
    is_bulk_request = models.BooleanField(default=False, editable=False)
    is_validate_request_approved = models.BooleanField(
        default=False, verbose_name=_("Is validate request approved")
    )
    request_description = models.TextField(
        null=True, verbose_name=_("Request Description")
    )
    request_type = models.CharField(
        max_length=18, null=True, choices=status, default="update_request"
    )
    is_holiday = models.BooleanField(default=False)
    requested_data = models.JSONField(null=True, editable=False)
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Approved By"),
        editable=False,
    )
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )

    def get_instance_id(self):
        return self.id

    def diff_cell(self):
        if self.request_type == "created_request":
            return 'style="background-color: #FFE4B3"'

    def status_col(self):
        """
        This method for get custome coloumn for rating.
        """

        return render_template(
            path="cbv/attendance_request/status.html",
            context={"instance": self},
        )

    def my_attendance_subtitle(self):
        """
        Detail view subtitle
        """

        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def my_attendance_detail(self):
        """
        detail view
        """

        url = reverse("my-attendance-detail", kwargs={"pk": self.pk})

        return url

    def attendance_detail_view(self):
        """
        detail view
        """

        url = reverse("attendances-tab-detail-view", kwargs={"pk": self.pk})

        return url

    class Meta:
        """
        Meta class to add some additional options
        """

        unique_together = ("employee_id", "attendance_date")
        # The unique_together above yields a (employee_id, attendance_date)
        # index, which serves lookups that pin an employee. It cannot serve a
        # date-range scan that does not -- which is what every dashboard and
        # report does -- because attendance_date is not the leading column.
        indexes = [
            models.Index(
                fields=["attendance_date"],
                name="attendance_date_idx",
            ),
            # Validation queues and payroll both filter unvalidated rows
            # within a period; date leads because it is the selective half.
            models.Index(
                fields=["attendance_date", "attendance_validated"],
                name="attendance_date_validated_idx",
            ),
        ]
        permissions = [
            ("change_validateattendance", "Validate Attendance"),
            ("change_approveovertime", "Change Approve Overtime"),
        ]
        ordering = [
            "-attendance_date",
            "employee_id__employee_first_name",
            "attendance_clock_in",
        ]
        verbose_name = _("Attendance")
        verbose_name_plural = _("Attendances")

    def check_min_ot(self):
        """
        Method to check the min ot for the attendance
        """

    def is_night_shift(self):
        """
        check is night shift or not
        """
        day = self.attendance_day
        if day is None:
            return False
        schedule = day.day_schedule.filter(shift_id=self.shift_id).first()
        if not schedule:
            return False
        return schedule.is_night_shift

    def __str__(self) -> str:
        return f"{self.employee_id.employee_first_name} \
            {self.employee_id.employee_last_name} - {self.attendance_date}"

    def attendance_actions(self):
        """
        method for rendering actions(edit,delete)
        """

        return render_template(
            path="cbv/attendances/attendance_actions.html",
            context={"instance": self},
        )

    def comment_col(self):
        """
        This method for get custom coloumn for comment.
        """

        return render_template(
            path="cbv/attendance_request/comment.html",
            context={"instance": self},
        )

    def attendance_detail_activity_col(self):
        """
        this method is used to return attendance detail view activity custom col
        """

        return render_template(
            path="cbv/attendances/detail_view_activity_col.html",
            context={"instance": self},
        )

    def request_actions(self):
        """
        This method for get custom coloumn for comment.
        """

        return render_template(
            path="cbv/attendance_request/request_actions.html",
            context={"instance": self},
        )

    def detail_actions(self):
        """
        This method is used to render the action buttons shown in the
        attendance detail view modal (All Attendances tab). Mirrors the
        row's Edit action (see AttendanceListTab.actions in
        attendance/cbv/attendance_request.py) using the modal's labeled
        pill-button convention.
        """

        return render_template(
            path="cbv/attendance_request/detail_actions.html",
            context={"instance": self},
        )

    def request_options(self):
        """
        This method for get custom options for request.
        """
        return render_template(
            path="cbv/attendance_request/attendance_request_option.html",
            context={"instance": self},
        )

    def validate_detail_view(self):
        """
        detail view of validate tab
        """
        url = reverse("validate-detail-view", kwargs={"pk": self.pk})
        return url

    def individual_validate_detail_view(self):
        """
        detail view of validate tab
        """
        url = reverse("individual-validate-detail-view", kwargs={"pk": self.pk})
        return url

    def ot_detail_view(self):
        """
        detail view of OT tab
        """
        url = reverse("ot-detail-view", kwargs={"pk": self.pk})
        return url

    def validated_detail_view(self):
        """
        detail view of validated tab
        """
        url = reverse("validated-detail-view", kwargs={"pk": self.pk})
        return url

    def detail_view(self):
        """
        deteil view of requested attendances
        """
        url = reverse("validate-attendance-request", kwargs={"attendance_id": self.pk})
        return url

    def change_attendance(self):
        """
        Edit url
        """
        url = reverse("update-attendance-request", kwargs={"pk": self.pk})
        return url

    def ot_approve(self):
        """
        method for rendering approve OT
        """
        minot = strtime_seconds("00:30")
        condition = AttendanceValidationCondition.objects.first()
        if condition is not None:
            minot = strtime_seconds(condition.minimum_overtime_to_approve)

        return render_template(
            path="cbv/attendances/ot_confirmation.html",
            context={"instance": self, "minot": minot},
        )

    def validate_actions(self):
        """
        combined actions column for validate tab: validate + edit + delete
        """

        return render_template(
            path="cbv/attendances/validate_actions.html",
            context={"instance": self},
        )

    def ot_actions(self):
        """
        combined actions column for OT tab: approve OT + edit + delete
        """
        minot = strtime_seconds("00:30")
        condition = AttendanceValidationCondition.objects.first()
        if condition is not None:
            minot = strtime_seconds(condition.minimum_overtime_to_approve)

        return render_template(
            path="cbv/attendances/ot_actions.html",
            context={"instance": self, "minot": minot},
        )

    def validate_detail_actions(self):
        """
        detail view actions of validate tab
        """

        return render_template(
            path="cbv/attendances/validate_tab_action.html",
            context={"instance": self},
        )

    def ot_detail_actions(self):
        """
        detail view actions of OT tab
        """

        minot = strtime_seconds("00:30")
        condition = AttendanceValidationCondition.objects.first()
        if condition is not None:
            minot = strtime_seconds(condition.minimum_overtime_to_approve)

        return render_template(
            path="cbv/attendances/ot_tab_action.html",
            context={"instance": self, "minot": minot},
        )

    def validated_detail_actions(self):
        """
        detail view actions of validated tab
        """

        return render_template(
            path="cbv/attendances/validated_tab_action.html",
            context={"instance": self},
        )

    def validate_button(self):
        """
        detail view actions of validated tab
        """

        return render_template(
            path="cbv/attendances/validate_button.html",
            context={"instance": self},
        )

    def attendances_detail_subtitle(self):
        """
        Return subtitle containing both department and job position information.
        """
        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def activities(self):
        """
        This method is used to return the activites and count of activites comes for an attendance
        """
        activities = AttendanceActivity.objects.filter(
            attendance_date=self.attendance_date, employee_id=self.employee_id
        )
        return {"query": activities, "count": activities.count()}

    def requested_fields(self):
        """
        This method will returns the value difference fields
        """
        keys = []
        if self.requested_data is not None:
            data = json.loads(self.requested_data)
            diffs = get_diff_dict(self.serialize(), data)
            keys = diffs.keys()
        return keys

    def get_last_clock_out(self, null_activity=False):
        """
        This method is used to get the last attendance activity if exists
        """
        activities = AttendanceActivity.objects.filter(
            employee_id=self.employee_id,
            attendance_date=self.attendance_date,
            clock_out__isnull=null_activity,
        ).order_by("id")
        return activities.last()

    def get_at_work_from_activities(self):
        """
        This method is used to retun the at work calculated from the activities
        """
        activities = AttendanceActivity.objects.filter(
            attendance_date=self.attendance_date, employee_id=self.employee_id
        ).order_by("clock_in")
        at_work_seconds = 0
        now = datetime.now()
        for activity in activities:
            out_time = activity.clock_out
            if out_time is None:
                combined_out = datetime.combine(
                    now, dt.time(hour=now.hour, minute=now.minute, second=now.second)
                )
            else:
                combined_out = datetime.combine(activity.clock_out_date, out_time)
            in_time = activity.clock_in
            combined_in = datetime.combine(activity.clock_in_date, in_time)
            diffs = combined_out - combined_in
            at_work_seconds = at_work_seconds + diffs.total_seconds()
        return at_work_seconds

    def hours_pending(self):
        """
        This method will returns difference between minimum_hour and attendance_worked_hour
        """
        minimum_hours = strtime_seconds(self.minimum_hour)
        worked_hour = strtime_seconds(self.attendance_worked_hour)
        pending_seconds = minimum_hours - worked_hour
        if pending_seconds < 0:
            return "00:00"
        pending_hours = format_time(pending_seconds)
        return pending_hours

    def adjust_minimum_hour(self):
        """
        Set minimum_hour to 00:00 if the attendance date falls on a holiday or company leave.
        """
        if is_holiday(self.attendance_date, self.employee_id) or is_company_leave(
            self.attendance_date
        ):
            self.minimum_hour = "00:00"
            self.is_holiday = True
        else:
            self.is_holiday = False

    def update_attendance_overtime(self):
        """
        Calculate and update attendance overtime and worked seconds.
        """
        self.attendance_overtime = format_time(
            max(
                0,
                (
                    strtime_seconds(self.attendance_worked_hour)
                    - strtime_seconds(self.minimum_hour)
                ),
            )
        )
        self.at_work_second = strtime_seconds(self.attendance_worked_hour)
        self.overtime_second = strtime_seconds(self.attendance_overtime)

    def handle_overtime_conditions(self):
        condition = AttendanceValidationCondition.objects.first()
        if self.is_validate_request:
            self.is_validate_request_approved = self.attendance_validated = False

        if condition:
            # Handle overtime cutoff
            if condition.overtime_cutoff:
                cutoff_seconds = strtime_seconds(condition.overtime_cutoff)
                if self.overtime_second > cutoff_seconds:
                    self.overtime_second = cutoff_seconds
                    self.attendance_overtime = format_time(cutoff_seconds)

            # Auto-approve overtime if conditions are met
            if condition.auto_approve_ot and self.overtime_second >= strtime_seconds(
                condition.minimum_overtime_to_approve
            ):
                self.attendance_overtime_approve = True

    # def save(self, *args, **kwargs):
    #     self.update_attendance_overtime()
    #     self.attendance_day = EmployeeShiftDay.objects.get(
    #         day=self.attendance_date.strftime("%A").lower()
    #     )
    #     prev_attendance_approved = False
    #     self.adjust_minimum_hour()

    #     # Handle overtime cutoff and auto-approval
    #     self.handle_overtime_conditions()

    #     if self.pk is not None:
    #         # Get the previous values of the boolean field
    #         prev_state = Attendance.objects.get(pk=self.pk)
    #         prev_attendance_approved = prev_state.attendance_overtime_approve

    #     # super().save(*args, **kwargs)  #commend this line, it take too much time to complete
    #     employee_ot = self.employee_id.employee_overtime.filter(
    #         month=self.attendance_date.strftime("%B").lower(),
    #         year=self.attendance_date.year,
    #     ).first()
    #     if employee_ot:
    #         # Update if exists
    #         self.update_ot(employee_ot)
    #     else:
    #         # Create and update in one call
    #         employee_ot = self.create_ot()
    #         self.update_ot(employee_ot)
    #     approved = self.attendance_overtime_approve
    #     attendance_account = self.employee_id.employee_overtime.filter(
    #         month=self.attendance_date.strftime("%B").lower(),
    #         year=self.attendance_date.year,
    #     ).first()
    #     total_ot_seconds = attendance_account.overtime_second
    #     if approved and prev_attendance_approved is False:
    #         self.approved_overtime_second = self.overtime_second
    #         total_ot_seconds = total_ot_seconds + self.approved_overtime_second
    #     elif not approved:
    #         total_ot_seconds = total_ot_seconds - self.approved_overtime_second
    #         self.approved_overtime_second = 0
    #     attendance_account.overtime = format_time(total_ot_seconds)
    #     attendance_account.save()
    #     super().save(*args, **kwargs)
    #     self.first_save = False

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old = None

        if not self.attendance_day:
            self.attendance_day = EmployeeShiftDay.objects.get(
                day=self.attendance_date.strftime("%A").lower()
            )

        if not is_new:
            old = Attendance.objects.only(
                "at_work_second",
                "approved_overtime_second",
                "minimum_hour",
                "attendance_overtime_approve",
            ).get(pk=self.pk)

            old_work = old.at_work_second or 0
            old_approved_ot = old.approved_overtime_second or 0
            old_approved_flag = old.attendance_overtime_approve or False

            old_min = strtime_seconds(old.minimum_hour)
            old_pending_today = max(0, old_min - old_work)
        else:
            old_work = 0
            old_approved_ot = 0
            old_pending_today = 0
            old_approved_flag = False

        self.update_attendance_overtime()
        self.adjust_minimum_hour()
        self.handle_overtime_conditions()

        if self.attendance_overtime_approve and not old_approved_flag:
            self.approved_overtime_second = self.overtime_second
        elif not self.attendance_overtime_approve:
            self.approved_overtime_second = 0
        else:
            self.approved_overtime_second = old_approved_ot

        new_work = self.at_work_second or 0
        new_approved_ot = self.approved_overtime_second or 0

        new_min = strtime_seconds(self.minimum_hour)
        new_pending_today = max(0, new_min - new_work)

        diff_work = new_work - old_work
        diff_approved_ot = new_approved_ot - old_approved_ot
        diff_pending = new_pending_today - old_pending_today

        super().save(*args, **kwargs)

        if diff_work == diff_approved_ot == diff_pending == 0:
            return

        month = self.attendance_date.strftime("%B").lower()
        year = self.attendance_date.year

        with transaction.atomic():
            ot, _ = AttendanceOverTime.objects.get_or_create(
                employee_id=self.employee_id,
                month=month,
                year=year,
                defaults={
                    "hour_account_second": 0,
                    "hour_pending_second": 0,
                    "overtime_second": 0,
                },
            )

            AttendanceOverTime.objects.filter(pk=ot.pk).update(
                hour_account_second=F("hour_account_second") + diff_work,
                overtime_second=F("overtime_second") + diff_approved_ot,
                hour_pending_second=F("hour_pending_second") + diff_pending,
            )

            ot.refresh_from_db(
                fields=["hour_account_second", "hour_pending_second", "overtime_second"]
            )
            ot.worked_hours = format_time(ot.hour_account_second or 0)
            ot.pending_hours = format_time(ot.hour_pending_second or 0)
            ot.overtime = format_time(ot.overtime_second or 0)
            ot.save(update_fields=["worked_hours", "pending_hours", "overtime"])

    def serialize(self):
        """
        Used to serialize attendance instance
        """
        # Return a dictionary containing the data you want to store
        # strftime("%d %b %Y") date
        # strftime("%I:%M %p") time
        serialized_data = {
            "employee_id": self.employee_id.id,
            "attendance_date": str(self.attendance_date),
            "attendance_clock_in_date": str(self.attendance_clock_in_date),
            "attendance_clock_in": str(self.attendance_clock_in),
            "attendance_clock_out": str(self.attendance_clock_out),
            "attendance_clock_out_date": str(self.attendance_clock_out_date),
            "shift_id": self.shift_id.id if self.shift_id else "",
            "work_type_id": self.work_type_id.id if self.work_type_id else "",
            "attendance_worked_hour": self.attendance_worked_hour,
            "minimum_hour": self.minimum_hour,
            "batch_attendance_id": (
                self.batch_attendance_id.id if self.batch_attendance_id else ""
            ),
            # Add other fields you want to store
        }
        return serialized_data

    def delete(self, *args, **kwargs):
        # Custom delete logic
        # Perform additional operations before deleting the object
        with contextlib.suppress(Exception):
            AttendanceActivity.objects.filter(
                attendance_date=self.attendance_date, employee_id=self.employee_id
            ).delete()
            employee_ot = self.employee_id.employee_overtime.filter(
                month=self.attendance_date.strftime("%B").lower(),
                year=self.attendance_date.strftime("%Y"),
            )
            if employee_ot.exists():
                self.update_ot(employee_ot.first())
        # Call the superclass delete() method to delete the object
        super().delete(*args, **kwargs)

        # Perform additional operations after deleting the object

    def create_ot(self):
        """
        Create a new Hours Balance instance if it doesn't exist for a specific month and year.
        Returns:
            AttendanceOverTime: The created or fetched AttendanceOverTime instance.
        """
        # Create or fetch the AttendanceOverTime instance
        employee_ot, created = AttendanceOverTime.objects.get_or_create(
            employee_id=self.employee_id,
            month=self.attendance_date.strftime("%B").lower(),
            year=self.attendance_date.year,
        )

        # Update only if the fields are available
        if self.attendance_overtime_approve:
            employee_ot.overtime = self.attendance_overtime

        if self.attendance_validated:
            employee_ot.hour_account = self.attendance_worked_hour

        employee_ot.save()
        return employee_ot

    def update_ot(self, employee_ot):
        """
        Update the hour account for the given employee.

        Args:
            employee_ot (obj): AttendanceOverTime instance
        """
        if apps.is_installed("leave"):
            approved_leave_requests = self.employee_id.leaverequest_set.filter(
                start_date__lte=self.attendance_date,
                end_date__gte=self.attendance_date,
                status="approved",
            )
        else:
            approved_leave_requests = []

        # Create exclude condition using Q objects
        exclude_condition = Q()
        if approved_leave_requests:
            # Combine multiple conditions for the exclude clause
            for leave in approved_leave_requests:
                exclude_condition |= Q(
                    attendance_date__range=(leave.start_date, leave.end_date)
                )

        # Filter month attendances in a single query
        month_attendances = (
            Attendance.objects.filter(
                employee_id=self.employee_id,
                # Range rather than __month/__year: those wrap the column in a
                # database function, which a B-tree index on attendance_date
                # cannot serve.
                attendance_date__range=month_date_range(
                    self.attendance_date.year, self.attendance_date.month
                ),
                attendance_validated=True,
            )
            .exclude(exclude_condition)
            .values("minimum_hour", "at_work_second")
        )

        # Calculate hour balance and hours pending in a single loop
        hour_balance = 0
        minimum_hour_second = 0
        for attendance in month_attendances:
            required_work_second = strtime_seconds(attendance["minimum_hour"])
            at_work_second = min(required_work_second, attendance["at_work_second"])
            hour_balance += at_work_second
            minimum_hour_second += required_work_second

        hours_pending = minimum_hour_second - hour_balance
        employee_ot.worked_hours = format_time(hour_balance)
        employee_ot.pending_hours = format_time(hours_pending)
        employee_ot.save()

        return employee_ot

    def clean(self, *args, **kwargs):
        super().clean(*args, **kwargs)
        now = datetime.now().time()
        today = datetime.today().date()

        # Convert to time if it's a string
        if isinstance(self.attendance_clock_out, str):
            out_time = datetime.strptime(self.attendance_clock_out, "%H:%M:%S").time()
        else:
            out_time = self.attendance_clock_out

        if (
            self.attendance_clock_in_date
            and self.attendance_clock_in_date < self.attendance_date
        ):
            raise ValidationError(
                {
                    "attendance_clock_in_date": "Attendance check-in date cannot be earlier than attendance date"
                }
            )

        if (
            self.attendance_clock_out_date
            and self.attendance_clock_in_date
            and self.attendance_clock_out_date < self.attendance_clock_in_date
        ):
            raise ValidationError(
                {
                    "attendance_clock_out_date": "Attendance check-out date cannot be earlier than check-in date"
                }
            )

        if self.attendance_clock_out_date and self.attendance_clock_out_date >= today:
            if out_time > now:
                raise ValidationError(
                    {"attendance_clock_out": "Check-out time cannot be in the future"}
                )


class AttendanceRequestFile(HorillaModel):
    file = models.FileField(upload_to=upload_path)


class AttendanceRequestComment(HorillaModel):
    """
    AttendanceRequestComment Model
    """

    request_id = models.ForeignKey(Attendance, on_delete=models.CASCADE)
    employee_id = models.ForeignKey(Employee, on_delete=models.CASCADE)
    files = models.ManyToManyField(AttendanceRequestFile, blank=True)
    comment = models.TextField(null=True, verbose_name=_("Comment"), max_length=255)

    def __str__(self) -> str:
        return f"{self.comment}"


class AttendanceOverTime(HorillaModel):
    """
    AttendanceOverTime model
    """

    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="employee_overtime",
        verbose_name=_("Employee"),
    )
    month = models.CharField(
        max_length=10,
        verbose_name=_("Month"),
    )
    month_sequence = models.PositiveSmallIntegerField(default=0)
    year = models.CharField(
        default=datetime.now().strftime("%Y"),
        null=True,
        max_length=10,
        verbose_name=_("Year"),
    )
    worked_hours = models.CharField(
        max_length=10,
        default="00:00",
        null=True,
        validators=[validate_time_format],
        verbose_name=_("Worked Hours"),
    )
    pending_hours = models.CharField(
        max_length=10,
        default="00:00",
        null=True,
        validators=[validate_time_format],
        verbose_name=_("Pending Hours"),
    )
    overtime = models.CharField(
        max_length=20,
        default="00:00",
        validators=[validate_time_format],
        verbose_name=_("Overtime Hours"),
    )
    hour_account_second = models.IntegerField(
        default=0,
        null=True,
        verbose_name=_("Worked Seconds"),
    )
    hour_pending_second = models.IntegerField(
        default=0,
        null=True,
        verbose_name=_("Pending Seconds"),
    )
    overtime_second = models.IntegerField(
        default=0,
        null=True,
        verbose_name=_("Overtime Seconds"),
    )
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )

    class Meta:
        """
        Meta class to add some additional options
        """

        unique_together = [("employee_id"), ("month"), ("year")]
        ordering = ["-year", "-month_sequence"]
        verbose_name = _("Hours Balance")
        verbose_name_plural = _("Hours Balances")

    def __str__(self):
        return f"{self.employee_id} - {self.month}"

    def get_month_capitalized(self):
        """
        capitalize month
        """
        return self.month.capitalize()

    def edit_url_overtime(self):
        """
        Edit url
        """

        url = reverse("attendance-overtime-update", kwargs={"obj_id": self.pk})

        return url

    def delete_url_overtime(self):
        """
        delete url
        """

        url = reverse("attendance-overtime-delete", kwargs={"obj_id": self.pk})

        return url

    def hour_actions(self):
        """
        actions in hour account

        """

        return render_template(
            path="cbv/hour_account/hour_actions.html",
            context={"instance": self},
        )

    def hour_options(self):
        """
        options in hour account

        """

        return render_template(
            path="cbv/hour_account/hour_options.html",
            context={"instance": self},
        )

    def hour_account_subtitle(self):
        """
        Detail view subtitle
        """

        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def hour_account_detail(self):
        """
        detail view
        """

        url = reverse("hour-account-detail-view", kwargs={"pk": self.pk})

        return url

    def hour_detail_actions(self):
        """
        actions in hour account detail view

        """

        return render_template(
            path="cbv/hour_account/hour_detail_action.html",
            context={"instance": self},
        )

    def clean(self):
        try:
            year = int(self.year)
            if not (1900 <= year <= 2100):
                raise ValidationError(
                    {"year": _("Year must be an integer value between 1900 and 2100")}
                )
        except (ValueError, TypeError):
            raise ValidationError(
                {"year": _("Year must be an integer value between 1900 and 2100")}
            )

    def month_days(self):
        """
        this method is used to create new AttendanceOvertime's instance if there
        is no existing for a specific month and year
        """
        month = self.month_sequence + 1
        year = int(self.year)
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        return start_date, end_date

    def not_validated_hrs(self):
        """
        This method will return not validated hours in a month
        """
        # Range rather than __month/__year so an index on attendance_date can
        # be used, and Sum() rather than pulling every row into Python to add
        # up -- the database can do this without transferring the rows.
        hrs_to_vlaidate = (
            Attendance.objects.filter(
                attendance_date__range=month_date_range(
                    self.year, MONTH_MAPPING[self.month]
                ),
                employee_id=self.employee_id,
                attendance_validated=False,
            ).aggregate(total=Sum("at_work_second"))["total"]
            or 0
        )
        return format_time(hrs_to_vlaidate)

    def not_approved_ot_hrs(self):
        """
        This method will return the overtime hours to be approved
        """
        hrs_to_approve = (
            Attendance.objects.filter(
                attendance_date__range=month_date_range(
                    self.year, MONTH_MAPPING[self.month]
                ),
                employee_id=self.employee_id,
                attendance_validated=True,
                attendance_overtime_approve=False,
                overtime_second__isnull=False,
            ).aggregate(total=Sum("overtime_second"))["total"]
            or 0
        )
        return format_time(hrs_to_approve)

    def get_month_index(self):
        """
        This method will return the index of the month
        """
        return MONTH_MAPPING[self.month]

    # def save(self, *args, **kwargs):
    #     self.hour_account_second = strtime_seconds(self.worked_hours)
    #     self.hour_pending_second = strtime_seconds(self.pending_hours)
    #     self.overtime_second = strtime_seconds(self.overtime)
    #     month_name = self.month.split("-")[0]
    #     months = [
    #         "january",
    #         "february",
    #         "march",
    #         "april",
    #         "may",
    #         "june",
    #         "july",
    #         "august",
    #         "september",
    #         "october",
    #         "november",
    #         "december",
    #     ]
    #     self.month_sequence = months.index(month_name)
    #     super().save(*args, **kwargs)

    def save(self, *args, **kwargs):
        self.worked_hours = format_time(self.hour_account_second or 0)
        self.pending_hours = format_time(self.hour_pending_second or 0)
        self.overtime = format_time(self.overtime_second or 0)

        month_name = self.month.split("-")[0]
        months = [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
        self.month_sequence = months.index(month_name)

        super().save(*args, **kwargs)


class AttendanceLateComeEarlyOut(HorillaModel):
    """
    AttendanceLateComeEarlyOut model
    """

    choices = [
        ("late_come", _("Late Arrival")),
        ("early_out", _("Early Departure")),
    ]

    attendance_id = models.ForeignKey(
        Attendance,
        on_delete=models.PROTECT,
        related_name="late_come_early_out",
        verbose_name=_("Attendance"),
    )
    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="late_come_early_out",
        verbose_name=_("Employee"),
        editable=False,
    )
    type = models.CharField(max_length=20, choices=choices, verbose_name=_("Type"))
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def get_penalties_count(self):
        """
        This method is used to return the total penalties in the late early instance
        """
        return self.penaltyaccounts_set.count()

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)
        self.employee_id = self.attendance_id.employee_id
        super().save(*args, **kwargs)

    class Meta:
        """
        Meta class to add some additional options
        """

        unique_together = [("attendance_id"), ("type")]
        ordering = ["-attendance_id__attendance_date"]

    def get_type(self):
        """
        Display work type
        """
        choices = [
            ("late_come", _("Late Arrival")),
            ("early_out", _("Early Departure")),
        ]
        return dict(choices).get(self.type)

    def penalities_column(self):
        """
        To get penalities

        """

        return render_template(
            path="cbv/late_come_and_early_out/penality.html",
            context={"instance": self},
        )

    def actions_column(self):
        """
        actions in hour account

        """

        return render_template(
            path="cbv/late_come_and_early_out/actions_column.html",
            context={"instance": self},
        )

    def detail_actions(self):
        """
        actions in hour account

        """

        return render_template(
            path="cbv/late_come_and_early_out/detail_action.html",
            context={"instance": self},
        )

    def late_come_subtitle(self):
        """
        Detail view subtitle
        """

        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def attendance_validated_check(self):
        if self.attendance_id.attendance_validated == True:
            return _("Yes")
        else:
            return _("No")

    def late_come_detail(self):
        """
        detail view
        """

        url = reverse("late-in-early-out-single-view", kwargs={"pk": self.pk})

        return url

    def __str__(self) -> str:
        return f"{self.attendance_id.employee_id.employee_first_name} \
            {self.attendance_id.employee_id.employee_last_name} - {self.type}"


class AttendanceValidationCondition(HorillaModel):
    """
    AttendanceValidationCondition model
    """

    validation_at_work = models.CharField(
        max_length=10,
        validators=[validate_time_format],
        verbose_name=_("Worked Hours Auto Approve Till"),
    )
    minimum_overtime_to_approve = models.CharField(
        blank=True, null=True, max_length=10, validators=[validate_time_format]
    )
    overtime_cutoff = models.CharField(
        blank=True, null=True, max_length=10, validators=[validate_time_format]
    )
    auto_approve_ot = models.BooleanField(
        default=False, verbose_name=_("Auto Approve OT")
    )
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))
    objects = HorillaCompanyManager()

    def clean(self):
        """
        This method is used to perform some custom validations
        """
        super().clean()
        if not self.id and AttendanceValidationCondition.objects.exists():
            raise ValidationError(_("You cannot add more conditions."))

    def break_point_actions(self):
        """
        actions in hour account

        """

        return render_template(
            path="cbv/settings/break_point_action.html",
            context={"instance": self},
        )


class GraceTime(HorillaModel):
    """
    Model for saving Grace time
    """

    allowed_time = models.CharField(
        default="00:00:00",
        validators=[validate_hh_mm_ss_format],
        max_length=10,
        verbose_name=_("Allowed Time"),
    )
    allowed_time_in_secs = models.IntegerField()
    allowed_clock_in = models.BooleanField(
        default=True,
        help_text=_("Allcocate this grace time for Check-In Attendance"),
        verbose_name=_("Allowed Clock-In"),
    )
    allowed_clock_out = models.BooleanField(
        default=False,
        help_text=_("Allcocate this grace time for Check-Out Attendance"),
        verbose_name=_("Allowed Clock-Out"),
    )
    is_default = models.BooleanField(default=False)

    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))
    objects = HorillaCompanyManager()

    def __str__(self) -> str:
        return str(f"{self.allowed_time} - Hours")

    def get_instance_id(self):
        return self.id

    def is_active_col(self):
        """
        This method for get custome coloumn .
        """

        return render_template(
            path="cbv/settings/is_active_col_grace_time.html",
            context={"instance": self},
        )

    def allowed_time_col(self):
        """
        Allowed time col
        """
        return f"{self.allowed_time} Hours"

    def is_default_col(self):
        """
        Allowed time col
        """
        return _("Yes") if self.is_default else _("No")

    def action_col(self):
        """
        This method for get custome coloumn .
        """

        return render_template(
            path="cbv/settings/grace_time_default_action.html",
            context={"instance": self},
        )

    def applicable_on_clock_in_col(self):
        """
        This method for get custom column .
        """

        return render_template(
            path="cbv/settings/applicable_on_clock_in_col.html",
            context={"instance": self},
        )

    def applicable_on_clock_out_col(self):
        """
        This method for get custom column .
        """

        return render_template(
            path="cbv/settings/applicable_on_clock_out_col.html",
            context={"instance": self},
        )

    def get_shifts_display(self):
        """
        This method for get custom column .
        """

        return render_template(
            path="cbv/settings/grace_time_shift.html",
            context={"instance": self},
        )

    def clean(self):
        """
        This method is used to perform some custom validations
        """
        super().clean()
        if self.is_default:
            if GraceTime.objects.filter(is_default=True).exclude(id=self.id).exists():
                raise ValidationError(
                    _("There is already a default grace time that exists.")
                )

        allowed_time = self.allowed_time
        is_default = self.is_default
        exclude_default = not is_default

        if (
            GraceTime.objects.filter(allowed_time=allowed_time)
            .exclude(is_default=exclude_default)
            .exclude(id=self.id)
            .exists()
        ):
            raise ValidationError(
                {
                    "allowed_time": _(
                        "There is already an existing grace time with this allowed time."
                    )
                }
            )

    def save(self, *args, **kwargs):
        allowed_time = self.allowed_time
        hours, minutes, secs = allowed_time.split(":")

        hours_int = int(hours)
        minutes_int = int(minutes)
        secs_int = int(secs)

        hours_str = f"{hours_int:02d}"
        minutes_str = f"{minutes_int:02d}"
        secs_str = f"{secs_int:02d}"

        self.allowed_time = f"{hours_str}:{minutes_str}:{secs_str}"
        self.allowed_time_in_secs = hours_int * 3600 + minutes_int * 60 + secs_int
        super().save(*args, **kwargs)


class AttendanceGeneralSetting(HorillaModel):
    """
    AttendanceGeneralSettings
    """

    time_runner = models.BooleanField(default=True)
    enable_check_in = models.BooleanField(
        default=True,
        verbose_name=_("Enable Check in/Check out"),
        help_text=_(
            "Enabling this feature allows employees to record their attendance using the Check-In/Check-Out button."
        ),
    )
    company_id = models.ForeignKey(Company, on_delete=models.CASCADE, null=True)
    objects = HorillaCompanyManager()

    def company_col(self):
        if self.company_id:
            return self.company_id.company
        else:
            return "All Company"

    def check_in_check_out_col(self):
        """
        This method for get custom coloumn .
        """

        return render_template(
            path="cbv/settings/check_in_check_out_col.html",
            context={"instance": self},
        )


class WorkRecords(models.Model):
    """
    WorkRecord Model
    """

    choices = [
        ("FDP", _("Present")),
        ("HDP", _("Half Day Present")),
        ("ABS", _("Absent")),
        ("HD", _("Holiday / Weekly Off")),
        ("CONF", _("Conflict")),
        ("DFT", _("Draft")),
    ]

    record_name = models.CharField(max_length=250, null=True, blank=True)
    work_record_type = models.CharField(max_length=10, null=True, choices=choices)
    employee_id = models.ForeignKey(
        Employee, on_delete=models.CASCADE, verbose_name=_("Employee")
    )
    date = models.DateField(null=True, blank=True)
    at_work = models.CharField(
        null=True,
        blank=True,
        validators=[
            validate_time_format,
        ],
        default="00:00",
        max_length=10,
    )  # 841
    min_hour = models.CharField(
        null=True,
        blank=True,
        validators=[
            validate_time_format,
        ],
        default="00:00",
        max_length=10,
    )
    at_work_second = models.IntegerField(null=True, blank=True, default=0)
    min_hour_second = models.IntegerField(null=True, blank=True, default=0)
    note = models.TextField(max_length=255)
    message = models.CharField(max_length=30, null=True, blank=True)
    is_attendance_record = models.BooleanField(default=False)
    attendance_id = models.ForeignKey(
        Attendance, on_delete=models.SET_NULL, blank=True, null=True
    )
    is_leave_record = models.BooleanField(default=False)
    if apps.is_installed("leave"):
        leave_request_id = models.ForeignKey(
            "leave.LeaveRequest",
            on_delete=models.SET_NULL,
            blank=True,
            null=True,
        )
    shift_id = models.ForeignKey(
        EmployeeShift, on_delete=models.SET_NULL, blank=True, null=True
    )
    day_percentage = models.FloatField(default=0)
    last_update = models.DateTimeField(null=True, blank=True)
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    def title_message(self):
        title_message = self.message
        if title_message == "Leave":
            if apps.is_installed("leave"):
                title_message += f" | {self.leave_request_id.leave_type_id}"
        return title_message

    def save(self, *args, **kwargs):
        self.last_update = timezone.now()

        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if not 0.0 <= self.day_percentage <= 1.0:
            raise ValidationError(_("Day percentage must be between 0.0 and 1.0"))

    def __str__(self):
        return (
            self.record_name
            if self.record_name is not None
            else f"{self.work_record_type}-{self.date}-{self.employee_id}"
        )

    class Meta:
        verbose_name = _("Daily Work Status")
        verbose_name_plural = _("Daily Work Status")
        constraints = [
            models.UniqueConstraint(
                fields=["employee_id", "date"],
                name="unique_work_record_per_employee_per_date",
            )
        ]


class AttendanceConflictResolution(HorillaModel):
    """
    HR decision for days where an attendance record overlaps a leave/holiday/week-off.
    resolution="attendance" → the day counts as attendance (leave/holiday ignored in summary).
    resolution="leave"      → the day counts as leave/holiday (attendance ignored in summary).
    """

    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="conflict_resolutions",
        verbose_name=_("Employee"),
    )
    date = models.DateField(verbose_name=_("Date"))
    resolution = models.CharField(
        max_length=20,
        choices=[
            ("full_present", _("Full Present")),
            ("half_present", _("Half Day")),
            ("partial_hours", _("Partial Hours")),
            ("absent", _("Absent")),
            ("paid_leave", _("Paid Leave")),
            ("unpaid_leave", _("Unpaid Leave")),
            ("holiday", _("Holiday")),
            ("week_off", _("Week Off")),
            # legacy values kept for existing records
            ("attendance", _("Count as Attendance")),
            ("leave", _("Count as Leave / Holiday")),
        ],
        verbose_name=_("Resolution"),
    )
    conflict_type = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name=_("Conflict Type"),
    )
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        unique_together = [["employee_id", "date"]]
        verbose_name = _("Attendance Conflict Resolution")
        verbose_name_plural = _("Attendance Conflict Resolutions")

    def __str__(self):
        return f"{self.employee_id} — {self.date} → {self.resolution}"


class AttendanceSummaryHours(HorillaModel):
    """
    Stores computed (or HR-overridden) total worked seconds for an employee
    over a specific date range.  Created/updated on every summary load;
    is_manually_edited=True records are never overwritten by the auto-compute.
    """

    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="summary_hours",
        verbose_name=_("Employee"),
    )
    from_date = models.DateField(verbose_name=_("From Date"))
    to_date = models.DateField(verbose_name=_("To Date"))
    hours_second = models.IntegerField(
        default=0,
        verbose_name=_("Hours (seconds)"),
    )
    is_manually_edited = models.BooleanField(
        default=False,
        verbose_name=_("Manually Edited"),
    )

    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        unique_together = [["employee_id", "from_date", "to_date"]]
        verbose_name = _("Attendance Summary Hours")
        verbose_name_plural = _("Attendance Summary Hours")

    def __str__(self):
        h, m = self.hours_second // 3600, (self.hours_second % 3600) // 60
        return f"{self.employee_id} {self.from_date}–{self.to_date}: {h}h{m:02d}m"


class AttendanceDailyHours(HorillaModel):
    """
    Per-employee per-date worked hours, editable inside the calendar modal.
    Created when a manager manually edits a single day's hours.
    When present with is_manually_edited=True, overrides the computed daily
    contribution in build_monthly_summary.
    """

    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="daily_hours",
        verbose_name=_("Employee"),
    )
    date = models.DateField(verbose_name=_("Date"))
    hours_second = models.IntegerField(default=0, verbose_name=_("Hours (seconds)"))
    is_manually_edited = models.BooleanField(
        default=False,
        verbose_name=_("Manually Edited"),
    )
    modified_at = models.DateTimeField(auto_now=True, verbose_name=_("Modified At"))

    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        unique_together = [["employee_id", "date"]]
        verbose_name = _("Attendance Daily Hours")
        verbose_name_plural = _("Attendance Daily Hours")

    def __str__(self):
        h, m = self.hours_second // 3600, (self.hours_second % 3600) // 60
        return f"{self.employee_id} {self.date}: {h}h{m:02d}m"
