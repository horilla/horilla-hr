"""
This module is used to register django models
"""

import ipaddress
from datetime import date, datetime

from django.apps import apps
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Case, Q, When
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from horilla import horilla_middlewares
from horilla.horilla_middlewares import _thread_locals
from horilla.methods import get_horilla_model_class
from horilla.models import HorillaModel, NoPermissionModel, upload_path
from horilla_audit.models import HorillaAuditInfo, HorillaAuditLog
from horilla_auth.models import HorillaUser
from horilla_views.cbv_methods import render_template

# Create your models here.
WEEKS = [
    ("0", _("First Week")),
    ("1", _("Second Week")),
    ("2", _("Third Week")),
    ("3", _("Fourth Week")),
    ("4", _("Fifth Week")),
]

WEEK_DAYS = [
    ("0", _("Monday")),
    ("1", _("Tuesday")),
    ("2", _("Wednesday")),
    ("3", _("Thursday")),
    ("4", _("Friday")),
    ("5", _("Saturday")),
    ("6", _("Sunday")),
]

DAY_DATE = [(str(i), str(i)) for i in range(1, 32)]
DAY_DATE.append(("last", _("Last Day")))

DAY = [
    ("monday", _("Monday")),
    ("tuesday", _("Tuesday")),
    ("wednesday", _("Wednesday")),
    ("thursday", _("Thursday")),
    ("friday", _("Friday")),
    ("saturday", _("Saturday")),
    ("sunday", _("Sunday")),
]

BASED_ON = [
    ("after", _("After")),
    ("weekly", _("Weekend")),
    ("monthly", _("Monthly")),
]


def validate_time_format(value):
    """
    this method is used to validate the format of duration like fields.
    """
    if len(value) > 6:
        raise ValidationError(_("Invalid format, it should be HH:MM format"))
    try:
        hour, minute = value.split(":")
        hour = int(hour)
        minute = int(minute)
        if len(str(hour)) > 3 or minute not in range(60):
            raise ValidationError(_("Invalid time, excepted HH:MM"))
    except ValueError as e:
        raise ValidationError(_("Invalid format,  excepted HH:MM")) from e


def clear_messages(request):
    """
    clear messages
    """
    storage = messages.get_messages(request)
    for message in storage:
        pass


class Company(HorillaModel):
    """
    Company model
    """

    company = models.CharField(max_length=50, verbose_name=_("Name"))
    hq = models.BooleanField(default=False)
    address = models.TextField(max_length=255)
    country = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    city = models.CharField(max_length=50)
    zip = models.CharField(max_length=20)
    icon = models.FileField(
        upload_to=upload_path,
        null=True,
    )
    objects = models.Manager()
    date_format = models.CharField(max_length=30, blank=True, null=True)
    time_format = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Company")
        verbose_name_plural = _("Companies")
        unique_together = ["company", "address"]
        app_label = "base"

    def __str__(self) -> str:
        return str(self.company)

    def company_icon_with_name(self):

        return format_html(
            '<img src="{}" style="width: 30px; border-radius: 100%; display:inline;" class="oh-profile__image" alt="" /> {}',
            self.icon.url,
            self.company,
        )

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("company-update-form", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("generic-delete")
        return url

    def get_delete_instance(self):
        """
        to get instance for delete
        """

        return self.pk


class CompanyGroupAssignment(HorillaModel):
    """
    Company-scoped membership of a user in an auth Group.

    When settings.COMPANY_SCOPED_PERMISSIONS is enabled, a user's group
    permissions only apply in companies where such an assignment exists
    (resolved by base.auth_backends.CompanyScopedBackend). The plain
    ``user.groups`` M2M is kept in sync as the union of these rows so that
    disabling the flag instantly restores legacy global behavior.
    """

    user = models.ForeignKey(
        HorillaUser,
        on_delete=models.CASCADE,
        related_name="company_group_assignments",
        verbose_name=_("User"),
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="group_assignments",
        verbose_name=_("Company"),
    )
    group = models.ForeignKey(
        "auth.Group",
        on_delete=models.CASCADE,
        related_name="company_assignments",
        verbose_name=_("Group"),
    )

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Company group assignment")
        verbose_name_plural = _("Company group assignments")
        unique_together = ["user", "company", "group"]
        app_label = "base"

    def __str__(self) -> str:
        return f"{self.user} - {self.group} @ {self.company}"

    @classmethod
    def sync_user_group_membership(cls, user, group):
        """
        Keep the plain ``user.groups`` M2M as the union of company
        assignments: member of the group in >=1 company -> in the M2M.
        """
        if cls.objects.filter(user=user, group=group).exists():
            user.groups.add(group)
        else:
            user.groups.remove(group)


class Department(HorillaModel):
    """
    Department model
    """

    department = models.CharField(
        max_length=50, blank=False, verbose_name=_("Department")
    )
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))

    objects = HorillaCompanyManager()

    class Meta:
        """
        meta
        """

        verbose_name = _("Department")
        verbose_name_plural = _("Departments")

    def clean(self, *args, **kwargs):
        super().clean(*args, **kwargs)
        request = getattr(_thread_locals, "request", None)
        if request and request.POST:
            company = request.POST.getlist("company_id", None)
            department = request.POST.get("department", None)
            if (
                Department.objects.filter(
                    company_id__id__in=company, department=department
                )
                .exclude(id=self.id)
                .exists()
            ):
                raise ValidationError(
                    _("This department already exists in this company")
                )
        return

    def toggle_count(self):
        return self.job_position.all().count()

    def get_department_col(self):
        """
        this method is to get custom department col in job position
        """

        return render_template(
            path="cbv/settings/job_position_dpt.html",
            context={"instance": self},
        )

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("settings-department-update", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("generic-delete")
        return url

    def get_delete_instance(self):
        """
        to get instance for delete
        """

        return self.pk

    def get_job_position_col(self):
        """
        this method is to get custom job position col in job position
        """

        return render_template(
            path="cbv/settings/position_in_job_position.html",
            context={"instance": self},
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.clean(*args, **kwargs)
        return self

    def __str__(self):
        return str(self.department)


class JobPosition(HorillaModel):
    """
    JobPosition model
    """

    job_position = models.CharField(
        max_length=50, blank=False, null=False, verbose_name=_("Job Position")
    )
    department_id = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="job_position",
        verbose_name=_("Department"),
    )
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))

    objects = HorillaCompanyManager("department_id__company_id")

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Job Position")
        verbose_name_plural = _("Job Positions")

    def __str__(self):
        return str(self.job_position + " - (" + self.department_id.department) + ")"

    def job_position_col(self):
        """
        This method for get custom column.
        """

        return render_template(
            path="cbv/settings/job_position_col_in_job_role.html",
            context={"instance": self},
        )

    def get_data_count(self):
        return self.jobrole_set.all().count()

    def job_role_col(self):
        """
        This method for get custom column.
        """

        return render_template(
            path="cbv/settings/job_role.html",
            context={"instance": self},
        )


class JobRole(HorillaModel):
    """JobRole model"""

    job_position_id = models.ForeignKey(
        JobPosition, on_delete=models.PROTECT, verbose_name=_("Job Position")
    )
    job_role = models.CharField(
        max_length=50, blank=False, null=True, verbose_name=_("Job Role")
    )
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))

    objects = HorillaCompanyManager("job_position_id__department_id__company_id")

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Job Role")
        verbose_name_plural = _("Job Roles")
        unique_together = ("job_position_id", "job_role")

    def __str__(self):
        return f"{self.job_role} - {self.job_position_id.job_position}"


