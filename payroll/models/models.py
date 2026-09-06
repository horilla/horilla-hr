"""
models.py
Used to register models
"""

import calendar
import logging
import re
from datetime import date, datetime, timedelta

from django import forms
from django.apps import apps
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import models
from django.http import QueryDict
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from base.methods import get_next_month_same_date
from base.models import (
    Company,
    Department,
    EmployeeShift,
    JobPosition,
    JobRole,
    WorkType,
    validate_time_format,
)
from employee.methods.duration_methods import strtime_seconds
from employee.models import BonusPoint, Employee, EmployeeWorkInformation
from horilla import horilla_middlewares
from horilla.horilla_middlewares import _thread_locals
from horilla.models import HorillaModel, upload_path
from horilla_audit.models import HorillaAuditInfo, HorillaAuditLog
from horilla_views.cbv_methods import render_template

logger = logging.getLogger(__name__)


# Create your models here.


def min_zero(value):
    """
    The minimum value zero validation method
    """
    if value < 0:
        raise ValidationError(_("Value must be greater than zero"))


def get_date_range(start_date, end_date):
    """
    Returns a list of all dates within a given date range.

    Args:
        start_date (date): The start date of the range.
        end_date (date): The end date of the range.

    Returns:
        list: A list of date objects representing all dates within the range.

    Example:
        start_date = date(2023, 1, 1)
        end_date = date(2023, 1, 10)
        date_range = get_date_range(start_date, end_date)
    """
    date_list = []
    delta = end_date - start_date

    for i in range(delta.days + 1):
        current_date = start_date + timedelta(days=i)
        date_list.append(current_date)

    return date_list


class FilingStatus(HorillaModel):
    """
    FilingStatus model
    """

    based_on_choice = [
        ("basic_pay", _("Basic Pay")),
        ("gross_pay", _("Gross Pay")),
        ("taxable_gross_pay", _("Taxable Gross Pay")),
    ]
    filing_status = models.CharField(
        max_length=30,
        blank=False,
        verbose_name=_("Filing status"),
    )
    based_on = models.CharField(
        max_length=255,
        choices=based_on_choice,
        null=False,
        blank=False,
        default="taxable_gross_pay",
        verbose_name=_("Based on"),
    )
    use_py = models.BooleanField(verbose_name=_("Python Code"), default=False)
    python_code = models.TextField(null=True)
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        max_length=255,
    )
    company_id = models.ForeignKey(
        Company, null=True, editable=False, on_delete=models.PROTECT
    )
    objects = HorillaCompanyManager()

    def __str__(self) -> str:
        return str(self.filing_status)

    def get_update_url(self):
        """
        Returns the URL for updating the filing status instance.
        """
        return reverse("filing-status-update", kwargs={"pk": self.pk})

    def get_create_url(self):
        """
        Returns the URL for updating the filing status instance.
        """
        return reverse("tax-bracket-create", kwargs={"filing_status_id": self.pk})

    def get_delete_url(self):
        """
        Returns the URL for updating the filing status instance.
        """
        return f"{reverse('generic-delete')}?model=payroll.FilingStatus&pk={self.pk}"

    def tax_brackets_col(self):
        """
        Renders the tax brackets belonging to this filing status as a table.
        """
        return render_template(
            path="cbv/federal_tax/tax_brackets_col.html",
            context={
                "instance": self,
                "tax_brackets": self.taxbracket_set.all().order_by("min_income"),
            },
        )

    class Meta:
        ordering = ["-id"]
        verbose_name = _("Filing Status")
        verbose_name_plural = _("Filing Statuses")


class Contract(HorillaModel):
    """
    Contract Model
    """

    COMPENSATION_CHOICES = (
        ("salary", _("Salary")),
        ("hourly", _("Hourly")),
        ("commission", _("Commission")),
    )

    PAY_FREQUENCY_CHOICES = (
        ("weekly", _("Weekly")),
        ("monthly", _("Monthly")),
        ("semi_monthly", _("Semi-Monthly")),
    )
    WAGE_CHOICES = [
        ("daily", _("Daily")),
        ("monthly", _("Monthly")),
    ]

    if apps.is_installed("attendance"):
        WAGE_CHOICES.append(("hourly", _("Hourly")))

    CONTRACT_STATUS_CHOICES = (
        ("draft", _("Draft")),
        ("active", _("Active")),
        ("expired", _("Expired")),
        ("terminated", _("Terminated")),
    )

    contract_name = models.CharField(
        max_length=250, help_text=_("Contract Title."), verbose_name=_("Contract")
    )
    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="contract_set",
        verbose_name=_("Employee"),
    )
    contract_start_date = models.DateField(verbose_name=_("Start Date"))
    contract_end_date = models.DateField(
        null=True, blank=True, verbose_name=_("End Date")
    )
    wage_type = models.CharField(
        choices=WAGE_CHOICES,
        max_length=250,
        default="monthly",
        verbose_name=_("Wage Type"),
    )
    pay_frequency = models.CharField(
        max_length=20,
        null=True,
        choices=PAY_FREQUENCY_CHOICES,
        default="monthly",
        verbose_name=_("Pay Frequency"),
    )
    wage = models.FloatField(verbose_name=_("Basic Salary"), null=True, default=0)
    filing_status = models.ForeignKey(
        FilingStatus,
        on_delete=models.PROTECT,
        related_name="contracts",
        null=True,
        blank=True,
        verbose_name=_("Filing Status"),
    )
    salary_structure_id = models.ForeignKey(
        "payroll.SalaryStructure",
        on_delete=models.SET_NULL,
        related_name="contracts",
        null=True,
        blank=True,
        verbose_name=_("Salary Structure"),
    )
    contract_status = models.CharField(
        choices=CONTRACT_STATUS_CHOICES,
        max_length=250,
        default="draft",
        verbose_name=_("Status"),
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts",
        verbose_name=_("Department"),
    )
    job_position = models.ForeignKey(
        JobPosition,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts",
        verbose_name=_("Job Position"),
    )
    job_role = models.ForeignKey(
        JobRole,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts",
        verbose_name=_("Job Role"),
    )
    shift = models.ForeignKey(
        EmployeeShift,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts",
        verbose_name=_("Shift"),
    )
    work_type = models.ForeignKey(
        WorkType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contracts",
        verbose_name=_("Work Type"),
    )
    notice_period_in_days = models.IntegerField(
        default=30,
        help_text=_("Notice period in total days."),
        validators=[min_zero],
        verbose_name=_("Notice Period"),
    )
    contract_document = models.FileField(upload_to=upload_path, null=True, blank=True)
    deduct_leave_from_basic_pay = models.BooleanField(
        default=True,
        verbose_name=_("Deduct From Basic Pay"),
        help_text=_("Deduct the leave amount from basic pay."),
    )
    calculate_daily_leave_amount = models.BooleanField(
        default=True,
        verbose_name=_("Calculate Daily Leave Amount"),
        help_text=_(
            "Leave amount will be calculated by dividing the basic pay by number of working days."
        ),
    )
    deduction_for_one_leave_amount = models.FloatField(
        null=True,
        blank=True,
        default=0,
        verbose_name=_("Deduction For One Leave Amount"),
    )

    note = models.TextField(null=True, blank=True)
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )

    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    def get_wage_type_display(self):
        """
        Display wage type
        """
        return dict(self.WAGE_CHOICES).get(self.wage_type)

    def get_pay_frequency_display(self):
        """
        Display pay frequency
        """
        return dict(self.PAY_FREQUENCY_CHOICES).get(self.pay_frequency)

    def get_status_display(self):
        """
        Display status
        """
        return dict(self.CONTRACT_STATUS_CHOICES).get(self.contract_status)

    def status_col(self):
        """
        status column
        """
        return render_template(
            path="cbv/contracts/status.html",
            context={"instance": self},
        )

    def detail_action(self):
        """
        Detail actions
        """
        return render_template(
            path="cbv/contracts/detail_action.html",
            context={"instance": self},
        )

    def note_col(self):
        """
        Note column
        """
        return render_template(
            path="cbv/contracts/note.html",
            context={"instance": self},
        )

    def document_col(self):
        """
        Document column
        """
        return render_template(
            path="cbv/contracts/document.html",
            context={"instance": self},
        )

    def actions_col(self):
        """
        actions column
        """
        return render_template(
            path="cbv/contracts/actions.html",
            context={"instance": self},
        )

    def cal_leave_amount(self):
        """
        Action column for Calculate Leave Amount
        """
        return render_template(
            path="cbv/contracts/cal_leave_amount.html",
            context={"instance": self},
        )

    def conract_subtitle(self):
        """
        Detail view subtitle
        """

        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def contracts_detail(self):
        """
        detail view
        """

        url = reverse("contracts-detail-view", kwargs={"pk": self.pk})

        return url

    def deduct_leave_from_basic_pay_col(self):
        """
        Deduct leave from basic pay column
        """
        if self.deduct_leave_from_basic_pay:
            return _("Yes")
        else:
            return _("No")

    def set_salary_structure(self, new_structure):
        """
        Reassign this contract's salary structure, syncing the employee into
        the new structure's allowances/deductions and out of the old
        structure's, when this contract is active. Reassigning to a
        different structure naturally replaces the old one, since a contract
        can only point to one structure at a time.
        """
        old_structure = self.salary_structure_id
        if old_structure == new_structure:
            return
        if self.contract_status == "active":
            if old_structure:
                for allowance in old_structure.allowances.all():
                    still_targeted = (
                        allowance.salary_structures.exclude(pk=old_structure.pk)
                        .filter(contracts__employee_id=self.employee_id)
                        .exists()
                    )
                    if not still_targeted:
                        allowance.specific_employees.remove(self.employee_id)
                for deduction in old_structure.deductions.all():
                    still_targeted = (
                        deduction.salary_structures.exclude(pk=old_structure.pk)
                        .filter(contracts__employee_id=self.employee_id)
                        .exists()
                    )
                    if not still_targeted:
                        deduction.specific_employees.remove(self.employee_id)
            if new_structure:
                for allowance in new_structure.allowances.all():
                    allowance.specific_employees.add(self.employee_id)
                for deduction in new_structure.deductions.all():
                    deduction.specific_employees.add(self.employee_id)
        self.salary_structure_id = new_structure
        self.save()

    def __str__(self) -> str:
        return f"{self.contract_name} -{self.contract_start_date} - {self.contract_end_date}"

    def clean(self):
        if self.contract_end_date is not None:
            if self.contract_end_date < self.contract_start_date:
                raise ValidationError(
                    {"contract_end_date": _("End date must be greater than start date")}
                )
        if (
            self.contract_status == "active"
            and Contract.objects.filter(
                employee_id=self.employee_id, contract_status="active"
            )
            .exclude(id=self.pk)
            .count()
            >= 1
        ):
            raise forms.ValidationError(
                _("An active contract already exists for this employee.")
            )
        if (
            self.contract_status == "draft"
            and Contract.objects.filter(
                employee_id=self.employee_id, contract_status="draft"
            )
            .exclude(id=self.pk)
            .count()
            >= 1
        ):
            raise forms.ValidationError(
                _("A draft contract already exists for this employee.")
            )

        if self.wage_type in ["daily", "monthly"]:
            if not self.calculate_daily_leave_amount:
                if self.deduction_for_one_leave_amount is None:
                    raise ValidationError(
                        {"deduction_for_one_leave_amount": _("This field is required")}
                    )

    def save(self, *args, **kwargs):
        if EmployeeWorkInformation.objects.filter(
            employee_id=self.employee_id
        ).exists():
            if self.department is None:
                self.department = self.employee_id.employee_work_info.department_id

            if self.job_position is None:
                self.job_position = self.employee_id.employee_work_info.job_position_id

            if self.job_role is None:
                self.job_role = self.employee_id.employee_work_info.job_role_id

            if self.work_type is None:
                self.work_type = self.employee_id.employee_work_info.work_type_id

            if self.shift is None:
                self.shift = self.employee_id.employee_work_info.shift_id
        if self.contract_end_date is not None and self.contract_end_date < date.today():
            self.contract_status = "expired"
        if (
            self.contract_status == "active"
            and Contract.objects.filter(
                employee_id=self.employee_id, contract_status="active"
            )
            .exclude(id=self.id)
            .count()
            >= 1
        ):
            raise forms.ValidationError(
                _("An active contract already exists for this employee.")
            )

        if (
            self.contract_status == "draft"
            and Contract.objects.filter(
                employee_id=self.employee_id, contract_status="draft"
            )
            .exclude(id=self.pk)
            .count()
            >= 1
        ):
            raise forms.ValidationError(
                _("A draft contract already exists for this employee.")
            )
        super().save(*args, **kwargs)
        if self.contract_status == "active" and self.wage is not None:
            try:
                wage_int = int(self.wage)
                work_info = self.employee_id.employee_work_info
                work_info.basic_salary = wage_int
                work_info.save()
            except ValueError:
                logger.error((f"Failed to convert wage '{self.wage}' to an integer."))
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
        return self

    class Meta:
        """
        Meta class to add additional options
        """

        unique_together = ["employee_id", "contract_start_date", "contract_end_date"]