class WorkType(HorillaModel):
    """
    WorkType model
    """

    work_type = models.CharField(max_length=50, verbose_name=_("Work Type"))
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))

    objects = HorillaCompanyManager()

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Work Type")
        verbose_name_plural = _("Work Types")

    def __str__(self) -> str:
        return str(self.work_type)

    def clean(self, *args, **kwargs):
        super().clean(*args, **kwargs)
        request = getattr(_thread_locals, "request", None)
        if request and request.POST:
            company = request.POST.getlist("company_id", None)
            work_type = request.POST.get("work_type", None)
            if (
                WorkType.objects.filter(company_id__id__in=company, work_type=work_type)
                .exclude(id=self.id)
                .exists()
            ):
                raise ValidationError(
                    _("This work type already exists in this company")
                )
        return

    def get_company_name(self):
        """
        Returns comma-separated company names for display in list views.
        Returns 'All Company' when no company is assigned.
        """
        companies = self.company_id.all()
        if companies.exists():
            return ", ".join(c.company for c in companies)
        return _("All Company")

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("work-type-update-form", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("generic-delete")
        return url

    def get_delete_instance(self):
        """
        to get instance for delete
        """

        return self.pk

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.clean(*args, **kwargs)
        return self


class RotatingWorkType(HorillaModel):
    """
    RotatingWorkType model
    """

    name = models.CharField(max_length=50, unique=True, verbose_name=_("Name"))
    work_type1 = models.ForeignKey(
        WorkType,
        on_delete=models.PROTECT,
        related_name="work_type1",
        verbose_name=_("Work Type 1"),
    )
    work_type2 = models.ForeignKey(
        WorkType,
        on_delete=models.PROTECT,
        related_name="work_type2",
        verbose_name=_("Work Type 2"),
    )
    employee_id = models.ManyToManyField(
        "employee.Employee",
        through="RotatingWorkTypeAssign",
        verbose_name=_("Employee"),
    )
    additional_data = models.JSONField(
        default=dict,
        blank=True,
        null=True,
    )
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Rotating Work Type")
        verbose_name_plural = _("Rotating Work Types")

    def __str__(self) -> str:
        return str(self.name)

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("rotating-work-type-update-form", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("generic-delete")
        return url

    def get_delete_instance(self):
        """
        to get instance for delete
        """

        return self.pk

    def get_additional_worktytpes(self):
        """
        this method is to get additional work types if exists
        """

        additional_work = self.additional_work_types()
        if additional_work:
            additional = "<br>".join([str(work) for work in additional_work])
            return additional
        return "None"

    def clean(self):
        if (
            self.work_type1_id
            and self.work_type2_id
            and self.work_type1_id == self.work_type2_id
        ):
            raise ValidationError(_("Select different work type continuously"))

        additional_work_types = (
            self.additional_data.get("additional_work_types", [])
            if self.additional_data
            else []
        )

        if (
            additional_work_types
            and self.work_type2_id is not None
            and str(self.work_type2_id) == additional_work_types[0]
        ):
            raise ValidationError(_("Select different work type continuously"))

        if (
            additional_work_types
            and self.work_type1_id is not None
            and str(self.work_type1_id) == additional_work_types[-1]
        ):
            raise ValidationError(_("Select different work type continuously"))

        for i in range(len(additional_work_types) - 1):
            if additional_work_types[i] and additional_work_types[i + 1]:
                if additional_work_types[i] == additional_work_types[i + 1]:
                    raise ValidationError(_("Select different work type continuously"))

    def additional_work_types(self):
        rotating_work_type = RotatingWorkType.objects.get(id=self.pk)
        additional_data = rotating_work_type.additional_data
        if additional_data:
            additional_work_type_ids = additional_data.get("additional_work_types")
            if additional_work_type_ids:
                additional_work_types = WorkType.objects.filter(
                    id__in=additional_work_type_ids
                )
            else:
                additional_work_types = None
        else:
            additional_work_types = None
        return additional_work_types


class RotatingWorkTypeAssign(HorillaModel):
    """
    RotatingWorkTypeAssign model
    """

    employee_id = models.ForeignKey(
        "employee.Employee",
        on_delete=models.PROTECT,
        null=True,
        verbose_name=_("Employee"),
    )
    rotating_work_type_id = models.ForeignKey(
        RotatingWorkType, on_delete=models.PROTECT, verbose_name=_("Rotating Work Type")
    )
    start_date = models.DateField(default=timezone.now, verbose_name=_("Start Date"))
    next_change_date = models.DateField(null=True, verbose_name=_("Next Switch"))
    current_work_type = models.ForeignKey(
        WorkType,
        null=True,
        on_delete=models.PROTECT,
        related_name="current_work_type",
        verbose_name=_("Current Work Type"),
    )
    next_work_type = models.ForeignKey(
        WorkType,
        null=True,
        on_delete=models.PROTECT,
        related_name="next_work_type",
        verbose_name=_("Next Work Type"),
    )
    based_on = models.CharField(
        max_length=10,
        choices=BASED_ON,
        null=False,
        blank=False,
        verbose_name=_("Based On"),
    )
    rotate_after_day = models.IntegerField(
        default=7, verbose_name=_("Rotate After Day")
    )
    rotate_every_weekend = models.CharField(
        max_length=10,
        default="monday",
        choices=DAY,
        blank=True,
        null=True,
        verbose_name=_("Rotate Every Weekend"),
    )
    rotate_every = models.CharField(
        max_length=10,
        default="1",
        choices=DAY_DATE,
        verbose_name=_("Rotate Every Month"),
    )
    additional_data = models.JSONField(
        default=dict,
        blank=True,
        null=True,
    )
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Rotating Work Type Assign")
        verbose_name_plural = _("Rotating Work Type Assigns")
        ordering = ["-next_change_date", "-employee_id__employee_first_name"]

    def clean(self):
        if self.start_date < timezone.now().date():
            raise ValidationError(_("Date must be greater than or equal to today"))

        if self.is_active and self.employee_id is not None:
            # Check if any other active record with the same parent already exists
            siblings = RotatingWorkTypeAssign.objects.filter(
                is_active=True, employee_id=self.employee_id
            )
            if siblings.exists() and siblings.first().id != self.id:
                raise ValidationError(_("Only one active record allowed per employee"))

    def rotate_data(self):
        """
        method for rotate col
        """

        return render_template(
            path="cbv/rotating_work_type/rotation_col.html",
            context={"instance": self},
        )

    def get_based_on_display(self):
        """
        Display work type
        """
        return dict(BASED_ON).get(self.based_on)

    def get_actions(self):
        """
        get different actions
        """

        return render_template(
            path="cbv/rotating_work_type/work_rotate_actions.html",
            context={"instance": self},
        )

    def work_rotate_detail_subtitle(self):
        """
        Return subtitle containing both department and job position information.
        """

        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def work_rotate_detail_view(self):
        """
        for detail view of page
        """
        url = reverse("work-rotating-detail-view", kwargs={"pk": self.pk})
        return url

    def individual_tab_work_rotate_detail_view(self):
        """
        for detail view of page in employee profile
        """
        url = reverse("individual-work-rotating-detail-view", kwargs={"pk": self.pk})
        return url

    def detail_is_active(self):
        """
        return active or not
        """

        if self.is_active:
            return "Is Active"
        else:
            return "Archived"

    def get_detail_view_actions(self):
        """
        get detail view actions
        """

        return render_template(
            path="cbv/rotating_work_type/rotate_detail_view_actions.html",
            context={"instance": self},
        )


class EmployeeType(HorillaModel):
    """
    EmployeeType model
    """

    employee_type = models.CharField(max_length=50, verbose_name=_("Employee Type"))
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))

    objects = HorillaCompanyManager()

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Employee Type")
        verbose_name_plural = _("Employee Types")

    def __str__(self) -> str:
        return str(self.employee_type)

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("employee-type-update-view", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("generic-delete")
        return url

    def get_instance_id(self):
        return self.id

    def clean(self, *args, **kwargs):
        super().clean(*args, **kwargs)
        request = getattr(_thread_locals, "request", None)
        if request and request.POST:
            company = request.POST.getlist("company_id", None)
            employee_type = request.POST.get("employee_type", None)
            if (
                EmployeeType.objects.filter(
                    company_id__id__in=company, employee_type=employee_type
                )
                .exclude(id=self.id)
                .exists()
            ):
                raise ValidationError(
                    _("This employee type already exists in this company")
                )
        return

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.clean(*args, **kwargs)
        return self


class EmployeeShiftDay(models.Model):
    """
    EmployeeShiftDay model
    """

    day = models.CharField(max_length=20, choices=DAY)
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))

    objects = HorillaCompanyManager()

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Employee Shift Day")
        verbose_name_plural = _("Employee Shift Days")

    def __str__(self) -> str:
        return str(_(self.day).capitalize())


class EmployeeShift(HorillaModel):
    """
    EmployeeShift model
    """

    employee_shift = models.CharField(
        max_length=50,
        null=False,
        blank=False,
        verbose_name=_("Employee Shift"),
    )
    days = models.ManyToManyField(EmployeeShiftDay, through="EmployeeShiftSchedule")
    weekly_full_time = models.CharField(
        max_length=6,
        default="40:00",
        null=True,
        blank=True,
        validators=[validate_time_format],
    )
    full_time = models.CharField(
        max_length=6, default="200:00", validators=[validate_time_format]
    )
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))
    if apps.is_installed("attendance"):
        grace_time_id = models.ForeignKey(
            "attendance.GraceTime",
            null=True,
            blank=True,
            related_name="employee_shift",
            on_delete=models.PROTECT,
            verbose_name=_("Grace Time"),
        )

    objects = HorillaCompanyManager()

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Employee Shift")
        verbose_name_plural = _("Employee Shifts")

    def __str__(self) -> str:
        return str(self.employee_shift)

    def get_grace_time(self):
        if self.grace_time_id:
            return self.grace_time_id
        else:
            return _("Nil")

    def get_instance_id(self):
        return self.id

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("employee-shift-update-view", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete  url
        """
        url = reverse_lazy("generic-delete")
        return url

    def clean(self, *args, **kwargs):
        super().clean(*args, **kwargs)
        request = getattr(_thread_locals, "request", None)
        if request and request.POST:
            company = request.POST.getlist("company_id", None)
            employee_shift = request.POST.get("employee_shift", None)
            if (
                EmployeeShift.objects.filter(
                    company_id__id__in=company, employee_shift=employee_shift
                )
                .exclude(id=self.id)
                .exists()
            ):
                raise ValidationError(
                    _("This employee shift already exists in this company")
                )
        return

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.clean(*args, **kwargs)
        return self


class EmployeeShiftSchedule(HorillaModel):
    """
    EmployeeShiftSchedule model
    """

    day = models.ForeignKey(
        EmployeeShiftDay, on_delete=models.PROTECT, related_name="day_schedule"
    )
    shift_id = models.ForeignKey(
        EmployeeShift, on_delete=models.PROTECT, verbose_name=_("Shift")
    )
    minimum_working_hour = models.CharField(
        default="08:15",
        max_length=5,
        validators=[validate_time_format],
        verbose_name=_("Minimum Working Hours"),
    )
    start_time = models.TimeField(null=True, verbose_name=_("Start Time"))
    end_time = models.TimeField(null=True, verbose_name=_("End Time"))
    is_night_shift = models.BooleanField(default=False, verbose_name=_("Night Shift"))
    is_auto_punch_out_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Enable Automatic Check Out"),
        help_text=_("Enable this to trigger automatic check out."),
    )
    auto_punch_out_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name=_("Automatic Check Out Time"),
        help_text=_(
            "Time at which the horilla will automatically check out the employee attendance if they forget."
        ),
    )

    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))

    objects = HorillaCompanyManager()

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Employee Shift Schedule")
        verbose_name_plural = _("Employee Shift Schedules")
        unique_together = [["shift_id", "day"]]
        ordering = [
            Case(
                When(day__day="monday", then=0),
                When(day__day="tuesday", then=1),
                When(day__day="wednesday", then=2),
                When(day__day="thursday", then=3),
                When(day__day="friday", then=4),
                When(day__day="saturday", then=5),
                When(day__day="sunday", then=6),
                default=7,
            )
        ]

    def __str__(self) -> str:
        return f"{self.shift_id.employee_shift} {self.day}"

    def get_detail_url(self):
        """
        Detail view url
        """
        url = reverse_lazy("employee-shift-shedule-detail-view", kwargs={"pk": self.pk})
        return url

    def get_instance_id(self):
        return self.id

    def get_automatic_check_out_time(self):
        """
        Custom column for automatic checkout time
        """
        return (
            f"<div class='oh-timeoff-modal__stat-title'>Automatic Check Out Time</div><div>{self.auto_punch_out_time}</div>"
            if self.is_auto_punch_out_enabled
            else ""
        )

    def get_avatar(self):
        """
        Method will retun the api to the avatar or path to the profile image
        """
        url = f"https://ui-avatars.com/api/?name={self.day.day}&background=random"
        return url

    def actions_col(self):
        """
        This for actions column in employee shift schedule
        """
        return render_template(
            path="cbv/settings/employee_shift_schedule_action.html",
            context={"instance": self},
        )

    def detail_actions_col(self):
        """
        This for detail actions column in employee shift schedule
        """
        return render_template(
            path="cbv/settings/employee_shift_schedule_detail_action.html",
            context={"instance": self},
        )

    def auto_punch_out_col(self):
        return _("Yes") if self.is_auto_punch_out_enabled else _("No")

    def save(self, *args, **kwargs):
        if self.start_time and self.end_time:
            if self.start_time > self.end_time:
                self.is_night_shift = True
        super().save(*args, **kwargs)

    def day_col(self):
        """
        Custom column for day in employee shift schedule
        """

        return dict(DAY).get(self.day.day)


class RotatingShift(HorillaModel):
    """
    RotatingShift model
    """

    name = models.CharField(max_length=50)
    employee_id = models.ManyToManyField(
        "employee.Employee", through="RotatingShiftAssign", verbose_name=_("Employee")
    )
    shift1 = models.ForeignKey(
        EmployeeShift,
        related_name="shift1",
        on_delete=models.PROTECT,
        verbose_name=_("Shift 1"),
        blank=True,
        null=True,
    )
    shift2 = models.ForeignKey(
        EmployeeShift,
        related_name="shift2",
        on_delete=models.PROTECT,
        verbose_name=_("Shift 2"),
        blank=True,
        null=True,
    )
    additional_data = models.JSONField(
        default=dict,
        blank=True,
        null=True,
    )
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Rotating Shift")
        verbose_name_plural = _("Rotating Shifts")

    def __str__(self) -> str:
        return str(self.name)

    def get_additional_shifts(self):
        """
        Returns a list of additional shifts or a message if no additional shifts are available.
        """
        additional_shifts = self.additional_shifts()
        if additional_shifts:
            additional_shift = "<br>".join([str(shift) for shift in additional_shifts])
            return additional_shift
        return "None"

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("rotating-shift-update", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete  url
        """
        url = reverse_lazy("generic-delete")
        return url

    def get_instance_id(self):
        return self.id

    def clean(self):

        additional_shifts = (
            self.additional_data.get("additional_shifts", [])
            if self.additional_data
            else []
        )

        if additional_shifts and self.shift1 == self.shift2:
            raise ValidationError(_("Select different shift continuously"))

        #  ---------------- Removed the validation for same shifts to be continously added ----------------

        # if additional_shifts and str(self.shift2.id) == additional_shifts[0]:
        #     raise ValidationError(_("Select different shift continuously"))

        # if additional_shifts and str(self.shift1.id) == additional_shifts[-1]:
        #     raise ValidationError(_("Select different shift continuously"))

        # for i in range(len(additional_shifts) - 1):
        #     if additional_shifts[i] and additional_shifts[i + 1]:
        #         if additional_shifts[i] == additional_shifts[i + 1]:
        #             raise ValidationError(_("Select different shift continuously"))

    def additional_shifts(self):
        additional_data = self.additional_data
        if additional_data:
            additional_shift_ids = additional_data.get("additional_shifts")
            if additional_shift_ids:
                unique_ids = set(additional_shift_ids)
                shifts_dict = {
                    shift.id: shift
                    for shift in EmployeeShift.objects.filter(id__in=unique_ids)
                }
                additional_shifts = []
                for shift_id in additional_shift_ids:
                    if shift_id:
                        additional_shifts.append(shifts_dict[int(shift_id)])
                    else:
                        additional_shifts.append(None)
            else:
                additional_shifts = None
        else:
            additional_shifts = None
        return additional_shifts

    def total_shifts(self):
        total_shifts = []
        total_shifts += [self.shift1, self.shift2]
        if self.additional_shifts():
            total_shifts += list(self.additional_shifts())

        return total_shifts


class RotatingShiftAssign(HorillaModel):
    """
    RotatingShiftAssign model
    """

    employee_id = models.ForeignKey(
        "employee.Employee", on_delete=models.PROTECT, verbose_name=_("Employee")
    )
    rotating_shift_id = models.ForeignKey(
        RotatingShift, on_delete=models.PROTECT, verbose_name=_("Rotating Shift")
    )
    start_date = models.DateField(default=timezone.now, verbose_name=_("Start Date"))
    next_change_date = models.DateField(null=True, verbose_name=_("Next Switch"))
    current_shift = models.ForeignKey(
        EmployeeShift,
        on_delete=models.PROTECT,
        null=True,
        related_name="current_shift",
        verbose_name=_("Current Shift"),
    )
    next_shift = models.ForeignKey(
        EmployeeShift,
        on_delete=models.PROTECT,
        null=True,
        related_name="next_shift",
        verbose_name=_("Next Shift"),
    )
    based_on = models.CharField(
        max_length=10,
        choices=BASED_ON,
        null=False,
        blank=False,
        verbose_name=_("Based On"),
    )
    rotate_after_day = models.IntegerField(
        null=True, blank=True, default=7, verbose_name=_("Rotate After Day")
    )
    rotate_every_weekend = models.CharField(
        max_length=10,
        default="monday",
        choices=DAY,
        blank=True,
        null=True,
        verbose_name=_("Rotate Every Weekend"),
    )
    rotate_every = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        default="1",
        choices=DAY_DATE,
        verbose_name=_("Rotate Every Month"),
    )
    additional_data = models.JSONField(
        default=dict,
        blank=True,
        null=True,
    )
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    def rotating_column(self):
        """
        This method for get custom column.
        """

        return render_template(
            path="cbv/rotating_shift/rotating_column.html",
            context={"instance": self},
        )

    def actions(self):
        """
        This method for get custom column.
        """

        return render_template(
            path="cbv/rotating_shift/actions_rotaing_shift.html",
            context={"instance": self},
        )

    def rotating_detail_actions(self):
        """
        This method for get custom column.
        """

        return render_template(
            path="cbv/rotating_shift/rotating_shift_detail_actions.html",
            context={"instance": self},
        )

    def get_based_on_display(self):
        """
        Display work type
        """
        return dict(BASED_ON).get(self.based_on)

    def rotating_shift_detail(self):
        """
        detail view
        """

        url = reverse("rotating-shift-detail-view", kwargs={"pk": self.pk})

        return url

    def rotating_shift_individual_detail(self):
        """
        individual detail view
        """

        url = reverse("rotating-shift-individual-detail-view", kwargs={"pk": self.pk})

        return url

    def rotating_subtitle(self):
        """
        Detail view subtitle
        """

        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def check_active(self):
        """
        Check active
        """

        if self.is_active:
            return "Is Active"
        else:
            return "Archived"

    def detail_edit_url(self):
        """
        Detail view edit
        """

        url = reverse("rotating-shift-assign-update", kwargs={"id": self.pk})

        return url

    def detail_archive_url(self):
        """
        Detail view edit
        """

        url = reverse("rotating-shift-assign-archive", kwargs={"obj_id": self.pk})

        return url

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Rotating Shift Assign")
        verbose_name_plural = _("Rotating Shift Assigns")
        ordering = ["-next_change_date", "-employee_id__employee_first_name"]

    def clean(self):
        if self.is_active and self.employee_id_id is not None:
            # Check if any other active record with the same parent already exists
            siblings = RotatingShiftAssign.objects.filter(
                is_active=True, employee_id__id=self.employee_id_id
            )
            if siblings.exists() and siblings.first().id != self.id:
                raise ValidationError(_("Only one active record allowed per employee"))

        if self.start_date < timezone.now().date():
            raise ValidationError(_("Date must be greater than or equal to today"))


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