class WorkRecord(models.Model):
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
    work_record_type = models.CharField(max_length=5, null=True, choices=choices)
    employee_id = models.ForeignKey(
        Employee, on_delete=models.PROTECT, verbose_name=_("Employee")
    )
    date = models.DateField(null=True, blank=True)
    at_work = models.CharField(
        null=True,
        blank=True,
        validators=[
            validate_time_format,
        ],
        default="00:00",
        max_length=5,
    )
    min_hour = models.CharField(
        null=True,
        blank=True,
        validators=[
            validate_time_format,
        ],
        default="00:00",
        max_length=5,
    )
    at_work_second = models.IntegerField(null=True, blank=True, default=0)
    min_hour_second = models.IntegerField(null=True, blank=True, default=0)
    note = models.TextField(max_length=255)
    message = models.CharField(max_length=30, null=True, blank=True)
    is_attendance_record = models.BooleanField(default=False)
    is_leave_record = models.BooleanField(default=False)
    day_percentage = models.FloatField(default=0)
    last_update = models.DateTimeField(null=True, blank=True)
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

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
            else f"{self.work_record_type}-{self.date}"
        )


if apps.is_installed("attendance"):
    from attendance.models import Attendance

    # class OverrideAttendance(Attendance):
    #     """
    #     Class to override Attendance model save method
    #     """
    #     pass
    # Additional fields and methods specific to AnotherModel
    # @receiver(post_save, sender=Attendance)
    # def attendance_post_save(sender, instance, **kwargs):
    #     """
    #     Overriding Attendance model save method
    #     """
    #     if instance.first_save:
    #         min_hour_second = strtime_seconds(instance.minimum_hour)
    #         at_work_second = strtime_seconds(instance.attendance_worked_hour)
    #         status = "FDP" if instance.at_work_second >= min_hour_second else "HDP"
    #         status = "CONF" if instance.attendance_validated is False else status
    #         message = (
    #             _("Validate the attendance") if status == "CONF" else _("Validated")
    #         )
    #         message = (
    #             _("Incomplete minimum hour")
    #             if status == "HDP" and min_hour_second > at_work_second
    #             else message
    #         )
    #         work_record = WorkRecord.objects.filter(
    #             date=instance.attendance_date,
    #             is_attendance_record=True,
    #             employee_id=instance.employee_id,
    #         )
    #         work_record = (
    #             WorkRecord()
    #             if not WorkRecord.objects.filter(
    #                 date=instance.attendance_date,
    #                 employee_id=instance.employee_id,
    #             ).exists()
    #             else WorkRecord.objects.filter(
    #                 date=instance.attendance_date,
    #                 employee_id=instance.employee_id,
    #             ).first()
    #         )
    #         work_record.employee_id = instance.employee_id
    #         work_record.date = instance.attendance_date
    #         work_record.at_work = instance.attendance_worked_hour
    #         work_record.min_hour = instance.minimum_hour
    #         work_record.min_hour_second = min_hour_second
    #         work_record.at_work_second = at_work_second
    #         work_record.work_record_type = status
    #         work_record.message = message
    #         work_record.is_attendance_record = True
    #         if instance.attendance_validated:
    #             work_record.day_percentage = (
    #                 1.00 if at_work_second > min_hour_second / 2 else 0.50
    #             )
    #         work_record.save()
    #         if status == "HDP" and work_record.is_leave_record:
    #             message = _("Half day leave")
    #         if status == "FDP":
    #             message = _("Present")
    #         work_record.message = message
    #         work_record.save()
    #         message = work_record.message
    #         status = work_record.work_record_type
    #         if not instance.attendance_clock_out:
    #             status = "FDP"
    #             message = _("Currently working")
    #         work_record.message = message
    #         work_record.work_record_type = status
    #         work_record.save()
    # @receiver(pre_delete, sender=Attendance)
    # def attendance_pre_delete(sender, instance, **_kwargs):
    #     """
    #     Overriding Attendance model delete method
    #     """
    #     # Perform any actions before deleting the instance
    #     # ...
    #     WorkRecord.objects.filter(
    #         employee_id=instance.employee_id,
    #         is_attendance_record=True,
    #         date=instance.attendance_date,
    #     ).delete()