class Roster(HorillaModel):
    """
    Forward-planning shift roster entry: one employee, one date, one shift.
    Planners assign shifts in advance; employees see published entries via My Roster.
    """

    employee = models.ForeignKey(
        "employee.Employee",
        on_delete=models.CASCADE,
        related_name="roster_entries",
        verbose_name=_("Employee"),
    )
    date = models.DateField(verbose_name=_("Date"))
    shift = models.ForeignKey(
        "base.EmployeeShift",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="roster_entries",
        verbose_name=_("Shift"),
    )
    department = models.ForeignKey(
        "base.Department",
        on_delete=models.CASCADE,
        related_name="roster_entries",
        verbose_name=_("Department"),
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name=_("Published"),
        help_text=_("Visible to the employee once published."),
    )
    is_off = models.BooleanField(
        default=False,
        verbose_name=_("Day Off"),
        help_text=_("Planned weekly rest day."),
    )
    notes = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Notes"),
    )
    created_by = models.ForeignKey(
        "employee.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_roster_entries",
        verbose_name=_("Created By"),
    )

    objects = HorillaCompanyManager("employee__employee_work_info__company_id")

    class Meta:
        verbose_name = _("Roster Entry")
        verbose_name_plural = _("Roster Entries")
        unique_together = [("employee", "date")]

    def __str__(self):
        shift_label = "OFF" if self.is_off else self.shift or "-"
        return f"{self.employee} — {self.date} — {shift_label}"


class RosterPublishLog(models.Model):
    """
    Audit trail for each roster publish action.
    """

    department = models.ForeignKey(
        "base.Department",
        on_delete=models.CASCADE,
        related_name="roster_publish_logs",
        verbose_name=_("Department"),
    )
    from_date = models.DateField(verbose_name=_("From Date"))
    to_date = models.DateField(verbose_name=_("To Date"))
    published_by = models.ForeignKey(
        "employee.Employee",
        on_delete=models.SET_NULL,
        null=True,
        related_name="roster_publishes",
        verbose_name=_("Published By"),
    )
    published_on = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Published On"),
    )
    total_employees = models.IntegerField(
        default=0,
        verbose_name=_("Total Employees"),
    )

    objects = models.Manager()

    class Meta:
        verbose_name = _("Roster Publish Log")
        verbose_name_plural = _("Roster Publish Logs")
        ordering = ["-published_on"]

    def __str__(self):
        return f"{self.department} — {self.from_date} to {self.to_date}"


class BaserequestFile(models.Model):
    file = models.FileField(upload_to=upload_path)
    objects = models.Manager()


class WorkTypeRequest(HorillaModel):
    """
    WorkTypeRequest model
    """

    employee_id = models.ForeignKey(
        "employee.Employee",
        on_delete=models.PROTECT,
        null=True,
        related_name="work_type_request",
        verbose_name=_("Employee"),
    )
    work_type_id = models.ForeignKey(
        WorkType,
        on_delete=models.PROTECT,
        related_name="requested_work_type",
        verbose_name=_("Requesting Work Type"),
    )
    previous_work_type_id = models.ForeignKey(
        WorkType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="previous_work_type",
        verbose_name=_("Previous Work Type"),
    )
    requested_date = models.DateField(
        null=True, default=timezone.now, verbose_name=_("Requested Date")
    )
    requested_till = models.DateField(
        null=True, blank=True, verbose_name=_("Requested Till")
    )
    description = models.TextField(null=True, verbose_name=_("Description"))
    is_permanent_work_type = models.BooleanField(
        default=False, verbose_name=_("Permanent Request")
    )
    approved = models.BooleanField(default=False, verbose_name=_("Approved"))
    canceled = models.BooleanField(default=False, verbose_name=_("Canceled"))
    work_type_changed = models.BooleanField(default=False)
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Work Type Request")
        verbose_name_plural = _("Work Type Requests")
        permissions = (
            ("approve_worktyperequest", "Approve Work Type Request"),
            ("cancel_worktyperequest", "Cancel Work Type Request"),
        )
        ordering = [
            "-id",
        ]

    def comment_note(self):
        """
        method used for comment note col in the page
        """

        return render_template(
            path="cbv/work_type_request/note.html",
            context={"instance": self},
        )

    def work_actions(self):
        """
        method for rendering actions(edit,duplicate,delete)
        """

        return render_template(
            path="cbv/work_type_request/actions.html",
            context={"instance": self},
        )

    def confirmation(self):
        """
        method for rendering options(approve,reject)
        """

        return render_template(
            path="cbv/work_type_request/confirmation.html",
            context={"instance": self},
        )

    def detail_confirmation(self):
        """
        method for rendering options(approve,reject)
        """

        return render_template(
            path="cbv/work_type_request/detail_confirmation.html",
            context={"instance": self},
        )

    def detail_view(self):
        """
        for detail view of page
        """
        url = reverse("work-detail-view", kwargs={"pk": self.pk})
        return url

    def is_permanent_work_type_display(self):
        """
        Method to display "Yes" or "No" based on is_permanent_work_type value
        """
        return _("Yes") if self.is_permanent_work_type else _("No")

    def detail_view_actions(self):
        """
        method for rendering different options
        convert,skillzone,reject,mail
        """

        return render_template(
            path="cbv/work_type_request/detail_view_actions.html",
            context={"instance": self},
        )

    def detail_subtitle(self):
        """
        Return subtitle containing both department and job position information.
        """
        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def delete(self, *args, **kwargs):
        request = getattr(_thread_locals, "request", None)
        if not self.approved:
            super().delete(*args, **kwargs)
        else:
            if request:
                clear_messages(request)
                messages.warning(request, _("The request entry cannot be deleted."))

    def is_any_work_type_request_exists(self):
        approved_work_type_requests_range = WorkTypeRequest.objects.filter(
            employee_id=self.employee_id,
            approved=True,
            canceled=False,
            requested_date__range=[self.requested_date, self.requested_till],
            requested_till__range=[self.requested_date, self.requested_till],
        ).exclude(id=self.id)
        if approved_work_type_requests_range:
            return True
        approved_work_type_requests = WorkTypeRequest.objects.filter(
            employee_id=self.employee_id,
            approved=True,
            canceled=False,
            requested_date__lte=self.requested_date,
            requested_till__gte=self.requested_date,
        ).exclude(id=self.id)
        if approved_work_type_requests:
            return True
        if self.requested_till:
            approved_work_type_requests_2 = WorkTypeRequest.objects.filter(
                employee_id=self.employee_id,
                approved=True,
                canceled=False,
                requested_date__lte=self.requested_till,
                requested_till__gte=self.requested_till,
            ).exclude(id=self.id)
            if approved_work_type_requests_2:
                return True
        approved_permanent_req = WorkTypeRequest.objects.filter(
            employee_id=self.employee_id,
            approved=True,
            canceled=False,
            requested_date__exact=self.requested_date,
        )
        if approved_permanent_req:
            return True
        return False

    def clean(self):
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if not request.user.is_superuser:
            if self.requested_date < timezone.now().date():
                raise ValidationError(_("Date must be greater than or equal to today"))
        if self.requested_till and self.requested_till < self.requested_date:
            raise ValidationError(
                _("End date must be greater than or equal to start date")
            )
        if self.is_any_work_type_request_exists():
            raise ValidationError(
                _("A work type request already exists during this time period.")
            )
        if not self.is_permanent_work_type:
            if not self.requested_till:
                raise ValidationError(_("Requested till field is required."))

    def request_status(self):
        return (
            _("Rejected")
            if self.canceled
            else (_("Approved") if self.approved else _("Requested"))
        )

    def __str__(self) -> str:
        return f"{self.employee_id.employee_first_name} \
            {self.employee_id.employee_last_name} - {self.requested_date}"


class WorkTypeRequestComment(HorillaModel):
    """
    WorkTypeRequestComment Model
    """

    from employee.models import Employee

    request_id = models.ForeignKey(WorkTypeRequest, on_delete=models.CASCADE)
    employee_id = models.ForeignKey(Employee, on_delete=models.CASCADE)
    comment = models.TextField(null=True, verbose_name=_("Comment"))
    files = models.ManyToManyField(BaserequestFile, blank=True)
    objects = models.Manager()

    def __str__(self) -> str:
        return f"{self.comment}"


class ShiftRequest(HorillaModel):
    """
    ShiftRequest model
    """

    employee_id = models.ForeignKey(
        "employee.Employee",
        on_delete=models.PROTECT,
        null=True,
        related_name="shift_request",
        verbose_name=_("Employee"),
    )
    shift_id = models.ForeignKey(
        EmployeeShift,
        on_delete=models.PROTECT,
        related_name="requested_shift",
        verbose_name=_("Requesting Shift"),
    )
    previous_shift_id = models.ForeignKey(
        EmployeeShift,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="previous_shift",
        verbose_name=_("Previous Shift"),
    )
    requested_date = models.DateField(
        null=True, default=timezone.now, verbose_name=_("Requested Date")
    )
    reallocate_to = models.ForeignKey(
        "employee.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reallocate_shift_request",
        verbose_name=_("Reallocate Employee"),
    )
    reallocate_approved = models.BooleanField(default=False, verbose_name=_("Approved"))
    reallocate_canceled = models.BooleanField(default=False, verbose_name=_("Canceled"))
    requested_till = models.DateField(
        null=True, blank=True, verbose_name=_("Requested Till")
    )
    description = models.TextField(null=True, verbose_name=_("Description"))
    is_permanent_shift = models.BooleanField(
        default=False, verbose_name=_("Permanent Request")
    )
    approved = models.BooleanField(default=False, verbose_name=_("Approved"))
    canceled = models.BooleanField(default=False, verbose_name=_("Canceled"))
    shift_changed = models.BooleanField(default=False)
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Shift Request")
        verbose_name_plural = _("Shift Requests")
        permissions = (
            ("approve_shiftrequest", "Approve Shift Request"),
            ("cancel_shiftrequest", "Cancel Shift Request"),
        )
        ordering = [
            "-id",
        ]

    def comment(self):
        """
        This method for get custom column for comment.
        """

        return render_template(
            path="cbv/shift_request/comment.html",
            context={"instance": self},
        )

    # def shift_allocate_actions(self):
    #     """
    #     This method for get custom column for allocated actions.
    #     """

    #     return render_template(
    #         path="cbv/shift_request/allocated_shift_actions.html",
    #         context={"instance": self},
    #     )

    def allocated_confirm_action_col(self):
        """
        This method for get custom column for allocated actions.
        """

        return render_template(
            path="cbv/shift_request/allocated_confirm_action.html",
            context={"instance": self},
        )

    def allocated_detail_confirm_action(self):
        """
        Action buttons for the Allocated Shift Request detail modal - same
        buttons, same order, same per-role conditions as
        allocated_confirm_action_col's row actions.
        """

        return render_template(
            path="cbv/shift_request/allocated_detail_confirm_action.html",
            context={"instance": self},
        )

    def user_availability(self):
        """
        This method for get custom column for HorillaUser availability.
        """

        return render_template(
            path="cbv/shift_request/user_availability.html",
            context={"instance": self},
        )

    def shift_details(self):
        """
        Detail view
        """

        url = reverse("shift-detail-view", kwargs={"pk": self.pk})

        return url

    def allocate_shift_details(self):
        """
        Allocate detail view
        """

        url = reverse("allocate-detail-view", kwargs={"pk": self.pk})

        return url

    def is_permanent(self):
        """
        Permanent shift
        """
        return _("Yes") if self.is_permanent_shift else _("No")

    def shift_actions(self):
        """
        This method for get custom column for actions.
        """

        return render_template(
            path="cbv/shift_request/actions_shift_requst.html",
            context={"instance": self},
        )

    def shift_detail_confirm_action(self):
        """
        Action buttons for the Shift Request detail modal - same buttons,
        same order, same per-role conditions as shift_actions's row
        actions (Edit, Duplicate, Remove, Approve, Reject).
        """

        return render_template(
            path="cbv/shift_request/shift_detail_confirm_action.html",
            context={"instance": self},
        )

    def confirmations(self):
        """
        This method for get custom column for confirmations.
        """

        return render_template(
            path="cbv/shift_request/confirmations.html",
            context={"instance": self},
        )

    def detail_confirmations(self):

        return render_template(
            path="cbv/shift_request/detail_confirmations.html",
            context={"instance": self},
        )

    def allocate_confirmations(self):
        """
        This method for get custom column for confirmations.
        """

        return render_template(
            path="cbv/shift_request/confirm_allocated.html",
            context={"instance": self},
        )

    def detail_actions(self):
        """
        This method for get custom column for comment.
        """

        return render_template(
            path="cbv/shift_request/shift_detail_actions.html",
            context={"instance": self},
        )

    def request_status(self):
        return (
            _("Rejected")
            if self.canceled
            else (_("Approved") if self.approved else _("Requested"))
        )

    def details_subtitle(self):
        """
        Detail view subtitle
        """

        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def clean(self):

        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if not request.user.is_superuser:
            if not self.pk and self.requested_date < timezone.now().date():
                raise ValidationError(_("Date must be greater than or equal to today"))
        if self.requested_till and self.requested_till < self.requested_date:
            raise ValidationError(
                _("End date must be greater than or equal to start date")
            )
        if self.is_any_request_exists():
            raise ValidationError(
                _("An approved shift request already exists during this time period.")
            )
        if not self.is_permanent_shift:
            if not self.requested_till:
                raise ValidationError(_("Requested till field is required."))

    def is_any_request_exists(self):
        approved_shift_requests_range = ShiftRequest.objects.filter(
            employee_id=self.employee_id,
            approved=True,
            canceled=False,
            requested_date__range=[self.requested_date, self.requested_till],
            requested_till__range=[self.requested_date, self.requested_till],
        ).exclude(id=self.id)
        if approved_shift_requests_range:
            return True
        approved_shift_requests = ShiftRequest.objects.filter(
            employee_id=self.employee_id,
            approved=True,
            canceled=False,
            requested_date__lte=self.requested_date,
            requested_till__gte=self.requested_date,
        ).exclude(id=self.id)
        if approved_shift_requests:
            return True
        if self.requested_till:
            approved_shift_requests_2 = ShiftRequest.objects.filter(
                employee_id=self.employee_id,
                approved=True,
                canceled=False,
                requested_date__lte=self.requested_till,
                requested_till__gte=self.requested_till,
            ).exclude(id=self.id)
            if approved_shift_requests_2:
                return True
        approved_permanent_req = ShiftRequest.objects.filter(
            employee_id=self.employee_id,
            approved=True,
            canceled=False,
            requested_date__exact=self.requested_date,
        )
        if approved_permanent_req:
            return True
        return False

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        request = getattr(_thread_locals, "request", None)
        if not self.approved:
            super().delete(*args, **kwargs)
        else:
            if request:
                clear_messages(request)
                messages.warning(request, _("The request entry cannot be deleted."))

    def __str__(self) -> str:
        return f"{self.employee_id.employee_first_name} \
            {self.employee_id.employee_last_name} - {self.requested_date}"


class ShiftRequestComment(HorillaModel):
    """
    ShiftRequestComment Model
    """

    from employee.models import Employee

    request_id = models.ForeignKey(ShiftRequest, on_delete=models.CASCADE)
    employee_id = models.ForeignKey(Employee, on_delete=models.CASCADE)
    files = models.ManyToManyField(BaserequestFile, blank=True)
    comment = models.TextField(null=True, verbose_name=_("Comment"))
    objects = models.Manager()

    def __str__(self) -> str:
        return f"{self.comment}"


class Tags(HorillaModel):
    title = models.CharField(max_length=30)
    color = models.CharField(max_length=30)
    company_id = models.ForeignKey(
        Company, null=True, editable=False, on_delete=models.PROTECT
    )
    objects = HorillaCompanyManager(related_company_field="company_id")

    class Meta:
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from base.auth_backends import stamp_company_on_create

        stamp_company_on_create(self)
        super().save(*args, **kwargs)

    def get_color(self):
        """
        This method returns the style string with the tag's color
        """
        color = (
            f"<span style='height: 25px; "
            f"width: 25px; "
            f"background-color: {self.color}; "
            f"border-radius: 50%; "
            f"display: inline-block;'></span>"
        )
        return color

    def get_instance_id(self):
        """
        To get instance
        """
        return self.id

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("update-helpdesk-tag", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("tag-delete", kwargs={"obj_id": self.pk})
        # message = "Are you sure you want to delete this tag ?"
        # return f"'{url}'" + "," + f"'{message}'"
        return url


class HorillaMailTemplate(HorillaModel):
    title = models.CharField(max_length=100, unique=True)
    body = models.TextField()
    company_id = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
    )
    objects = HorillaCompanyManager(related_company_field="company_id")

    def __str__(self) -> str:
        return f"{self.title}"


class DynamicEmailConfiguration(HorillaModel):
    """
    SingletonModel to keep the mail server configurations
    """

    host = models.CharField(null=True, max_length=256, verbose_name=_("Email Host"))

    port = models.SmallIntegerField(null=True, verbose_name=_("Email Port"))

    from_email = models.EmailField(
        null=True, max_length=256, verbose_name=_("Default From Email")
    )

    username = models.CharField(
        null=True,
        max_length=256,
        verbose_name=_("Email Host Username"),
    )

    display_name = models.CharField(
        null=True,
        max_length=256,
        verbose_name=_("Display Name"),
    )

    password = models.CharField(
        null=True,
        max_length=256,
        verbose_name=_("Email Authentication Password"),
    )

    use_tls = models.BooleanField(default=True, verbose_name=_("Use TLS"))

    use_ssl = models.BooleanField(default=False, verbose_name=_("Use SSL"))

    fail_silently = models.BooleanField(default=False, verbose_name=_("Fail Silently"))

    is_primary = models.BooleanField(
        default=False, verbose_name=_("Primary Mail Server")
    )
    use_dynamic_display_name = models.BooleanField(
        default=True,
        help_text=_(
            "By enabling this the display name will take from who triggered the mail"
        ),
        verbose_name=_("Use dynamic display name"),
    )

    timeout = models.SmallIntegerField(
        null=True, verbose_name=_("Email Send Timeout (seconds)")
    )
    company_id = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Company"),
    )

    def highlight_cell(self):
        if self.is_primary:
            return 'class="bg-primary-50"'

    def action_col(self):
        """
        This method for get custom column.
        """

        return render_template(
            path="cbv/settings/mail_server_action.html",
            context={"instance": self},
        )

    def clean(self):
        if self.use_ssl and self.use_tls:
            raise ValidationError(
                _(
                    '"Use TLS" and "Use SSL" are mutually exclusive, '
                    "so only set one of those settings to True."
                )
            )
        if not self.company_id and not self.is_primary:
            raise ValidationError({"company_id": _("This field is required")})

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs) -> None:
        if self.is_primary:
            DynamicEmailConfiguration.objects.filter(is_primary=True).update(
                is_primary=False
            )
        if not DynamicEmailConfiguration.objects.exists():
            self.is_primary = True

        super().save(*args, **kwargs)
        servers_same_company = DynamicEmailConfiguration.objects.filter(
            company_id=self.company_id
        ).exclude(id=self.id)
        if servers_same_company.exists():
            self.delete()
        return

    class Meta:
        verbose_name = _("Email Configuration")