if apps.is_installed("leave"):
    from leave.models import LeaveRequest

    class OverrideLeaveRequest(LeaveRequest):
        """
        Class to override Attendance model save method
        """

        pass
        # Additional fields and methods specific to AnotherModel
        # @receiver(pre_save, sender=LeaveRequest)
        # def leaverequest_pre_save(sender, instance, **_kwargs):
        #     """
        #     Overriding LeaveRequest model save method
        #     """
        #     if (
        #         instance.start_date == instance.end_date
        #         and instance.end_date_breakdown != instance.start_date_breakdown
        #     ):
        #         instance.end_date_breakdown = instance.start_date_breakdown
        #         super(LeaveRequest, instance).save()

        #     period_dates = get_date_range(instance.start_date, instance.end_date)
        #     if instance.status == "approved":
        #         for date in period_dates:
        #             try:
        #                 work_entry = (
        #                     WorkRecord.objects.filter(
        #                         date=date,
        #                         employee_id=instance.employee_id,
        #                     )
        #                     if WorkRecord.objects.filter(
        #                         date=date,
        #                         employee_id=instance.employee_id,
        #                     ).exists()
        #                     else WorkRecord()
        #                 )
        #                 work_entry.employee_id = instance.employee_id
        #                 work_entry.is_leave_record = True
        #                 work_entry.day_percentage = (
        #                     0.50
        #                     if instance.start_date == date
        #                     and instance.start_date_breakdown == "first_half"
        #                     or instance.end_date == date
        #                     and instance.end_date_breakdown == "second_half"
        #                     else 0.00
        #                 )
        #                 # scheduler task to validate the conflict entry for half day if they
        #                 # take half day leave is when they mark the attendance.
        #                 status = (
        #                     "CONF"
        #                     if instance.start_date == date
        #                     and instance.start_date_breakdown == "first_half"
        #                     or instance.end_date == date
        #                     and instance.end_date_breakdown == "second_half"
        #                     else "ABS"
        #                 )
        #                 work_entry.work_record_type = status
        #                 work_entry.date = date
        #                 work_entry.message = (
        #                     "Absent"
        #                     if status == "ABS"
        #                     else _("Half day Attendance need to validate")
        #                 )
        #                 work_entry.save()
        #             except:
        #                 pass

        #     else:
        #         for date in period_dates:
        #             WorkRecord.objects.filter(
        #                 is_leave_record=True,
        #                 date=date,
        #                 employee_id=instance.employee_id,
        #             ).delete()


# class OverrideWorkInfo(EmployeeWorkInformation):
#     """
#     This class is to override the Model default methods
#     """

# @receiver(pre_save, sender=EmployeeWorkInformation)
# def employeeworkinformation_pre_save(sender, instance, **_kwargs):
#     """
#     This method is used to override the save method for EmployeeWorkInformation Model
#     """
#     active_employee = (
#         instance.employee_id if instance.employee_id.is_active == True else None
#     )
#     if active_employee is not None:
#         contract_exists = active_employee.contract_set.exists()
#         if not contract_exists:
#             contract = Contract()
#             contract.contract_name = f"{active_employee}'s Contract"
#             contract.employee_id = active_employee
#             contract.contract_start_date = (
#                 instance.date_joining if instance.date_joining else datetime.today()
#             )
#             contract.wage = (
#                 instance.basic_salary if instance.basic_salary is not None else 0
#             )
#             contract.save()


# Create your models here.
def rate_validator(value):
    """
    Percentage validator
    """
    if value < 0:
        raise ValidationError(_("Rate must be greater than 0"))
    if value > 100:
        raise ValidationError(_("Rate must be less than 100"))


CONDITION_CHOICE = [
    ("equal", _("Equal (==)")),
    ("notequal", _("Not Equal (!=)")),
    ("lt", _("Less Than (<)")),
    ("gt", _("Greater Than (>)")),
    ("le", _("Less Than or Equal To (<=)")),
    ("ge", _("Greater Than or Equal To (>=)")),
    ("icontains", _("Contains")),
]
IF_CONDITION_CHOICE = [
    ("equal", _("Equal (==)")),
    ("notequal", _("Not Equal (!=)")),
    ("lt", _("Less Than (<)")),
    ("gt", _("Greater Than (>)")),
    ("le", _("Less Than or Equal To (<=)")),
    ("ge", _("Greater Than or Equal To (>=)")),
    ("range", _("Range")),
]
FIELD_CHOICE = [
    ("children", _("Children")),
    ("marital_status", _("Marital Status")),
    ("experience", _("Experience")),
    ("employee_work_info__experience", _("Company Experience")),
    ("gender", _("Gender")),
    ("country", _("Country")),
    ("state", _("State")),
    ("contract_set__pay_frequency", _("Pay Frequency")),
    ("contract_set__wage_type", _("Wage Type")),
    ("contract_set__department__department", _("Department on Contract")),
]


class MultipleCondition(models.Model):
    """
    MultipleCondition Model
    """

    field = models.CharField(
        max_length=255,
    )
    condition = models.CharField(
        max_length=255, choices=CONDITION_CHOICE, null=True, blank=True
    )
    value = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("The value must be like the data stored in the database"),
    )