FIELD_CHOICE = [
    ("", "---------"),
    ("requested_days", _("Leave Requested Days")),
]
CONDITION_CHOICE = [
    ("equal", _("Equal (==)")),
    ("notequal", _("Not Equal (!=)")),
    ("range", _("Range")),
    ("lt", _("Less Than (<)")),
    ("gt", _("Greater Than (>)")),
    ("le", _("Less Than or Equal To (<=)")),
    ("ge", _("Greater Than or Equal To (>=)")),
    ("icontains", _("Contains")),
]


class MultipleApprovalCondition(HorillaModel):
    """
    Multiple approve conditions
    """

    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    condition_field = models.CharField(
        max_length=255,
        choices=FIELD_CHOICE,
        verbose_name=_("Condition Field"),
    )
    condition_operator = models.CharField(
        max_length=255,
        choices=CONDITION_CHOICE,
        null=True,
        blank=True,
        verbose_name=_("Condition Operator"),
    )
    condition_value = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Condition Value"),
    )
    condition_start_value = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Starting Value"),
    )
    condition_end_value = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Ending Value"),
    )
    company_id = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
    )
    objects = HorillaCompanyManager()

    def __str__(self) -> str:
        return f"{self.condition_field} {self.condition_operator}"

    def get_condition_field(self):
        """
        Display condition field
        """
        return dict(FIELD_CHOICE).get(self.condition_field)

    def get_condition_operator(self):
        """
        Display condition operator
        """
        return dict(CONDITION_CHOICE).get(self.condition_operator)

    def get_condition_value(self):
        """
        Condition value column
        """
        if self.condition_operator == "range":
            start_value = self.condition_start_value
            end_value = self.condition_end_value
            return start_value + " - " + end_value
        else:
            return self.condition_value

    def approval_managers_col(self):
        """
        For approval managers column
        """

        return render_template(
            path="cbv/multiple_approval_condition/approval_managers.html",
            context={"instance": self},
        )

    def detail_actions(self):
        """
        For detail action column
        """

        return render_template(
            path="cbv/multiple_approval_condition/detail_action.html",
            context={"instance": self},
        )

    def actions_col(self):
        """
        For actions column
        """

        return render_template(
            path="cbv/multiple_approval_condition/actions.html",
            context={"instance": self},
        )

    def get_avatar(self):
        """
        Method will retun the api to the avatar or path to the profile image
        """
        url = f"https://ui-avatars.com/api/?name={self.department}&background=random"
        return url

    def detail_view(self):
        """
        detail view
        """
        url = reverse("detail-view-multiple-approval-condition", kwargs={"pk": self.pk})
        return url

    def clean(self, *args, **kwargs):
        if self.condition_value:
            instance = MultipleApprovalCondition.objects.filter(
                department=self.department,
                condition_field=self.condition_field,
                condition_operator=self.condition_operator,
                condition_value=self.condition_value,
                company_id=self.company_id,
            ).exclude(id=self.pk)
            if instance:
                raise ValidationError(
                    _("A condition with the provided fields already exists")
                )
        if self.condition_field == "requested_days":
            if self.condition_operator != "range":
                if not self.condition_value:
                    raise ValidationError(
                        {
                            "condition_operator": _(
                                "Please enter a numeric value for condition value"
                            )
                        }
                    )
                try:
                    float_value = float(self.condition_value)
                except ValueError as e:
                    raise ValidationError(
                        {
                            "condition_operator": _(
                                "Please enter a valid numeric value for the condition value when the condition field is Leave Requested Days."
                            )
                        }
                    )
            else:
                if not self.condition_start_value or not self.condition_end_value:
                    raise ValidationError(
                        {
                            "condition_operator": _(
                                "Please specify condition value range"
                            )
                        }
                    )
                try:
                    start_value = float(self.condition_start_value)
                except ValueError as e:
                    raise ValidationError(
                        {
                            "condition_operator": _(
                                "Please enter a valid numeric value for the starting value when the condition field is Leave Requested Days."
                            )
                        }
                    )
                try:
                    end_value = float(self.condition_end_value)
                except ValueError as e:
                    raise ValidationError(
                        {
                            "condition_operator": _(
                                "Please enter a valid numeric value for the ending value when the condition field is Leave Requested Days."
                            )
                        }
                    )

                if start_value == end_value:
                    raise ValidationError(
                        {
                            "condition_operator": _(
                                "End value must be different from the start value in a range."
                            )
                        }
                    )
                if end_value <= start_value:
                    raise ValidationError(
                        {
                            "condition_operator": _(
                                "End value must be greater than the start value in a range."
                            )
                        }
                    )
        super().clean(*args, **kwargs)

    def save(self, *args, **kwargs):
        if self.condition_operator != "range":
            self.condition_start_value = None
            self.condition_end_value = None
        else:
            self.condition_value = None
        super().save(*args, **kwargs)

    def approval_managers(self, *args, **kwargs):
        """
        approved managers
        """
        managers = []
        from employee.models import Employee

        queryset = MultipleApprovalManagers.objects.filter(
            condition_id=self.pk
        ).order_by("sequence")
        for query in queryset:
            emp_id = query.employee_id
            employee = (
                query.reporting_manager
                if not emp_id
                else Employee.objects.get(id=emp_id)
            )
            managers.append(employee)

        return managers


class MultipleApprovalManagers(models.Model):
    """
    Multiple approve
    """

    condition_id = models.ForeignKey(
        MultipleApprovalCondition, on_delete=models.CASCADE
    )
    sequence = models.IntegerField(null=False, blank=False)
    employee_id = models.IntegerField(null=True, blank=True)
    reporting_manager = models.CharField(max_length=100, null=True, blank=True)
    objects = HorillaCompanyManager(related_company_field="condition_id__company_id")

    class Meta:
        verbose_name = _("Multiple Approval Managers")
        verbose_name_plural = _("Multiple Approval Managers")

    def get_manager(self):
        manager = self.employee_id
        if manager:
            manager = self.reporting_manager.replace("_", " ").title()
        return manager


class DynamicPagination(models.Model):
    """
    Per-user, per-company default for the number of records shown per
    page across list views.
    """

    user_id = models.ForeignKey(
        HorillaUser,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="dynamic_pagination",
        verbose_name=_("User"),
    )
    company_id = models.ForeignKey("base.Company", on_delete=models.CASCADE, null=True)
    pagination = models.IntegerField(default=50, validators=[MinValueValidator(1)])
    objects = HorillaCompanyManager()

    def save(self, *args, **kwargs):
        request = getattr(_thread_locals, "request", None)
        user = request.user
        self.user_id = user
        super().save(*args, **kwargs)

    def company_col(self):
        return self.company_id.company if self.company_id else "All Company"

    def __str__(self):
        return f"{self.user_id}|{self.company_id}|{self.pagination}"


class Attachment(models.Model):
    """
    Attachment model for multiple attachments in announcements.
    """

    file = models.FileField(upload_to=upload_path)

    def __str__(self):
        return self.file.name


class AnnouncementExpire(models.Model):
    """
    Per-company default for the number of days an announcement stays
    active when no explicit expire date is set.
    """

    days = models.IntegerField(null=True, blank=True, default=30)
    company_id = models.ForeignKey("base.Company", on_delete=models.CASCADE, null=True)
    objects = HorillaCompanyManager()

    def company_col(self):
        return self.company_id.company if self.company_id else "All Company"

    def __str__(self):
        return (
            f"Default expire days for {self.company_id or 'All Company'}: {self.days}"
        )


class Announcement(HorillaModel):
    """
    Announcement Model for storing all announcements.
    """

    from employee.models import Employee

    model_employee = Employee

    title = models.CharField(max_length=100)
    description = models.TextField(null=True)
    attachments = models.ManyToManyField(
        Attachment, related_name="announcement_attachments", blank=True
    )
    expire_date = models.DateField(null=True, blank=True)
    employees = models.ManyToManyField(
        Employee,
        related_name="announcement_employees",
        blank=True,
        help_text=_(
            "If no employee, department or job position is selected, the announcement will be visible to all employees in the selected company."
        ),
    )
    department = models.ManyToManyField(Department, blank=True)
    job_position = models.ManyToManyField(
        JobPosition, blank=True, verbose_name=_("Job Position")
    )
    company_id = models.ManyToManyField(
        Company, blank=True, related_name="announcement", verbose_name=_("Company")
    )
    disable_comments = models.BooleanField(
        default=False, verbose_name=_("Disable Comments")
    )
    public_comments = models.BooleanField(
        default=True,
        verbose_name=_("Show Comments to All"),
        help_text=_("If enabled, all employees can view each other's comments."),
    )

    filtered_employees = models.ManyToManyField(
        Employee, related_name="announcement_filtered_employees", editable=False
    )
    objects = HorillaCompanyManager(related_company_field="company_id")

    class Meta:
        verbose_name = _("Announcement")
        verbose_name_plural = _("Announcements")

    def get_views(self):
        """
        This method is used to get the view count of the announcement
        """
        return self.announcementview_set.filter(viewed=True)

    def viewed_by(self):
        """
        Announcement view
        """

        viewed_by = AnnouncementView.objects.filter(
            announcement_id__id=self.id, viewed=True
        )
        viewed_emp = []
        for i in viewed_by:
            viewed_emp.append(i.user)
        return viewed_emp

    def save(self, *args, **kwargs):
        """
        if comments are disabled, force public comments to be false
        """
        if self.disable_comments:
            self.public_comments = False
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    def announcement_custom_col(self):
        """
        custom col for announcement list col
        """

        current_date = datetime.now().strftime("%Y-%m-%d")

        return render_template(
            path="cbv/dashboard/announcement_title.html",
            context={"instance": self, "current_date": current_date},
        )