class Allowance(HorillaModel):
    """
    Allowance model
    """

    exceed_choice = [
        ("ignore", _("Exclude the allowance")),
        ("max_amount", _("Provide max amount")),
    ]

    based_on_choice = [
        ("basic_pay", _("Basic Pay")),
        ("children", _("Children")),
    ]

    if apps.is_installed("attendance"):
        attendance_choices = [
            ("overtime", _("Regular Overtime")),
            ("week_off_overtime", _("Week Off Overtime")),
            ("holiday_overtime", _("Holiday Overtime")),
            ("shift_id", _("Shift")),
            ("work_type_id", _("Work Type")),
            ("attendance", _("Attendance")),
        ]
        based_on_choice += attendance_choices

    if_condition_choice = [
        ("basic_pay", _("Basic Pay")),
    ]
    title = models.CharField(
        max_length=255,
        null=False,
        blank=False,
    )
    one_time_date = models.DateField(
        null=True,
        blank=True,
    )
    include_active_employees = models.BooleanField(
        default=False,
        verbose_name=_("Include All Employees"),
    )
    specific_employees = models.ManyToManyField(
        Employee,
        verbose_name=_("Employees Specific"),
        blank=True,
        related_name="allowance_specific",
    )
    exclude_employees = models.ManyToManyField(
        Employee,
        verbose_name=_("Exclude Employees"),
        related_name="allowance_excluded",
        blank=True,
    )
    is_taxable = models.BooleanField(
        default=True,
    )
    is_condition_based = models.BooleanField(
        default=False,
    )
    # If condition based
    field = models.CharField(
        max_length=255,
        choices=FIELD_CHOICE,
        null=True,
        blank=True,
    )
    condition = models.CharField(
        max_length=255, choices=CONDITION_CHOICE, null=True, blank=True
    )
    value = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    is_fixed = models.BooleanField(
        default=True,
    )
    amount = models.FloatField(
        null=True,
        blank=True,
        validators=[min_zero],
    )
    # If is fixed is false
    based_on = models.CharField(
        max_length=255,
        default="basic_pay",
        choices=based_on_choice,
        null=True,
        blank=True,
    )
    rate = models.FloatField(
        null=True,
        blank=True,
        validators=[
            rate_validator,
        ],
    )
    # If based on attendance
    per_attendance_fixed_amount = models.FloatField(
        null=True,
        blank=True,
        default=0.00,
        validators=[min_zero],
    )
    # If based on children
    per_children_fixed_amount = models.FloatField(
        null=True,
        blank=True,
        default=0.00,
        validators=[min_zero],
    )
    # If based on shift
    shift_id = models.ForeignKey(
        EmployeeShift,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Shift"),
    )
    shift_per_attendance_amount = models.FloatField(
        null=True,
        default=0.00,
        blank=True,
        validators=[min_zero],
    )
    amount_per_one_hr = models.FloatField(
        null=True,
        default=0.00,
        blank=True,
        validators=[min_zero],
    )
    work_type_id = models.ForeignKey(
        WorkType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Work Type"),
    )
    work_type_per_attendance_amount = models.FloatField(
        null=True,
        default=0.00,
        blank=True,
        validators=[min_zero],
    )
    # for apply only
    has_max_limit = models.BooleanField(
        default=False,
        verbose_name=_("Has max limit for allowance"),
    )
    maximum_amount = models.FloatField(
        null=True,
        blank=True,
        validators=[min_zero],
        verbose_name=_("Maximum Amount"),
    )
    maximum_unit = models.CharField(
        max_length=20,
        null=True,
        default="month_working_days",
        choices=[
            (
                "month_working_days",
                _("For working days on month"),
            ),
            # ("monthly_working_days", "For working days on month"),
        ],
        verbose_name=_("Maximum Unit"),
    )
    if_choice = models.CharField(
        max_length=10,
        choices=if_condition_choice,
        default="basic_pay",
    )
    if_condition = models.CharField(
        max_length=10,
        choices=IF_CONDITION_CHOICE,
        default="gt",
    )
    if_amount = models.FloatField(
        default=0.00,
    )
    start_range = models.FloatField(
        blank=True,
        null=True,
    )
    end_range = models.FloatField(
        blank=True,
        null=True,
    )
    company_id = models.ForeignKey(
        Company, null=True, editable=False, on_delete=models.PROTECT
    )
    only_show_under_employee = models.BooleanField(default=False, editable=False)
    is_loan = models.BooleanField(default=False, editable=False)
    objects = HorillaCompanyManager()
    other_conditions = models.ManyToManyField(
        MultipleCondition, blank=True, editable=False
    )

    class Meta:
        """
        Meta class for additional options
        """

        unique_together = [
            "title",
            "is_taxable",
            "is_condition_based",
            "field",
            "condition",
            "value",
            "is_fixed",
            "amount",
            "based_on",
            "rate",
            "per_attendance_fixed_amount",
            "shift_id",
            "shift_per_attendance_amount",
            "amount_per_one_hr",
            "work_type_id",
            "work_type_per_attendance_amount",
        ]
        verbose_name = _("Allowance")

    def get_specific_employees(self):
        """
        Get all specific employees separated by commas.
        """

        employees = self.specific_employees.all()
        employee_names_string = ", ".join([str(employee) for employee in employees])
        return employee_names_string

    def get_exclude_employees(self):
        """
        Get all specific employees separated by commas.
        """

        return ", ".join([str(employee) for employee in self.exclude_employees.all()])

    def get_is_taxable_display(self):
        """
        method to return is taxable or not
        """
        return _("Yes") if self.is_taxable else _("No")

    def get_is_condition_based(self):
        """
        method to return is condition based or not
        """
        return _("Yes") if self.is_condition_based else _("No")

    def get_is_fixed(self):
        """
        method to return is fixed
        """
        return _("Yes") if self.is_fixed else _("No")

    def get_based_on_display(self):
        """
        method to return get based on field
        """
        return dict(self.based_on_choice).get(self.based_on)

    def allowance_detail_view(self):
        """
        detail view
        """

        url = reverse("allowance-detail-view", kwargs={"pk": self.pk})

        return url

    def get_delete_url(self):
        """
        to get the delete url for card action delete
        """

        url = reverse_lazy("generic-delete")

        return url

    def get_update_url(self):
        """
        to get the update url for card action update
        """

        url = reverse("update-allowance", kwargs={"pk": self.pk})
        return url

    def get_allowance_actions(self):
        """
        This method to get allowance actions
        """

        return render_template(
            path="cbv/allowance_deduction/allowance_action.html",
            context={"instance": self},
        )

    def get_avatar(self):
        """
        Method will return the API URL for the avatar or the path to the profile image.
        """
        sanitized_title = re.sub(r"[^a-zA-Z0-9\s]", "", self.title)
        sanitized_title = sanitized_title.replace(" ", "+")
        url = f"https://ui-avatars.com/api/?name={sanitized_title}&background=random"
        return url

    def one_time_date_display(self):
        """
        method to return one time field
        """
        if self.one_time_date:
            return f'On <span class="dateformat_changer">{self.one_time_date}</span>'
        else:
            return _("No")

    def get_field_display(self):
        """
        get field choice dict if based on condition
        """
        return dict(FIELD_CHOICE).get(self.field)

    def get_condition_display(self):
        """
        get condition choice dict if based on condition
        """
        return dict(CONDITION_CHOICE).get(self.condition)

    def condition_based_display(self):
        """
        method to return condition if condition based
        """
        if self.is_condition_based:
            condition_display = self.get_condition_display()
            return f"{self.get_field_display()} {condition_display} {self.value}"
        else:
            return _("No")

    def based_on_amount(self):
        """
        custome template for retrieve amount
        """
        return render_template(
            path="cbv/allowance_deduction/allowance/custom_amount.html",
            context={"instance": self},
        )

    def cust_allowance_max_limit(self):
        """
        custom template to retrive allowance max limit
        """
        return render_template(
            path="cbv/allowance_deduction/allowance/max_limit_col.html",
            context={"instance": self},
        )

    def get_if_choice_display(self):
        """
        for allowance eligibility
        """
        return (
            dict(self.if_condition_choice).get(self.if_choice, self.if_choice)
            if self.if_choice
            else ""
        )

    def get_if_condition_display(self):
        """
        for allowance eligibility
        """
        return (
            dict(IF_CONDITION_CHOICE).get(self.if_condition, self.if_condition)
            if self.if_condition
            else ""
        )

    def allowance_eligibility(self):
        """
        for allowance eligibility
        """
        return f'{_("If")} {self.get_if_choice_display()} {self.get_if_condition_display()} {self.if_amount}'

    def allowance_detail_actions(self):
        """
        custom template to retrive detail view actions
        """
        return render_template(
            path="cbv/allowance_deduction/allowance/detail_view_actions.html",
            context={"instance": self},
        )

    def reset_based_on(self):
        """Reset the this fields when is_fixed attribute is true"""
        attributes_to_reset = [
            "based_on",
            "rate",
            "per_attendance_fixed_amount",
            "shift_id",
            "shift_per_attendance_amount",
            "amount_per_one_hr",
            "work_type_id",
            "work_type_per_attendance_amount",
            "maximum_amount",
        ]
        for attribute in attributes_to_reset:
            setattr(self, attribute, None)
        self.has_max_limit = False

    def get_specific_exclude_employees(self):
        """
        Get all specific and exclude employees separated by commas for detail view.
        """
        col = ""
        if self.specific_employees.exists():
            specific_employees = self.specific_employees.all()
            specific_employee_names = ", ".join(
                str(employee.get_full_name()) for employee in specific_employees
            )
            label = "Specific Employees"

            col += format_html(
                """
                    <div class="col-span-1 md:col-span-6 mb-2 flex gap-5 items-center">
                            <span class="font-medium text-xs text-[#565E6C] w-32">
                                {}
                            </span>
                            <div class="text-xs font-semibold flex items-center gap-5">
                                : <span>
                                    {}
                                </span>
                            </div>
                        </div>
                """,
                label,
                specific_employee_names,
            )

        if self.exclude_employees.exists():
            exclude_employees = self.exclude_employees.all()
            exclude_employee_names = ", ".join(
                str(employee.get_full_name()) for employee in exclude_employees
            )
            label = "Excluded Employees"
            col += format_html(
                """
                    <div class="col-span-1 md:col-span-6 mb-2 flex gap-5 items-center">
                            <span class="font-medium text-xs text-[#565E6C] w-32">
                                {}
                            </span>
                            <div class="text-xs font-semibold flex items-center gap-5">
                                : <span>
                                    {}
                                </span>
                            </div>
                        </div>
                """,
                label,
                exclude_employee_names,
            )
        return col

    def clean(self):
        super().clean()
        self.clean_fixed_attributes()
        if not self.is_condition_based:
            self.field = None
            self.condition = None
            self.value = None
        if not self.is_fixed:
            if not self.based_on:
                raise ValidationError(
                    _(
                        "If the 'Is fixed' field is disabled, the 'Based on' field is required."
                    )
                )
        if not self.is_fixed and self.based_on and self.based_on == "basic_pay":
            if not self.rate:
                raise ValidationError(
                    _("Rate must be specified for allowances based on basic pay.")
                )
        if self.is_condition_based:
            if not self.field or not self.value or not self.condition:
                raise ValidationError(
                    _(
                        "If condition based, all fields (field, value, condition) must be filled."
                    )
                )
        if self.based_on == "attendance" and not self.per_attendance_fixed_amount:
            raise ValidationError(
                {
                    "based_on": _(
                        "If based on is attendance, \
                        then per attendance fixed amount must be filled."
                    )
                }
            )
        if self.based_on == "shift_id" and not self.shift_id:
            raise ValidationError(_("If based on is shift, then shift must be filled."))
        if self.based_on == "work_type_id" and not self.work_type_id:
            raise ValidationError(
                _("If based on is work type, then work type must be filled.")
            )
        if self.based_on == "children" and not self.per_children_fixed_amount:
            raise ValidationError(_("The amount per children must be filled."))
        if self.is_fixed and self.amount < 0:
            raise ValidationError({"amount": _("Amount should be greater than zero.")})

        if self.has_max_limit and self.maximum_amount is None:
            raise ValidationError({"maximum_amount": _("This field is required")})

        if not self.has_max_limit:
            self.maximum_amount = None

    def clean_fixed_attributes(self):
        """Clean the amount field and trigger the reset_based_on function based on the condition"""
        if not self.is_fixed:
            self.amount = None
        if self.is_fixed:
            if self.amount is None:
                raise ValidationError({"amount": _("This field is required")})
            self.reset_based_on()

    def __str__(self) -> str:
        return str(self.title)

    def save(self, *args, **kwargs):
        from base.auth_backends import stamp_company_on_create

        if not self.id:
            stamp_company_on_create(self)
        super().save(*args, **kwargs)


class Deduction(HorillaModel):
    """
    Deduction model
    """

    if_condition_choice = [
        ("basic_pay", _("Basic Pay")),
        ("gross_pay", _("Gross Pay")),
    ]

    based_on_choice = [
        ("basic_pay", _("Basic Pay")),
        ("gross_pay", _("Gross Pay")),
        ("taxable_gross_pay", _("Taxable Gross Pay")),
        ("net_pay", _("Net Pay")),
    ]

    exceed_choice = [
        ("ignore", _("Exclude the deduction")),
        ("max_amount", _("Provide max amount")),
    ]

    title = models.CharField(max_length=255)
    one_time_date = models.DateField(
        null=True,
        blank=True,
    )
    include_active_employees = models.BooleanField(
        default=False,
        verbose_name=_("Include All Employees"),
    )
    specific_employees = models.ManyToManyField(
        Employee,
        verbose_name=_("Employees Specific"),
        related_name="deduction_specific",
        blank=True,
    )
    exclude_employees = models.ManyToManyField(
        Employee,
        verbose_name=_("Exclude Employees"),
        related_name="deduction_exclude",
        blank=True,
    )

    is_tax = models.BooleanField(
        default=False,
    )

    is_pretax = models.BooleanField(
        default=True,
    )

    is_condition_based = models.BooleanField(
        default=False,
    )
    # If condition based then must fill field, value, and condition,
    field = models.CharField(
        max_length=255,
        choices=FIELD_CHOICE,
        null=True,
        blank=True,
    )
    condition = models.CharField(
        max_length=255, choices=CONDITION_CHOICE, null=True, blank=True
    )
    value = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    update_compensation = models.CharField(
        null=True,
        blank=True,
        max_length=10,
        choices=[
            (
                "basic_pay",
                _("Basic pay"),
            ),
            ("gross_pay", _("Gross Pay")),
            ("net_pay", _("Net Pay")),
        ],
    )
    is_fixed = models.BooleanField(
        default=True,
    )
    # If fixed amount then fill amount
    amount = models.FloatField(
        null=True,
        blank=True,
        validators=[min_zero],
    )
    based_on = models.CharField(
        max_length=255,
        choices=based_on_choice,
        null=True,
        blank=True,
    )
    rate = models.FloatField(
        null=True,
        blank=True,
        default=0.00,
        validators=[
            rate_validator,
        ],
        verbose_name=_("Employee rate"),
    )

    employer_rate = models.FloatField(
        default=0.00,
        null=True,
        blank=True,
        validators=[
            rate_validator,
        ],
    )
    has_max_limit = models.BooleanField(
        default=False,
        verbose_name=_("Has max limit for deduction"),
    )
    maximum_amount = models.FloatField(
        null=True,
        blank=True,
        validators=[min_zero],
        verbose_name=_("Maximum Amount"),
    )

    maximum_unit = models.CharField(
        max_length=20,
        null=True,
        default="month_working_days",
        choices=[
            ("month_working_days", _("For working days on month")),
            # ("monthly_working_days", "For working days on month"),
        ],
        verbose_name=_("Maximum Unit"),
    )
    if_choice = models.CharField(
        max_length=10,
        choices=if_condition_choice,
        default="basic_pay",
    )
    if_condition = models.CharField(
        max_length=10,
        choices=IF_CONDITION_CHOICE,
        default="gt",
    )
    if_amount = models.FloatField(default=0.00)
    start_range = models.FloatField(blank=True, null=True)
    end_range = models.FloatField(blank=True, null=True)
    company_id = models.ForeignKey(
        Company, null=True, editable=False, on_delete=models.PROTECT
    )
    only_show_under_employee = models.BooleanField(default=False, editable=False)
    objects = HorillaCompanyManager()

    is_installment = models.BooleanField(default=False, editable=False)
    other_conditions = models.ManyToManyField(
        MultipleCondition, blank=True, editable=False
    )

    @cached_property
    def installment_payslip(self):
        """
        The payslip associated with this installment, if any. A
        cached_property so the handful of templates/filters checking this
        per row (loan/salary-advance/fine repayment schedules) don't each
        re-query for the same instance. Views rendering many installments
        at once should still bulk-resolve and pre-set this attribute
        instead of relying on the per-instance query here -- see
        LoanDetailView.get_context_data.
        """
        return Payslip.objects.filter(installment_ids=self).first()

    def get_is_pretax_display(self):
        return _("Yes") if self.is_pretax else _("No")

    def get_is_condition_based_display(self):
        return _("Yes") if self.is_condition_based else _("No")

    def get_is_fixed_display(self):
        return _("Yes") if self.is_fixed else _("No")

    def get_based_on_display(self):
        """
        Display work type
        """
        return dict(self.based_on_choice).get(self.based_on)

    def get_field_display(self):
        """
        Field column
        """
        return dict(FIELD_CHOICE).get(self.field)

    def get_condition_display(self):
        """
        condition display column
        """
        return dict(CONDITION_CHOICE).get(self.condition)

    def condition_based_col(self):
        """
        Condition based column
        """
        if self.is_condition_based:
            return f"{self.get_field_display()} {self.get_condition_display()} {self.value}"
        else:
            return _("No")

    def deduct_actions(self):
        """
        This method for get custom coloumn .
        """

        return render_template(
            path="cbv/allowance_deduction/deductions/deductions_actions.html",
            context={"instance": self},
        )

    def deduct_detail_actions(self):
        """
        This method for get custom coloumn .
        """

        return render_template(
            path="cbv/allowance_deduction/deductions/detail_view_actions.html",
            context={"instance": self},
        )

    def deduction_eligibility(self):
        """
        Deduction eligibility column
        """
        return f"{self.get_if_choice_display()} {self.get_if_condition_display()} {self.if_amount}"

    def has_maximum_limit_col(self):
        """
        This method for get custom coloumn .
        """

        return render_template(
            path="cbv/allowance_deduction/deductions/has_maximum_limit.html",
            context={"instance": self},
        )

    def amount_col(self):
        """
        This method for get custom coloumn for amount .
        """

        return render_template(
            path="cbv/allowance_deduction/deductions/amount.html",
            context={"instance": self},
        )

    def get_avatar(self):
        """
        Method will return the API URL for the avatar or the path to the profile image.
        """
        sanitized_title = re.sub(r"[^a-zA-Z0-9\s]", "", self.title)
        sanitized_title = sanitized_title.replace(" ", "+")
        url = f"https://ui-avatars.com/api/?name={sanitized_title}&background=random"
        return url

    def deduction_detail_view(self):
        """
        detail view
        """
        url = reverse("deduction-detail-view", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        detail view
        """
        # url = reverse("delete-deduction", kwargs={"deduction_id": self.pk})
        url = reverse_lazy("generic-delete")

        return url

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("update-deduction", kwargs={"pk": self.pk})
        return url

    def specific_employees_col(self):
        """
        Specific Employees
        """
        employees = self.specific_employees.all()
        employee_names_string = ", ".join(
            [str(employee.get_full_name()) for employee in employees]
        )
        return employee_names_string

    def excluded_employees_col(self):
        """
        Excluded employees
        """
        employees = self.exclude_employees.all()
        employee_names_string = ", ".join(
            [str(employee.get_full_name()) for employee in employees]
        )
        return employee_names_string

    def tax_col(self):
        if self.is_tax:
            title = _("Tax")
            count = _("Yes") if self.is_tax else _("No")
        else:
            title = _("Pretax")
            count = _("Yes") if self.is_pretax else _("No")
        count = count.capitalize()

        return f"""
            <div class="col-span-1 md:col-span-6 mb-2 flex gap-5">
                <span class="font-medium text-xs text-[#565E6C] w-32">
                    {title}
                </span>
                <div class="text-xs font-semibold flex gap-5">
                    : <span>
                        {count}
                    </span>
                </div>
            </div>
        """

    def get_one_time_deduction(self):
        """
        One time deduction column
        """
        if self.one_time_date:
            return f"On <span class='dateformat_changer'> {self.one_time_date}</span> "
        else:
            return _("No")

    def get_specific_exclude_employees(self):
        """
        Get all specific and exclude employees separated by commas for detail view.
        """
        col = ""
        if self.specific_employees.exists():
            specific_employees = self.specific_employees.all()
            specific_employee_names = ", ".join(
                str(employee.get_full_name()) for employee in specific_employees
            )
            label = "Specific Employees"

            col += format_html(
                """
                    <div class="col-span-1 md:col-span-6 mb-2 flex gap-5 items-center">
                            <span class="font-medium text-xs text-[#565E6C] w-32">
                                {}
                            </span>
                            <div class="text-xs font-semibold flex items-center gap-5">
                                : <span>
                                    {}
                                </span>
                            </div>
                        </div>
                """,
                label,
                specific_employee_names,
            )

        if self.exclude_employees.exists():
            exclude_employees = self.exclude_employees.all()
            exclude_employee_names = ", ".join(
                str(employee.get_full_name()) for employee in exclude_employees
            )
            label = "Excluded Employees"
            col += format_html(
                """
                    <div class="col-span-1 md:col-span-6 mb-2 flex gap-5 items-center">
                            <span class="font-medium text-xs text-[#565E6C] w-32">
                                {}
                            </span>
                            <div class="text-xs font-semibold flex items-center gap-5">
                                : <span>
                                    {}
                                </span>
                            </div>
                        </div>
                """,
                label,
                exclude_employee_names,
            )
        return col

    def clean(self):
        super().clean()

        if self.is_tax:
            self.is_pretax = False
        if not self.is_fixed:
            if not self.based_on and not self.update_compensation:
                raise ValidationError(
                    _(
                        "If the 'Is fixed' field is disabled, the 'Based on' field is required."
                    )
                )
        if not self.is_fixed and self.based_on and not self.rate:
            raise ValidationError(
                _(
                    "Employee rate must be specified for deductions that are not fixed amount"
                )
            )

        if self.is_pretax and self.based_on in ["taxable_gross_pay"]:
            raise ValidationError(
                {
                    "based_on": _(
                        " Don't choose taxable gross pay when pretax is enabled."
                    )
                }
            )
        if self.is_pretax and self.based_on in ["net_pay"]:
            raise ValidationError(
                {"based_on": _(" Don't choose net pay when pretax is enabled.")}
            )
        if self.is_tax and self.based_on in ["net_pay"]:
            raise ValidationError(
                {"based_on": _(" Don't choose net pay when the tax is enabled.")}
            )
        if not self.is_fixed:
            self.amount = None
        else:
            self.based_on = None
            self.rate = None
            self.employer_rate = 0
        self.clean_condition_based_on()
        if self.has_max_limit:
            if self.maximum_amount is None:
                raise ValidationError({"maximum_amount": _("This fields required")})

        if self.is_condition_based:
            if not self.field or not self.value or not self.condition:
                raise ValidationError(
                    {
                        "is_condition_based": _(
                            "If condition based, all fields \
                            (field, value, condition) must be filled."
                        )
                    }
                )
        if self.update_compensation is None:
            if self.is_fixed:
                if self.amount is None:
                    raise ValidationError({"amount": _("This field is required")})

    def clean_condition_based_on(self):
        """
        Clean the field, condition, and value attributes when not condition-based.
        """
        if not self.is_condition_based:
            self.field = None
            self.condition = None
            self.value = None

    def __str__(self) -> str:
        return str(self.title)

    def save(self, *args, **kwargs):
        from base.auth_backends import stamp_company_on_create

        if not self.id:
            stamp_company_on_create(self)
        super().save(*args, **kwargs)


class SalaryStructure(HorillaModel):
    """
    Salary Structure model

    A reusable, named set of allowances/deductions. Employees are linked to a
    structure through their active Contract's ``salary_structure_id`` (see
    ``Contract.set_salary_structure``), which keeps ``Allowance``/``Deduction``
    ``specific_employees`` in sync. Payslip calculation continues to read
    ``specific_employees`` directly and is unaffected by this model.
    """

    title = models.CharField(
        max_length=255,
    )
    allowances = models.ManyToManyField(
        Allowance,
        blank=True,
        related_name="salary_structures",
        verbose_name=_("Allowances"),
    )
    deductions = models.ManyToManyField(
        Deduction,
        blank=True,
        related_name="salary_structures",
        verbose_name=_("Deductions"),
    )
    company_id = models.ForeignKey(
        Company, null=True, editable=False, on_delete=models.PROTECT
    )
    objects = HorillaCompanyManager()

    class Meta:
        """
        Meta class for additional options
        """

        unique_together = ["title", "company_id"]
        verbose_name = _("Salary Structure")

    def __str__(self) -> str:
        return str(self.title)

    def save(self, *args, **kwargs):
        from base.auth_backends import stamp_company_on_create

        if not self.id:
            stamp_company_on_create(self)
        super().save(*args, **kwargs)

    def _active_contracts(self):
        return self.contracts.filter(contract_status="active")

    def add_allowance(self, allowance):
        """
        Attach an allowance to this structure and target every employee
        currently assigned to this structure through an active contract.
        """
        self.allowances.add(allowance)
        for contract in self._active_contracts():
            allowance.specific_employees.add(contract.employee_id)

    def remove_allowance(self, allowance):
        """
        Detach an allowance from this structure and stop targeting employees
        assigned to this structure, unless another structure they're on also
        includes the same allowance.
        """
        self.allowances.remove(allowance)
        for contract in self._active_contracts():
            still_targeted = (
                allowance.salary_structures.exclude(pk=self.pk)
                .filter(contracts__employee_id=contract.employee_id)
                .exists()
            )
            if not still_targeted:
                allowance.specific_employees.remove(contract.employee_id)

    def add_deduction(self, deduction):
        """
        Attach a deduction to this structure and target every employee
        currently assigned to this structure through an active contract.
        """
        self.deductions.add(deduction)
        for contract in self._active_contracts():
            deduction.specific_employees.add(contract.employee_id)

    def remove_deduction(self, deduction):
        """
        Detach a deduction from this structure and stop targeting employees
        assigned to this structure, unless another structure they're on also
        includes the same deduction.
        """
        self.deductions.remove(deduction)
        for contract in self._active_contracts():
            still_targeted = (
                deduction.salary_structures.exclude(pk=self.pk)
                .filter(contracts__employee_id=contract.employee_id)
                .exists()
            )
            if not still_targeted:
                deduction.specific_employees.remove(contract.employee_id)

    def get_allowances_col(self):
        """
        Allowances column
        """
        return ", ".join(str(allowance) for allowance in self.allowances.all())

    def get_deductions_col(self):
        """
        Deductions column
        """
        return ", ".join(str(deduction) for deduction in self.deductions.all())

    def get_employees_col(self):
        """
        Assigned employees column
        """
        return ", ".join(
            str(contract.employee_id) for contract in self._active_contracts()
        )

    def get_update_url(self):
        """
        This method to get update url
        """
        return reverse_lazy("update-salary-structure", kwargs={"pk": self.pk})

    def get_delete_url(self):
        """
        This method to get delete url
        """
        return reverse_lazy("generic-delete")

    def get_salary_structure_actions(self):
        """
        This method to get salary structure actions
        """
        return render_template(
            path="cbv/salary_structure/salary_structure_action.html",
            context={"instance": self},
        )

    def salary_structure_detail(self):
        """
        detail view
        """
        return reverse("salary-structure-detail-view", kwargs={"pk": self.pk})

    def get_employees_detail_col(self):
        """
        Employees column for the detail view, returned as a queryset so the
        `linkify` filter can render each one as a link to its own detail view.
        """
        return Employee.objects.filter(
            id__in=[contract.employee_id_id for contract in self._active_contracts()]
        )

    def get_allowances_detail_col(self):
        """
        Allowances column for the detail view
        """
        return render_template(
            path="cbv/salary_structure/allowances_detail_col.html",
            context={"instance": self},
        )

    def get_deductions_detail_col(self):
        """
        Deductions column for the detail view
        """
        return render_template(
            path="cbv/salary_structure/deductions_detail_col.html",
            context={"instance": self},
        )

    def salary_structure_detail_actions(self):
        """
        Footer actions for the detail view
        """
        return render_template(
            path="cbv/salary_structure/detail_view_actions.html",
            context={"instance": self},
        )


class Payslip(HorillaModel):
    """
    Payslip model
    """

    status_choices = [
        ("draft", _("Draft")),
        ("review_ongoing", _("Review Ongoing")),
        ("confirmed", _("Confirmed")),
        ("paid", _("Paid")),
    ]
    group_name = models.CharField(
        max_length=50, null=True, blank=True, verbose_name=_("Batch name")
    )
    reference = models.CharField(max_length=255, unique=False, null=True, blank=True)
    employee_id = models.ForeignKey(
        Employee, on_delete=models.PROTECT, verbose_name=_("Employee")
    )
    start_date = models.DateField()
    end_date = models.DateField()
    pay_head_data = models.JSONField()
    contract_wage = models.FloatField(null=True, default=0)
    basic_pay = models.FloatField(null=True, default=0)
    gross_pay = models.FloatField(null=True, default=0)
    deduction = models.FloatField(null=True, default=0)
    net_pay = models.FloatField(null=True, default=0)
    status = models.CharField(
        max_length=20, null=True, default="draft", choices=status_choices
    )
    sent_to_employee = models.BooleanField(null=True, default=False)
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")
    installment_ids = models.ManyToManyField(Deduction, editable=False)
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )

    def __str__(self) -> str:
        return f"Payslip for {self.employee_id} - Period: {self.start_date} to {self.end_date}"

    def get_status(self):
        """
        Display status
        """
        return dict(self.status_choices).get(self.status)

    def get_download_url(self):
        """
        This method to get download url
        """
        return render_template(
            path="cbv/payslip/payslip_download_tab.html",
            context={"instance": self},
        )

    def gross_pay_display(self):
        """
        gross pay
        """
        gross_pay = self.gross_pay

        return render_template(
            path="cbv/payslip/pay_display.html",
            context={"amount": gross_pay},
        )

    def deduction_display(self):
        """
        deduction
        """
        deduction = self.deduction

        return render_template(
            path="cbv/payslip/pay_display.html",
            context={"amount": deduction},
        )

    def net_pay_display(self):
        """
        net pay
        """
        net_pay = self.net_pay

        return render_template(
            path="cbv/payslip/pay_display.html",
            context={"amount": net_pay},
        )

    def custom_status_col(self):
        """
        custom status coloumn
        """

        return render_template(
            path="cbv/payslip/payslip_status_col.html",
            context={"instance": self},
        )

    def custom_actions_col(self):
        """
        custom actions coloumn
        """

        return render_template(
            path="cbv/payslip/payslip_actions.html",
            context={"instance": self},
        )

    def get_individual_payslip(self):
        """
        This method to get individual payslip
        """

        url = reverse_lazy("view-created-payslip", kwargs={"payslip_id": self.pk})
        return url

    def clean(self):
        super().clean()
        today = date.today()
        if self.end_date < self.start_date:
            raise ValidationError(
                {
                    "end_date": _(
                        "The end date must be greater than or equal to the start date"
                    )
                }
            )
        if self.end_date > today:
            raise ValidationError(_("The end date cannot be in the future."))
        if self.start_date > today:
            raise ValidationError(_("The start date cannot be in the future."))

    def save(self, *args, **kwargs):
        if (
            Payslip.objects.filter(
                employee_id=self.employee_id,
                start_date=self.start_date,
                end_date=self.end_date,
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError(_("Employee ,start and end date must be unique"))

        if not isinstance(self.pay_head_data, (QueryDict, dict)):
            raise ValidationError(_("The data must be in dictionary or querydict type"))

        super().save(*args, **kwargs)

    def get_name(self):
        """
        Method is used to get the full name of the owner
        """
        return self.employee_id.get_full_name()

    def get_company(self):
        """
        Method is used to get the full name of the owner
        """
        return getattr(
            getattr(
                getattr(getattr(self, "employee_id", None), "employee_work_info", None),
                "company_id",
                None,
            ),
            "company",
            None,
        )

    def get_payslip_title(self):
        """
        Method to generate the title for a payslip.
        Returns:
            str: The title for the payslip.
        """
        if self.group_name:
            return self.group_name
        return (
            f"Payslip {self.start_date} to {self.end_date} for {self.employee_id}"
            if self.start_date != self.end_date
            else f"Payslip for {self.start_date} for {self.employee_id}"
        )

    def get_days_in_month(self):
        year = self.start_date.year
        month = self.start_date.month
        return calendar.monthrange(year, month)[1]

    class Meta:
        """
        Meta class for additional options
        """

        ordering = [
            "-end_date",
        ]
        # Meta.ordering sorts every unqualified Payslip query by -end_date,
        # and the UniqueConstraint below leads on employee_id so it cannot
        # serve that sort. Payroll registers also filter by status within a
        # period.
        indexes = [
            models.Index(fields=["-end_date"], name="payslip_end_date_idx"),
            models.Index(fields=["status", "end_date"], name="payslip_status_date_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["employee_id", "start_date", "end_date"],
                name="unique_payslip_per_employee_period",
            )
        ]


class LoanAccount(HorillaModel):
    """
    This modal is used to store the loan Account details
    """

    loan_type = [
        ("loan", _("Loan")),
        ("advanced_salary", _("Salary Advance")),
        ("fine", _("Penalty / Fine")),
    ]
    title = models.CharField(max_length=100)
    employee_id = models.ForeignKey(
        Employee, on_delete=models.PROTECT, verbose_name=_("Employee")
    )
    type = models.CharField(default="loan", choices=loan_type, max_length=15)
    loan_amount = models.FloatField(default=0, verbose_name=_("Amount"))
    provided_date = models.DateField()
    allowance_id = models.ForeignKey(
        Allowance, on_delete=models.SET_NULL, editable=False, null=True
    )
    description = models.TextField(null=True)
    deduction_ids = models.ManyToManyField(Deduction, editable=False)
    is_fixed = models.BooleanField(default=True, editable=False)
    rate = models.FloatField(default=0, editable=False)
    installment_amount = models.FloatField(
        verbose_name=_("installment Amount"), blank=True, null=True
    )
    installments = models.IntegerField(verbose_name=_("Total installments"))
    installment_start_date = models.DateField(
        help_text=_("From the start date deduction will apply"),
        verbose_name=_("Installment start date"),
    )
    apply_on = models.CharField(default="end_of_month", max_length=20, editable=False)
    settled = models.BooleanField(default=False, verbose_name=_("Settled"))
    settled_date = models.DateTimeField(null=True)

    if apps.is_installed("asset"):
        asset_id = models.ForeignKey(
            "asset.Asset",
            on_delete=models.PROTECT,
            blank=True,
            null=True,
            editable=False,
        )
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    def __str__(self):
        return f"{self.title} - {self.employee_id}"

    def installment_paid(self):
        installment_paid = Payslip.objects.filter(
            installment_ids__in=self.deduction_ids.all()
        ).count()
        return installment_paid

    def total_installments(self):
        return self.installments

    def loan_actions(self):
        """
        This method for get loan actions.
        """

        return render_template(
            path="cbv/loan/loan_actions.html",
            context={"instance": self},
        )

    def get_delete_url(self):
        """
        This method to get delete url
        """
        base_url = reverse_lazy("delete-loan")
        message = "Do you want to delete this record?"
        loan_id = self.pk
        url = f"{base_url}?ids={loan_id}"
        return f"'{url}'" + "," + f"'{message}'"

    # def delete_url(self):
    #     """
    #     Edit url
    #     """

    #     return reverse("delete-loan", kwargs={"pk": self.pk})

    def edit_url(self):
        """
        Edit url
        """
        return reverse("loan-edit-form", kwargs={"pk": self.pk})

    def progress_bar_col(self):
        """
        This method for get progress bar col.
        """

        return render_template(
            path="cbv/loan/loan_card.html",
            context={
                "instance": self,
                "total_installments": self.total_installments,
                "installment_paid": self.installment_paid,
            },
        )

    def loan_detail_view(self):
        """
        for detail view of page
        """
        url = reverse("loan-detail-view", kwargs={"pk": self.pk})
        return url

    def detail_subtitle(self):
        """
        Return subtitle containing both department and job position information.
        """
        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def get_installments(self):
        """
        Method to calculate installment schedule for the loan.

        Returns:
            dict: A dictionary representing the installment schedule with installment dates as keys
            and corresponding installment amounts as values.
        """
        loan_amount = self.loan_amount
        total_installments = self.installments
        installment_amount = loan_amount / total_installments
        installment_start_date = self.installment_start_date

        installment_schedule = {}

        installment_date = installment_start_date
        installment_schedule = {}
        for _unused in range(total_installments):
            installment_schedule[str(installment_date)] = installment_amount
            installment_date = get_next_month_same_date(installment_date)

        return installment_schedule

    def delete(self, *args, **kwargs):
        """
        Method to delete the instance and associated objects.
        """
        self.deduction_ids.all().delete()
        if self.allowance_id is not None:
            self.allowance_id.delete()
        if not Payslip.objects.filter(
            installment_ids__in=list(self.deduction_ids.values_list("id", flat=True))
        ).exists():
            super().delete(*args, **kwargs)
        return

    def installment_ratio(self):
        """
        Method to calculate the ratio of paid installments to total installments in loan account.
        """
        total_installments = self.installments
        installment_paid = Payslip.objects.filter(
            installment_ids__in=self.deduction_ids.all()
        ).count()
        if not installment_paid:
            return 0
        ratio = (installment_paid / total_installments) * 100

        return ratio

    def save(self, *args, **kwargs):

        if self.settled:
            self.settled_date = timezone.now()
        else:
            self.settled_date = None

        super().save(*args, **kwargs)