class AnnouncementComment(HorillaModel):
    """
    AnnouncementComment Model
    """

    from employee.models import Employee

    announcement_id = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    employee_id = models.ForeignKey(Employee, on_delete=models.CASCADE)
    comment = models.TextField(null=True, verbose_name=_("Comment"), max_length=255)
    objects = models.Manager()


class AnnouncementView(models.Model):
    """
    Announcement View Model
    """

    user = models.ForeignKey(HorillaUser, on_delete=models.CASCADE)
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    viewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    objects = models.Manager()

    def announcement_viewed_by_col(self):
        """
        custom col for announcement list col
        """

        return render_template(
            path="cbv/dashboard/announcement_viewed_by.html",
            context={
                "instance": self,
            },
        )


class EmailLog(models.Model):
    """
    EmailLog Keeping model
    """

    statuses = [("sent", "Sent"), ("failed", "Failed")]
    subject = models.CharField(max_length=255)
    body = models.TextField(max_length=255)
    from_email = models.EmailField()
    to = models.EmailField()
    status = models.CharField(max_length=6, choices=statuses)
    created_at = models.DateTimeField(auto_now_add=True)
    company_id = models.ForeignKey(
        Company, on_delete=models.CASCADE, null=True, editable=False
    )
    # Was a plain Manager(), so the company_id below was never filtered on and
    # the mail-log views -- which match only on recipient address -- could show
    # one tenant's mail to another. Bodies are redacted on write; see
    # base/email_redaction.py.
    objects = HorillaCompanyManager()

    def __str__(self) -> str:
        return f"{self.subject} {self.to}"

    def status_display(self):
        status = dict(self.statuses).get(self.status)
        if self.status == "sent":
            color_class = "oh-dot--success"
            link_class = "link-success"

        elif self.status == "failed":
            color_class = "oh-dot--danger"
            link_class = "link-danger"
        return format_html(
            '<span class="oh-dot oh-dot--small me-1 oh-dot--color {color_class}"></span>'
            '<span class="{link_class}">{status}</span>',
            color_class=color_class,
            status=status,
            link_class=link_class,
        )

    def mail_log_detail_view(self):
        """
        for detail view of page
        """
        url = reverse("individual-mail-log-detail", kwargs={"pk": self.pk})
        return url


class DriverViewed(models.Model):
    """
    Model to store driver viewed status
    """

    choices = [
        ("dashboard", "dashboard"),
        ("pipeline", "pipeline"),
        ("settings", "settings"),
    ]
    user = models.ForeignKey(HorillaUser, on_delete=models.CASCADE)
    viewed = models.CharField(max_length=10, choices=choices)

    def user_viewed(self):
        """
        This method is used to access all the viewd driver
        """
        return self.user.driverviewed_set.values_list("viewed", flat=True)


class DashboardEmployeeCharts(HorillaModel):
    """
    dashboard employee chart
    """

    from employee.models import Employee

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    charts = models.JSONField(
        verbose_name=_("Excluded Charts"), default=list, blank=True, null=True
    )

    class Meta:
        verbose_name = _("Dashboard Employee Charts")
        verbose_name_plural = _("Dashboard Employee Charts")

    def __str__(self):
        return f"{self.employee} - charts"


class BiometricAttendance(models.Model):
    """
    Biometric attendance
    """

    is_installed = models.BooleanField(default=False)
    company_id = models.ForeignKey(
        Company,
        null=True,
        editable=False,
        on_delete=models.PROTECT,
        related_name="biometric_enabled_company",
        verbose_name=_("Company"),
    )
    objects = HorillaCompanyManager()

    def __str__(self):
        return f"{self.is_installed}"

    def save(self, *args, **kwargs):
        if (
            not self.pk
            and BiometricAttendance.objects.filter(company_id=self.company_id).exists()
        ):
            raise ValidationError(
                _("Only one BiometricAttendance instance is allowed per company.")
            )
        return super().save(*args, **kwargs)


def default_additional_data():
    return {"allowed_ips": []}


class AttendanceAllowedIP(models.Model):
    """
    Represents client IP addresses that are allowed to mark attendance.
    Each company has its own record so IP restrictions are company-specific.
    """

    company_id = models.OneToOneField(
        Company,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attendance_allowed_ip",
        verbose_name=_("Company"),
    )
    is_enabled = models.BooleanField(default=False)
    additional_data = models.JSONField(
        null=True, blank=True, default=default_additional_data
    )
    objects = HorillaCompanyManager(related_company_field="company_id")

    def clean(self):
        """
        Validate that all entries in `allowed_ips` are either valid IP addresses or network prefixes.
        """
        allowed_ips = (self.additional_data or {}).get("allowed_ips", [])
        for ip in allowed_ips:
            try:
                ipaddress.ip_network(ip, strict=False)
            except ValueError:
                raise ValidationError(f"Invalid IP address or network prefix: {ip}")

    def __str__(self):
        company = self.company_id.company if self.company_id else "Global"
        return f"AttendanceAllowedIP ({company}) - {'enabled' if self.is_enabled else 'disabled'}"


class TrackLateComeEarlyOut(HorillaModel):
    is_enable = models.BooleanField(
        default=True,
        verbose_name=_("Enable"),
        help_text=_(
            "By enabling this, you track the late comes and early outs of employees in their attendance."
        ),
    )
    company_id = models.ForeignKey(
        Company,
        null=True,
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
    )
    objects = HorillaCompanyManager()

    class Meta:
        verbose_name = _("Track Late Arrival & Early Departure")
        verbose_name_plural = _("Track Late Arrival & Early Departure")

    def __str__(self):
        tracking = _("enabled") if self.is_enable else _("disabled")
        return f"Tracking late come early out {tracking}"

    def save(self, *args, **kwargs):
        if (
            not self.pk
            and TrackLateComeEarlyOut.objects.filter(
                company_id=self.company_id
            ).exists()
        ):
            raise ValidationError(
                _("Only one TrackLateComeEarlyOut instance is allowed per company.")
            )
        return super().save(*args, **kwargs)


class Holidays(HorillaModel):
    ASSIGNING_TYPE = [
        ("department", _("Department")),
        ("job_position", _("Job Position")),
        ("employee", _("Employee")),
    ]
    name = models.CharField(max_length=30, null=False, verbose_name=_("Name"))
    start_date = models.DateField(verbose_name=_("Start Date"))
    end_date = models.DateField(null=True, blank=True, verbose_name=_("End Date"))
    recurring = models.BooleanField(default=False, verbose_name=_("Recurring"))
    is_specific = models.BooleanField(default=False, verbose_name=_("Is Specific"))
    assigning_type = models.CharField(
        choices=ASSIGNING_TYPE,
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Assigning Type"),
    )
    department = models.ManyToManyField(
        Department,
        blank=True,
        related_name="holiday_departments",
        verbose_name=_("Department"),
    )
    job_position = models.ManyToManyField(
        JobPosition,
        blank=True,
        related_name="holiday_job_positions",
        verbose_name=_("Job Position"),
    )
    employees = models.ManyToManyField("employee.Employee", blank=True)
    company_id = models.ForeignKey(
        Company,
        null=True,
        on_delete=models.PROTECT,
        verbose_name=_("Company"),
    )
    objects = HorillaCompanyManager(related_company_field="company_id")

    class Meta:
        verbose_name = _("Holiday")
        verbose_name_plural = _("Holidays")

    def __str__(self):
        return self.name

    def detail_view(self):
        """
        detail view
        """

        url = reverse("holiday-detail-view", kwargs={"pk": self.pk})
        return url

    def detail_view_actions(self):
        """
        detail view actions
        """
        return render_template(
            path="cbv/holidays/detail_view_actions.html",
            context={"instance": self},
        )

    def get_recurring_status(self):
        """
        recurring data
        """
        return _("Yes") if self.recurring else _("No")

    def get_is_specific_status(self):
        return _("Yes") if self.is_specific else _("No")

    def get_assigning_type_label(self):
        if not self.is_specific or not self.assigning_type:
            return "-"
        return dict(self.ASSIGNING_TYPE).get(self.assigning_type, "-")

    def get_department_names(self):
        depts = self.department.all()
        return ", ".join(d.department for d in depts) if depts.exists() else "-"

    def get_job_position_names(self):
        positions = self.job_position.all()
        return (
            ", ".join(jp.job_position for jp in positions)
            if positions.exists()
            else "-"
        )

    def get_employee_names(self):
        emps = self.employees.all()
        return (
            ", ".join(f"{e.employee_first_name} {e.employee_last_name}" for e in emps)
            if emps.exists()
            else "-"
        )

    def holidays_actions(self):
        """
        method for rendering actions(edit,delete)
        """

        return render_template(
            path="cbv/holidays/holidays_actions.html",
            context={"instance": self},
        )

    def get_avatar(self):
        """
        Method will retun the api to the avatar or path to the profile image
        """
        url = f"https://ui-avatars.com/api/?name={self.name}&background=random"
        return url

    def today_holidays(today=None, employee=None) -> models.QuerySet:
        """
        Retrieve holidays that overlap with the given date (default is today).

        Args:
            today (date, optional): The date to check for holidays. Defaults to the current date.
            employee: When provided, limits results to global holidays and holidays
                      specific to this employee. When None, returns all holidays.

        Returns:
            QuerySet: A queryset of `Holidays` instances where the given date falls between
                    `start_date` and `end_date` (inclusive).
        """
        from django.db.models import Q

        today = today or date.today()
        qs = Holidays.objects.filter(start_date__lte=today, end_date__gte=today)
        if employee is not None:
            qs = qs.filter(Q(is_specific=False) | Q(employees=employee))
        return qs