class ReimbursementMultipleAttachment(models.Model):
    """
    ReimbursementMultipleAttachement Model
    """

    attachment = models.FileField(upload_to=upload_path)
    objects = models.Manager()


class Reimbursement(HorillaModel):
    """
    Reimbursement Model
    """

    reimbursement_types = [
        ("reimbursement", _("Reimbursement")),
        ("bonus_encashment", _("Bonus Point Encashment")),
    ]

    if apps.is_installed("leave"):
        reimbursement_types.append(("leave_encashment", _("Leave Encashment")))

    status_types = [
        ("requested", _("Requested")),
        ("approved", _("Approved")),
        ("rejected", _("Rejected")),
    ]
    title = models.CharField(max_length=50)
    type = models.CharField(
        choices=reimbursement_types, max_length=16, default="reimbursement"
    )
    employee_id = models.ForeignKey(
        Employee, on_delete=models.PROTECT, verbose_name="Employee"
    )
    allowance_on = models.DateField()
    attachment = models.FileField(upload_to=upload_path, null=True)
    other_attachments = models.ManyToManyField(
        ReimbursementMultipleAttachment, blank=True, editable=False
    )
    if apps.is_installed("leave"):
        leave_type_id = models.ForeignKey(
            "leave.LeaveType",
            on_delete=models.PROTECT,
            blank=True,
            null=True,
            verbose_name=_("Leave type"),
        )
    ad_to_encash = models.FloatField(
        default=0,
        help_text=_("Available Days to encash"),
        verbose_name=_("Available days"),
    )
    cfd_to_encash = models.FloatField(
        default=0,
        help_text=_("Carry Forward Days to encash"),
        verbose_name=_("Carry forward days"),
    )
    bonus_to_encash = models.IntegerField(
        default=0,
        help_text=_("Bonus points to encash"),
        verbose_name=_("Bonus points"),
    )
    amount = models.FloatField(default=0)
    status = models.CharField(
        max_length=10,
        choices=status_types,
        default="requested",
    )
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        related_name="approved_by",
        editable=False,
    )
    description = models.TextField(null=True)
    allowance_id = models.ForeignKey(
        Allowance, on_delete=models.SET_NULL, null=True, editable=False
    )
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        ordering = ["-id"]

    def save(self, *args, **kwargs) -> None:
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        amount_for_leave = (
            EncashmentGeneralSettings.objects.first().leave_amount
            if EncashmentGeneralSettings.objects.first()
            else 1
        )
        amount_for_bonus = (
            EncashmentGeneralSettings.objects.first().bonus_amount
            if EncashmentGeneralSettings.objects.first()
            else 1
        )

        # Setting the created use if the used dont have the permission
        has_perm = request.user.has_perm("payroll.change_reimbursement")
        if not has_perm:
            self.employee_id = request.user.employee_get
        if self.type == "reimbursement" and self.attachment is None:
            raise ValidationError({"attachment": "This field is required"})
        if self.type == "leave_encashment" and self.leave_type_id is None:
            raise ValidationError({"leave_type_id": "This field is required"})
        if self.type == "leave_encashment":
            if self.status == "requested":
                self.amount = (
                    self.cfd_to_encash + self.ad_to_encash
                ) * amount_for_leave
            self.cfd_to_encash = max((round(self.cfd_to_encash * 2) / 2), 0)
            self.ad_to_encash = max((round(self.ad_to_encash * 2) / 2), 0)
            assigned_leave = self.leave_type_id.employee_available_leave.filter(
                employee_id=self.employee_id
            ).first()
        if self.type == "bonus_encashment":
            if self.status == "requested":
                self.amount = (self.bonus_to_encash) * amount_for_bonus
        if self.status != "approved" or self.allowance_id is None:
            super().save(*args, **kwargs)
            if self.status == "approved" and self.allowance_id is None:
                if self.type == "reimbursement":
                    proceed = True
                elif self.type == "bonus_encashment":
                    proceed = False
                    bonus_points = BonusPoint.objects.get(employee_id=self.employee_id)
                    if bonus_points.points >= self.bonus_to_encash:
                        proceed = True
                        bonus_points.points -= self.bonus_to_encash
                        bonus_points.reason = "bonus points has been redeemed."
                        bonus_points.save()
                    else:
                        request = getattr(
                            horilla_middlewares._thread_locals, "request", None
                        )
                        if request:
                            messages.info(
                                request,
                                "The employee don't have that much bonus points to encash.",
                            )
                else:
                    proceed = False
                    if assigned_leave:
                        available_days = assigned_leave.available_days
                        carryforward_days = assigned_leave.carryforward_days
                        if (
                            available_days >= self.ad_to_encash
                            and carryforward_days >= self.cfd_to_encash
                        ):
                            proceed = True
                            assigned_leave.available_days = (
                                available_days - self.ad_to_encash
                            )
                            assigned_leave.carryforward_days = (
                                carryforward_days - self.cfd_to_encash
                            )
                            assigned_leave.save()
                        else:
                            request = getattr(
                                horilla_middlewares._thread_locals, "request", None
                            )
                            if request:
                                messages.info(
                                    request,
                                    _(
                                        "The employee don't have that much leaves \
                                        to encash in CFD / Available days"
                                    ),
                                )

                if proceed:
                    reimbursement = Allowance()
                    reimbursement.one_time_date = self.allowance_on
                    reimbursement.title = self.title
                    reimbursement.only_show_under_employee = True
                    reimbursement.include_active_employees = False
                    reimbursement.amount = self.amount
                    reimbursement.save()
                    reimbursement.include_active_employees = False
                    reimbursement.specific_employees.add(self.employee_id)
                    reimbursement.save()
                    self.allowance_id = reimbursement
                    if request:
                        self.approved_by = request.user.employee_get
                else:
                    self.status = "requested"
                super().save(*args, **kwargs)
            elif self.status == "rejected" and self.allowance_id is not None:
                cfd_days = self.cfd_to_encash
                available_days = self.ad_to_encash
                if self.type == "leave encashment":
                    if assigned_leave:
                        assigned_leave.available_days = (
                            assigned_leave.available_days + available_days
                        )
                        assigned_leave.carryforward_days = (
                            assigned_leave.carryforward_days + cfd_days
                        )
                        assigned_leave.save()
                    self.allowance_id.delete()

    def delete(self, *args, **kwargs):
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if self.status == "approved":
            message = messages.info(
                request,
                _(
                    f"{self.title} is in approved state,\
                    it cannot be deleted"
                ),
            )
        else:
            if self.allowance_id:
                self.allowance_id.delete()
                super().delete(*args, **kwargs)
                message = messages.success(request, _("Reimbursement deleted"))

        return message

    def __str__(self):
        return f"{self.title}"

    def get_status_display(self):
        """
        Display status types
        """
        return dict(self.status_types).get(self.status)

    def comment_col(self):
        """
        This method for get custom coloumn .
        """

        return render_template(
            path="cbv/reimbursements/comment.html",
            context={"instance": self},
        )

    def options_col(self):
        """
        This method for get custom coloumn .
        """

        return render_template(
            path="cbv/reimbursements/options.html",
            context={"instance": self},
        )

    def actions_col(self):
        """
        This method for get custom coloumn .
        """

        return render_template(
            path="cbv/reimbursements/actions.html",
            context={"instance": self},
        )

    def amount_col(self):
        """
        This method for get custom column for amount .
        """

        return render_template(
            path="cbv/reimbursements/amount.html",
            context={"instance": self},
        )

    def attachments_col(self):
        """
        This method for get custom column for attachment .
        """

        return render_template(
            path="cbv/reimbursements/attachments.html",
            context={"instance": self},
        )

    def detail_action_col(self):
        """
        This method for get custom column for actions in detail .
        """

        return render_template(
            path="cbv/reimbursements/detail_actions.html",
            context={"instance": self},
        )

    def reimbursements_detail_view(self):
        """
        for detail view of reimbursements
        """
        url = reverse("detail-view-reimbursement", kwargs={"pk": self.pk})
        return url

    def leave_encash_detail_view(self):
        """
        for detail view of leave encashments.
        """
        url = reverse("detail-view-leave-encashment", kwargs={"pk": self.pk})
        return url

    def bonus_encash_detail_view(self):
        """
        for detail view of bonus encashments.
        """
        url = reverse("detail-view-bonus-encashment", kwargs={"pk": self.pk})
        return url


class ReimbursementFile(models.Model):
    file = models.FileField(upload_to=upload_path)
    objects = models.Manager()


class ReimbursementrequestComment(HorillaModel):
    """
    ReimbursementRequestComment Model
    """

    request_id = models.ForeignKey(Reimbursement, on_delete=models.CASCADE)
    employee_id = models.ForeignKey(Employee, on_delete=models.CASCADE)
    comment = models.TextField(null=True, verbose_name=_("Comment"), max_length=255)
    files = models.ManyToManyField(ReimbursementFile, blank=True)
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        null=True,
    )

    def __str__(self) -> str:
        return f"{self.comment}"


class PayrollGeneralSetting(models.Model):
    """
    PayrollGeneralSetting
    """

    notice_period = models.IntegerField(
        help_text=_("Notice period in days"),
        validators=[min_zero],
        default=30,
    )
    company_id = models.ForeignKey(Company, on_delete=models.CASCADE, null=True)
    objects = HorillaCompanyManager("company_id")


class EncashmentGeneralSettings(models.Model):
    """
    BonusPointGeneralSettings model
    """

    bonus_amount = models.IntegerField(default=1)
    leave_amount = models.IntegerField(blank=True, null=True, verbose_name="Amount")
    objects = models.Manager()


DAYS = [
    ("last day", _("Last Day")),
    ("1", "1st"),
    ("2", "2nd"),
    ("3", "3rd"),
    ("4", "4th"),
    ("5", "5th"),
    ("6", "6th"),
    ("7", "7th"),
    ("8", "8th"),
    ("9", "9th"),
    ("10", "10th"),
    ("11", "11th"),
    ("12", "12th"),
    ("13", "13th"),
    ("14", "14th"),
    ("15", "15th"),
    ("16", "16th"),
    ("17", "17th"),
    ("18", "18th"),
    ("19", "19th"),
    ("20", "20th"),
    ("21", "21th"),
    ("22", "22th"),
    ("23", "23th"),
    ("24", "24th"),
    ("25", "25th"),
    ("26", "26th"),
    ("27", "27th"),
    ("28", "28th"),
    ("29", "29th"),
    ("30", "30th"),
    ("31", "31th"),
]