class CompanyLeaves(HorillaModel):
    based_on_week = models.CharField(
        max_length=100,
        choices=WEEKS,
        blank=True,
        null=True,
        verbose_name=_("Based On Week"),
    )
    based_on_week_day = models.CharField(
        max_length=100, choices=WEEK_DAYS, verbose_name=_("Based On Week Day")
    )
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))
    objects = HorillaCompanyManager()

    class Meta:
        unique_together = ("based_on_week", "based_on_week_day")
        verbose_name = _("Weekly Off Day")
        verbose_name_plural = _("Weekly Off Days")

    def __str__(self):
        return f"{dict(WEEK_DAYS).get(self.based_on_week_day)} | {dict(WEEKS).get(self.based_on_week)}"

    def custom_based_on_week(self):
        """
        custom based on col
        """

        return render_template(
            path="cbv/company_leaves/on_week.html",
            context={"instance": self, "weeks": WEEKS},
        )

    def get_detail_title(self):
        """
        for return title
        """

        title = "Weekly Off Days"
        return title

    def detail_view_actions(self):
        """
        detail view actions
        """
        return render_template(
            path="cbv/company_leaves/detail_view_actions.html",
            context={"instance": self},
        )

    def based_on_week_day_col(self):
        """
        custom based on week day col
        """

        return render_template(
            path="cbv/company_leaves/on_week_day.html",
            context={"instance": self, "week_days": WEEK_DAYS},
        )

    def company_leave_actions(self):
        """
        custom actions col
        """

        return render_template(
            path="cbv/company_leaves/company_leave_actions.html",
            context={"instance": self, "weeks": WEEKS},
        )

    def get_company_display(self):
        """
        Comma-separated names of the companies this weekly off day applies to.
        """
        return ", ".join(str(company) for company in self.company_id.all())

    def detail_view(self):
        """
        detail view
        """

        url = reverse("company-leave-detail-view", kwargs={"pk": self.pk})
        return url

    def get_avatar(self):
        """
        Method will retun the api to the avatar or path to the profile image
        """
        if self.based_on_week is not None:
            url = f"https://ui-avatars.com/api/?name={dict(WEEKS).get(self.based_on_week)}&background=random"
        else:
            data = "All"
            url = f"https://ui-avatars.com/api/?name={data}&background=random"
        return url


class PenaltyAccounts(HorillaModel):
    """
    LateComeEarlyOutPenaltyAccount
    """

    employee_id = models.ForeignKey(
        "employee.Employee",
        on_delete=models.PROTECT,
        related_name="penalty_accounts",
        editable=False,
        verbose_name=_("Employee"),
        null=True,
    )
    if apps.is_installed("attendance"):
        late_early_id = models.ForeignKey(
            "attendance.AttendanceLateComeEarlyOut",
            on_delete=models.CASCADE,
            null=True,
            editable=False,
        )
    if apps.is_installed("leave"):
        leave_request_id = models.ForeignKey(
            "leave.LeaveRequest", null=True, on_delete=models.CASCADE, editable=False
        )
        leave_type_id = models.ForeignKey(
            "leave.LeaveType",
            on_delete=models.DO_NOTHING,
            blank=True,
            null=True,
            verbose_name=_("Leave type"),
        )
        minus_leaves = models.FloatField(
            default=0.0, null=True, verbose_name=_("Minus Leaves")
        )
        deduct_from_carry_forward = models.BooleanField(
            default=False, verbose_name=_("Deduct from Carry Forward")
        )

        def get_deduct_from_carry_forward(self):
            if self.deduct_from_carry_forward:
                return _("Yes")
            return _("No")

    penalty_amount = models.FloatField(
        default=0.0, null=True, verbose_name=_("Penalty Amount")
    )

    def get_delete_url(self):
        """
        To get delete url
        """
        url = reverse("delete-penalties", kwargs={"penalty_id": self.pk})
        return url

    def get_delete_instance(self):
        """
        To get instance for delete
        """
        return self.pk

    def penalty_type_col(self):
        if apps.is_installed("attendance"):
            if self.late_early_id:
                return "Late come or Early out Penalty"
            return "Leave Penalty"

    def clean(self) -> None:
        super().clean()
        if apps.is_installed("leave") and not self.leave_type_id and self.minus_leaves:
            raise ValidationError(
                {"leave_type_id": _("Specify the leave type to deduct the leave.")}
            )
        if apps.is_installed("leave") and self.leave_type_id and not self.minus_leaves:
            raise ValidationError(
                {
                    "minus_leaves": _(
                        "If a leave type is chosen for a penalty, minus leaves are required."
                    )
                }
            )
        if (
            apps.is_installed("leave")
            and not self.minus_leaves
            and not self.penalty_amount
        ):
            raise ValidationError(
                {
                    "leave_type_id": _(
                        "Either minus leaves or a penalty amount is required"
                    )
                }
            )

        if (
            apps.is_installed("leave")
            and (self.minus_leaves or self.deduct_from_carry_forward)
            and not self.leave_type_id
        ):
            raise ValidationError({"leave_type_id": _("Leave type is required")})
        return

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Penalty Account")
        verbose_name_plural = _("Penalty Accounts")


class NotificationSound(models.Model):
    from employee.models import Employee

    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name="notification_sound"
    )
    sound_enabled = models.BooleanField(default=False)


class IntegrationApps(HorillaModel, NoPermissionModel):
    app_label = models.CharField(max_length=255)
    company = models.ForeignKey(
        "base.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Company"),
    )
    is_enabled = models.BooleanField(default=False)

    class Meta:
        unique_together = ("app_label", "company")


class SetupChecklistDismissal(models.Model):
    """
    Per-user, per-company dismissal of the onboarding setup checklist banner.
    A user who manages multiple companies can dismiss independently for each.
    """

    user = models.ForeignKey(
        HorillaUser,
        on_delete=models.CASCADE,
        related_name="setup_checklist_dismissals",
    )
    company = models.ForeignKey(
        "base.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="setup_checklist_dismissals",
    )
    dismissed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "base"
        unique_together = [("user", "company")]
        verbose_name = "Setup Checklist Dismissal"
        verbose_name_plural = "Setup Checklist Dismissals"

    def __str__(self):
        return f"{self.user} — {self.company or 'global'}"


class DefaultExportPermission(HorillaModel):
    """
    Per-company toggle for the "Default Export Access" setting. When
    enabled for a company, every user of that company may export data
    from any module; when disabled, export access falls back to the
    per-module export_<model> permission (superusers are always allowed).
    """

    is_enabled = models.BooleanField(default=True, blank=True, null=True)
    company_id = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
    )
    objects = models.Manager()

    class Meta:
        # Every reader does .filter(company_id=...).first(), so a second row
        # for the same company silently decides the setting by insertion
        # order. One row per company, plus one for the NULL "all companies"
        # scope.
        #
        # Two constraints rather than one with nulls_distinct=False: that
        # flag needs PostgreSQL 15+, and Django SKIPS the constraint
        # silently on older servers -- so on Postgres 14 it would enforce
        # nothing while looking correct. A partial unique index works
        # everywhere.
        constraints = [
            models.UniqueConstraint(
                fields=["company_id"],
                condition=Q(company_id__isnull=False),
                name="unique_default_export_permission_per_company",
            ),
            # Postgres treats every NULL as distinct, so a plain unique index
            # on company_id does NOT stop a second "all companies" row
            # (verified: two NULL rows insert happily). Indexing the constant
            # expression company_id IS NULL gives that partial index a single
            # possible key, which is what makes it a one-row guard.
            models.UniqueConstraint(
                Q(company_id__isnull=True),
                condition=Q(company_id__isnull=True),
                name="unique_default_export_permission_all_companies",
            ),
        ]

    def __str__(self):
        return f"Default Export Access for {self.company_id} is {'enabled' if self.is_enabled else 'disabled'}"


class CompanyLanguageSetting(HorillaModel):
    """
    Per-company list of enabled languages for the navbar language switcher.
    When a company has one or more languages configured here, only those
    languages are shown to that company's users; if none are configured,
    every language defined in settings.LANGUAGES remains available.
    """

    company_id = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
    )
    enabled_languages = models.JSONField(default=list, blank=True)
    objects = models.Manager()


# User.add_to_class("is_new_employee", models.BooleanField(default=False))