class PayslipAutoGenerate(models.Model):
    """
    Model for generating payslip automatically
    """

    generate_day = models.CharField(
        max_length=30,
        choices=DAYS,
        default=("1"),
        verbose_name=_("Payslip Generate Day"),
        help_text=_("On this day of every month,Payslip will auto generate"),
    )
    auto_generate = models.BooleanField(default=False, verbose_name=_("Auto Generate"))
    company_id = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Company"),
    )
    objects = HorillaCompanyManager(related_company_field="company_id")

    def get_generate_day_display(self):
        """
        Display work type
        """
        return dict(DAYS).get(self.generate_day)

    def get_company(self):
        if self.company_id:
            return self.company_id
        return "All company"

    def is_active_col(self):
        """
        is active column
        """
        return render_template(
            path="cbv/settings/is_active_col.html", context={"instance": self}
        )

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("pay-slip-automation-update", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("delete-auto-payslip", kwargs={"auto_id": self.pk})
        return url

    def get_instance_id(self):
        return self.id

    def clean(self):
        # Unique condition checking for all company
        if (
            not self.company_id
            and PayslipAutoGenerate.objects.filter(company_id=None).exists()
        ):
            if not self.id:
                raise ValidationError(
                    {
                        "company_id": "Auto payslip generation for all company is already exists"
                    }
                )
            all_company_auto_payslip = PayslipAutoGenerate.objects.filter(
                company_id=None
            ).first()
            if all_company_auto_payslip.id != self.id:
                raise ValidationError(
                    {
                        "company_id": "Auto payslip generation for all company is already exists"
                    }
                )

    def save(self, *args, **kwargs):
        from payroll.scheduler import auto_payslip_generate

        if self.auto_generate:
            auto_payslip_generate()

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.generate_day} | {self.company_id} "
