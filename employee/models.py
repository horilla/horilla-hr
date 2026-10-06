"""
models.py

This module is used to register models for employee app

"""

import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.query import QuerySet
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from PIL import Image

from accessibility.accessibility import ACCESSBILITY_FEATURE
from base.horilla_company_manager import HorillaCompanyManager
from base.models import (
    Company,
    Department,
    EmployeeShift,
    EmployeeType,
    JobPosition,
    JobRole,
    WorkType,
    validate_time_format,
)
from employee.methods.duration_methods import format_time, strtime_seconds
from horilla import horilla_middlewares
from horilla.horilla_middlewares import _thread_locals
from horilla.methods import get_horilla_model_class
from horilla.models import HorillaModel, has_xss, upload_path
from horilla_audit.methods import get_diff
from horilla_audit.models import HorillaAuditInfo, HorillaAuditLog
from horilla_auth.methods import (
    generate_random_password,
    generate_unique_fallback_username,
)
from horilla_auth.models import HorillaUser
from horilla_views.cbv_methods import render_template

# create your model


def reporting_manager_validator(value):
    """
    Method to implement reporting manager_validator
    """
    return value


phone_validator = RegexValidator(
    regex=r"^\+?[\d\s\-\(\)]{7,20}$",
    message=_("Enter a valid phone number (7-20 characters, optional +)."),
)


class Employee(models.Model):
    """
    Employee model
    """

    choice_gender = [
        ("male", _("Male")),
        ("female", _("Female")),
        ("other", _("Other")),
    ]
    choice_marital = (
        ("single", _("Single")),
        ("married", _("Married")),
        ("divorced", _("Divorced")),
    )
    badge_id = models.CharField(max_length=50, null=True, blank=True)
    employee_user_id = models.OneToOneField(
        HorillaUser,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="employee_get",
        verbose_name=_("User"),
    )
    employee_first_name = models.CharField(
        max_length=200, null=False, verbose_name=_("First Name")
    )
    employee_last_name = models.CharField(
        max_length=200, null=True, blank=True, verbose_name=_("Last Name")
    )
    employee_profile = models.ImageField(
        upload_to=upload_path, null=True, blank=True, verbose_name=_("Profile Image")
    )
    email = models.EmailField(max_length=254, unique=True)
    phone = models.CharField(max_length=25, validators=[phone_validator])
    address = models.TextField(max_length=200, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=30, null=True, blank=True)
    zip = models.CharField(max_length=20, null=True, blank=True, verbose_name=_("Zip"))
    dob = models.DateField(null=True, blank=True, verbose_name=_("Date of Birth"))
    gender = models.CharField(
        max_length=10, null=True, choices=choice_gender, default="male"
    )
    qualification = models.CharField(max_length=50, blank=True, null=True)
    experience = models.IntegerField(null=True, blank=True)
    marital_status = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=choice_marital,
        default="single",
        verbose_name=_("Marital Status"),
    )
    children = models.IntegerField(blank=True, null=True)
    emergency_contact = models.CharField(
        max_length=15, null=True, blank=True, verbose_name=_("Emergency Contact")
    )
    emergency_contact_name = models.CharField(
        max_length=20, null=True, blank=True, verbose_name=_("Emergency Contact Name")
    )
    emergency_contact_relation = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name=_("Emergency Contact Relation"),
    )
    is_active = models.BooleanField(default=True)
    additional_info = models.JSONField(null=True, blank=True)
    is_from_onboarding = models.BooleanField(
        default=False, null=True, blank=True, editable=False
    )
    is_directly_converted = models.BooleanField(
        default=False, null=True, blank=True, editable=False
    )
    objects = HorillaCompanyManager(
        related_company_field="employee_work_info__company_id"
    )

    def get_contact(self):
        """
        to get contact no of candidates
        """
        return self.phone

    def clean_fields(self, exclude=None):
        errors = {}

        # Get the list of fields to exclude from validation
        total_exclude = set(exclude or []).union(getattr(self, "xss_exempt_fields", []))

        for field in self._meta.get_fields():
            if (
                isinstance(field, (models.CharField, models.TextField))
                and field.name not in total_exclude
            ):
                value = getattr(self, field.name, None)
                if value and has_xss(value):
                    errors[field.name] = ValidationError(
                        _("Potential XSS content detected.")
                    )

        if errors:
            raise ValidationError(errors)

    def get_image(self):
        """
        This method is used to return the profile image path of the employee
        """
        url = False
        if self.employee_profile:
            url = self.employee_profile.url
        return url

    def get_employee_dob(self) -> any:
        if self.dob:
            return self.dob.strftime("%d %b")
        return None

    def get_full_name(self):
        """
        Method will return employee full name
        """
        return (
            f"{self.employee_first_name } {self.employee_last_name}"
            if self.employee_last_name
            else self.employee_first_name
        )

    def get_company(self):
        """
        This method is used to return the company of the employee
        """
        return getattr(getattr(self, "employee_work_info", None), "company_id", None)

    def get_date_format(self):
        company = (
            self.get_company()
            if self.get_company()
            else Company.objects.filter(hq=True).first()
        )

        if company:
            date_format = company.date_format

            return date_format if date_format else "MMM. D, YYYY"

        return "MMM. D, YYYY"

    def get_job_position(self):
        """
        This method is used to return the job position of the employee
        """
        return getattr(
            getattr(self, "employee_work_info", None), "job_position_id", None
        )

    def diff_cell(self):
        request = getattr(_thread_locals, "request", None)
        if (
            request
            and hasattr(request, "user")
            and hasattr(request.user, "employee_get")
        ):
            if (
                hasattr(self, "employee_work_info")
                and self.employee_work_info.reporting_manager_id
                == request.user.employee_get
            ):
                return 'style="color: inherit; text-decoration: none; background-color: rgba(255, 166, 0, 0.158);"'
            else:
                return ""
        else:
            return ""

    def get_department(self):
        """
        This method is used to return the department of the employee
        """
        return getattr(getattr(self, "employee_work_info", None), "department_id", None)

    def get_shift(self):
        """
        This method is used to return the shift of the employee
        """
        return getattr(getattr(self, "employee_work_info", None), "shift_id", None)

    def get_shift_schedule(self):
        """
        This method is used to check if the employee has a shift assigned
        """
        from base.methods import is_holiday

        today = datetime.today().date()
        if is_holiday(today, self):
            return None
        shift = self.get_shift()
        day = datetime.today().strftime("%A").lower()
        if not shift:
            return None
        schedule = shift.employeeshiftschedule_set.filter(day__day=day).first()
        return schedule if schedule else None

    def get_mail(self):
        """
        This method is used to return the employee's email, checking work email first
        then falling back to personal email.
        """
        work_info = getattr(self, "employee_work_info", None)
        work_email = getattr(work_info, "email", None)
        return work_email if work_email is not None else self.email

    def get_email(self):
        return self.get_mail()

    def get_work_type(self):
        """
        This method is used to return the work type of the employee
        """
        return getattr(getattr(self, "employee_work_info", None), "work_type_id", None)

    def get_employee_type(self):
        """
        This method is used to return the employee type of the employee
        """
        return getattr(
            getattr(self, "employee_work_info", None), "employee_type_id", None
        )

    def get_reporting_manager(self):
        """
        This method is used to return the employee type of the employee
        """
        return getattr(
            getattr(self, "employee_work_info", None), "reporting_manager_id", None
        )

    def get_avatar(self):
        if self.employee_profile and default_storage.exists(self.employee_profile.name):
            return self.employee_profile.url
        return static("images/ui/default_avatar.jpg")

    def get_active_status(self):
        """
        This method is used to return the active/inactive status of the employee
        """
        return _("Active") if self.is_active else _("Inactive")

    def get_leave_status(self):
        """
        This method is used to get the leave status of the employee
        """
        today = date.today()
        leaves_requests = (
            self.leaverequest_set.filter(start_date__lte=today, end_date__gte=today)
            if apps.is_installed("leave")
            else QuerySet().none()
        )
        status = _("Expected working")
        if leaves_requests.exists():
            if leaves_requests.filter(status="approved").exists():
                status = _("On Leave")
            elif leaves_requests.filter(status="requested"):
                status = _("Waiting Approval")
            else:
                status = _("Canceled / Rejected")
        elif (
            apps.is_installed("attendance")
            and self.employee_attendances.filter(
                attendance_date=today,
            ).exists()
        ):
            status = _("On a break")
        # return status
        return f'<span class="oh-recruitment_tag" style="font-size: 0.5rem; color: red;">{status}</span>'

    def send_mail_button(self):
        """
        View to return the HTML for the send mail button.
        """

        return render_template(
            path="cbv/dashboard/offline_action.html",
            context={"instance": self},
        )

    def get_forecasted_at_work(self):
        """
        This method is used to the employees current day shift status
        """
        if apps.is_installed("attendance"):
            today = datetime.today()
            yesterday = today - timedelta(days=1)
            today_attendance = None
            yesterday_attendance = None
            attendances = list(
                self.employee_attendances.filter(
                    attendance_date__in=[yesterday, today]
                ).order_by("attendance_date")
            )

            if len(attendances) == 1:
                yesterday_attendance, today_attendance = attendances[0], None
            elif len(attendances) == 2:
                yesterday_attendance, today_attendance = attendances
            else:
                yesterday_attendance, today_attendance = None, None

            attendance = today_attendance
            if not today_attendance:
                attendance = yesterday_attendance
            minimum_hour_seconds = strtime_seconds(
                getattr(attendance, "minimum_hour", "0")
            )
            at_work = 0
            forecasted_pending_hours = 0
            if attendance:
                at_work = attendance.get_at_work_from_activities()
            forecasted_pending_hours = max(0, (minimum_hour_seconds - at_work))

            return {
                "forecasted_at_work": format_time(at_work),
                "forecasted_pending_hours": format_time(forecasted_pending_hours),
                "forecasted_at_work_seconds": at_work,
                "forecasted_pending_hours_seconds": forecasted_pending_hours,
                "has_attendance": attendance is not None,
            }
        else:
            return {}

    def get_custom_forecasted_info_col(self):
        forecasted_info = self.get_forecasted_at_work()
        forecasted_at_work = forecasted_info.get("forecasted_at_work")
        forecasted_pending_hours = forecasted_info.get("forecasted_pending_hours")

        return f"""
                <span class="oh-recuritment_tag" style="font-size: .5rem;">At work {forecasted_at_work}</span>
                <span class="oh-recuritment_tag" style="font-size: .5rem;">Pending {forecasted_pending_hours}</span>
            """

    def get_today_attendance(self):
        """
        This method will returns employees todays attendance
        """
        return self.employee_attendances.filter(
            attendance_date=datetime.today()
        ).first()

    def sync_login_access(self):
        """Mirror ``is_active`` onto the linked user account.

        Archiving an employee is the expected way to offboard someone, but the
        login gate is ``HorillaUser.is_active`` -- ``CompanyScopedBackend``
        inherits ``ModelBackend.user_can_authenticate``, which reads that flag
        and knows nothing about ``Employee.is_active``. Setting the employee
        flag alone therefore hid the person from every list while leaving their
        credentials working.

        Call this immediately after a save that changed ``is_active``. It is
        deliberately NOT wired into ``save()``: ``ToggleDashboardAccess``
        revokes a login while leaving the employee active, and syncing on every
        save would silently hand that access back.

        Derives the user's value from ``self.is_active`` rather than negating
        anything, so it cannot reintroduce the inversion this replaces.
        """
        user = self.employee_user_id
        if user is not None and user.is_active != self.is_active:
            user.is_active = self.is_active
            user.save(update_fields=["is_active"])

    def get_archive_condition(self):
        """
        Determine whether an employee is eligible for archiving based on their
        involvement in various processes.

        Returns:
            dict or bool: A dictionary containing a list of related models
                        if the employee is not eligible for archiving,
                        otherwise, False.

        This method checks the employee's association with different models,
        such as reporting manager, recruitment stage, onboarding stage, onboarding task,
        and recruitment manager. If the employee is not associated with any of these,
        they are considered eligible for archiving. If they are associated,
        a dictionary is returned with a list of related models of that employee.
        """
        if apps.is_installed("onboarding"):
            OnboardingStage = get_horilla_model_class("onboarding", "onboardingstage")
            OnboardingTask = get_horilla_model_class("onboarding", "onboardingtask")
            onboarding_stage_query = OnboardingStage.objects.filter(employee_id=self.pk)
            onboarding_task_query = OnboardingTask.objects.filter(employee_id=self.pk)
        else:
            onboarding_stage_query = None
            onboarding_task_query = None
        if apps.is_installed("recruitment"):
            Recruitment = get_horilla_model_class("recruitment", "recruitment")
            Stage = get_horilla_model_class("recruitment", "stage")
            recruitment_stage_query = Stage.objects.filter(stage_managers=self.pk)
            recruitment_manager_query = Recruitment.objects.filter(
                recruitment_managers=self.pk
            )
        else:
            recruitment_stage_query = None
            recruitment_manager_query = None
        reporting_manager_query = EmployeeWorkInformation.objects.filter(
            reporting_manager_id=self.pk
        )
        if not (
            reporting_manager_query.exists()
            or (recruitment_stage_query and recruitment_stage_query.exists())
            or (onboarding_stage_query and onboarding_stage_query.exists())
            or (onboarding_task_query and onboarding_task_query.exists())
            or (recruitment_manager_query and recruitment_manager_query.exists())
        ):
            return False
        else:
            related_models = []
            related_model_fields = []
            if reporting_manager_query.exists():
                related_models.append(
                    {
                        "verbose_name": _("Reporting manager"),
                        "field_name": "reporting_manager_id",
                    }
                )
            if recruitment_manager_query and recruitment_manager_query.exists():
                related_models.append(
                    {
                        "verbose_name": _("Recruitment manager"),
                        "field_name": "recruitment_managers",
                    }
                )
            if recruitment_stage_query and recruitment_stage_query.exists():
                related_models.append(
                    {
                        "verbose_name": _("Recruitment stage manager"),
                        "field_name": "recruitment_stage_managers",
                    }
                )
            if onboarding_stage_query and onboarding_stage_query.exists():
                related_models.append(
                    {
                        "verbose_name": _("Onboarding stage manager"),
                        "field_name": "onboarding_stage_manager",
                    }
                )
            if onboarding_task_query and onboarding_task_query.exists():
                related_models.append(
                    {
                        "verbose_name": _("Onboarding task manager"),
                        "field_name": "onboarding_task_manager",
                    }
                )
            related_models_dict = {
                "related_models": related_models,
            }
            try:
                REPLACE_EMPLOYEE_CHOICES = [("", _("---Choose employee---"))] + [
                    (
                        employee_id,
                        f"{first_name} {last_name}" if last_name else first_name,
                    )
                    for employee_id, first_name, last_name in Employee.objects.filter(
                        is_active=True
                    ).values_list("id", "employee_first_name", "employee_last_name")
                ]
                related_models_dict["employee_choices"] = REPLACE_EMPLOYEE_CHOICES
            except:
                pass
            return related_models_dict

    def __str__(self) -> str:
        last_name = (
            self.employee_last_name if self.employee_last_name is not None else ""
        )
        badge_id = (f"({self.badge_id})") if self.badge_id is not None else ""
        return f"{self.employee_first_name} {last_name} {badge_id}"

    def employee_name_with_badge_id(self):

        last_name = (
            self.employee_last_name if self.employee_last_name is not None else ""
        )
        badge_id = (f"({self.badge_id})") if self.badge_id is not None else ""
        return f"{self.employee_first_name} {last_name} {badge_id}"

    def get_history_col(self):
        """
        Renders a clickable icon that opens this employee's activity-history
        feed -- the same feed shown on the profile page's History tab -- in
        the shared #historySidebar, matching the History column every
        HorillaModel-based list already gets automatically (see
        HorillaListView's history_tracking handling). Employee doesn't
        subclass HorillaModel, so it's added explicitly here instead.
        """
        return render_template(
            path="cbv/employees/history_col.html",
            context={
                "instance": self,
                "history_url": reverse_lazy(
                    "employee-history-sidebar", kwargs={"pk": self.pk}
                ),
            },
        )

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("employee-view-update", kwargs={"obj_id": self.pk})
        return url

    def get_archive_url(self):
        """
        This method to get archive  url
        """
        url = reverse_lazy("employee-archive", kwargs={"obj_id": self.pk})
        return url

    def get_individual_url(self):
        """
        This method to get individual  url
        """
        url = reverse_lazy("employee-view-individual", kwargs={"obj_id": self.pk})
        return url

    def get_pay_contract(self):
        """
        The contract this employee's pay is read from: the active one, and
        nothing when there is none. Pay lives on the contract; the salary fields
        on the work information are the old copy and are no longer shown or
        edited.
        """
        if not apps.is_installed("payroll"):
            return None
        return (
            self.contract_set.filter(contract_status="active")
            .order_by("-contract_start_date", "-id")
            .first()
        )

    def get_pay_summary(self):
        """
        The one figure to show for this employee's pay, and what it is called:
        the monthly CTC when the contract is on a CTC Down structure (that is
        the number the structure divides), the hourly rate for an hourly
        contract, the basic salary otherwise. None when there is no active
        contract.
        """
        contract = self.get_pay_contract()
        if contract is None:
            return None
        structure = contract.salary_structure_id
        if structure is not None and (structure.structure_mode or "") == "ctc_down":
            return {
                "label": _("CTC"),
                "amount": contract.monthly_ctc or contract.wage,
                "contract": contract,
            }
        if contract.wage_type == "hourly":
            return {
                "label": _("Hourly"),
                "amount": contract.hourly_wage or contract.wage,
                "contract": contract,
            }
        return {"label": _("Basic"), "amount": contract.wage, "contract": contract}

    def get_pay_contract_url(self):
        """
        Where the pay is changed: the edit form of the active contract, or, with
        no active contract, the contracts list showing just this employee's.
        """
        contract = self.get_pay_contract()
        if contract is not None:
            return reverse("update-contract", kwargs={"contract_id": contract.pk})
        return f"{reverse('view-contract')}?employee_id={self.pk}&filter_applied=true"

    def get_profile_url(self):
        """
        This method to get individual  url
        """
        url = reverse_lazy("profile-new", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete  url
        """
        url = reverse_lazy("generic-delete")
        return url

    def employee_actions(self):
        """
        This method for get custom column for actions.
        """

        return render_template(
            path="cbv/employees_view/employee_actions.html",
            context={"instance": self},
        )

    def archive_status(self):
        """
        archive status
        """
        if self.is_active:
            return _("Archive")
        else:
            return _("Un-Archive")

    def check_online(self):
        """
        This method is used to check if the user is in the list of online users.
        """
        if apps.is_installed("attendance"):
            Attendance = get_horilla_model_class("attendance", "attendance")
            request = getattr(horilla_middlewares._thread_locals, "request", None)

            if request is not None:
                if (
                    not hasattr(request, "working_employees")
                    or request.working_employees is None
                ):
                    today = datetime.now().date()
                    yesterday = today - timedelta(days=1)
                    working_employees = Attendance.objects.filter(
                        attendance_date__gte=yesterday,
                        attendance_date__lte=today,
                        attendance_clock_out_date__isnull=True,
                    ).values_list("employee_id", flat=True)
                    setattr(request, "working_employees", working_employees)
                working_employees = request.working_employees
                return self.pk in working_employees
        return False

    class Meta:
        """
        Recruitment model
        """

        unique_together = ("employee_first_name", "employee_last_name", "email")
        permissions = (
            ("change_ownprofile", "Update own profile"),
            ("view_ownprofile", "View Own Profile"),
        )
        ordering = [
            "id",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["badge_id"],
                condition=models.Q(badge_id__isnull=False),
                name="unique_badge_id",
            )
        ]

    def days_until_birthday(self):
        """
        This method will calculate the day until birthday
        """
        birthday = self.dob
        today = date.today()
        next_birthday = date(today.year, birthday.month, birthday.day)
        if next_birthday < today:
            next_birthday = date(today.year + 1, birthday.month, birthday.day)
        return (next_birthday - today).days

    def get_last_sent_mail(self):
        """
        This method is used to get last send mail
        """
        from base.models import EmailLog

        return (
            EmailLog.objects.filter(to__icontains=self.get_mail())
            .order_by("-created_at")
            .first()
        )

    def get_subordinate_employees(self):
        """
        Function to get all Employee objects of subordinates reporting to a given manager.
        :param manager: Employee object who is the reporting manager.
        :return: QuerySet of Employee objects.
        """
        subordinates = Employee.objects.filter(
            employee_work_info__reporting_manager_id=self
        )
        return subordinates

    def _employee_profile_path_matches_db(self, file) -> bool:
        """
        True if the in-memory file field still points at the same path as in the DB.
        Used to skip strict validation when the file is missing from storage but the
        row was not given a new upload (e.g. archive, other saves that touch is_active).
        """
        if not self.pk or not file:
            return False
        current = (getattr(file, "name", None) or "").strip()
        if not current:
            return False
        try:
            stored = (
                Employee.objects.filter(pk=self.pk)
                .values_list("employee_profile", flat=True)
                .first()
            )
        except Exception:
            return False
        stored = (stored or "").strip()
        return bool(stored) and stored == current

    def clean(self):
        super().clean()

        file = self.employee_profile
        if not file:
            return

        # Committed = already saved to storage; unreadable path → don't block saves.
        committed = getattr(file, "committed", False)
        same_as_db = self._employee_profile_path_matches_db(file)

        try:
            file.seek(0)
            content = file.read()
        except Exception:
            if committed or same_as_db:
                return
            raise ValidationError({"employee_profile": "Unable to read uploaded file."})

        is_svg = False
        try:
            text = content.decode("utf-8", errors="strict")
            root = ET.fromstring(text)
            if root.tag.endswith("svg"):
                is_svg = True
        except Exception:
            pass

        if not is_svg:
            try:
                file.seek(0)
                Image.open(file).verify()
            except Exception:
                if committed or same_as_db:
                    return
                raise ValidationError(
                    {"employee_profile": "Invalid image or SVG file."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if request and not self.is_active and self.get_archive_condition() is not False:
            self.is_active = True
            super().save(*args, **kwargs)
        employee = self

        if employee.employee_user_id is None:
            # Create user if no corresponding user exists
            username = self.email
            password = generate_random_password()

            # The email is unique among Employees, but an unrelated
            # HorillaUser can already own it as a username -- e.g. an
            # orphaned account left behind by a deleted employee. Fall back
            # to a random username rather than crashing on the uniqueness
            # constraint; email stays the real address either way.
            if HorillaUser.objects.filter(username=username).exists():
                username = generate_unique_fallback_username()

            user = HorillaUser.objects.create_user(
                username=username,
                email=self.email,
                password=password,
                is_new_employee=True,
            )
            if not user:
                user = HorillaUser.objects.create_user(
                    username=username, email=self.email, password=password
                )
            self.employee_user_id = user
            # default permissions
            change_ownprofile = Permission.objects.get(codename="change_ownprofile")
            view_ownprofile = Permission.objects.get(codename="view_ownprofile")
            user.user_permissions.add(view_ownprofile)
            user.user_permissions.add(change_ownprofile)

        if not hasattr(self, "employee_work_info"):
            EmployeeWorkInformation.objects.get_or_create(employee_id=self)
            return self.save()

        return self


class EmployeeTag(HorillaModel):
    """
    EmployeeTag Model
    """

    title = models.CharField(max_length=50, null=True, verbose_name=_("Title"))
    color = models.CharField(max_length=30, null=True)

    def __str__(self) -> str:
        return f"{self.title}"

    def color_span(self):
        """
        to return color into correct format
        """
        return (
            '<span style="height: 25px; width: 25px; '
            'background-color: {}; border-radius: 50%; display: inline-block;"></span>'
        ).format(self.color)

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("employee-tag-update-form", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("employee-tag-delete", kwargs={"obj_id": self.pk})
        return url

    def get_instance_id(self):
        return self.id


class EmployeeWorkInformation(models.Model):
    """
    EmployeeWorkInformation model
    """

    employee_id = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="employee_work_info",
        verbose_name=_("Employee"),
    )
    department_id = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Department"),
    )
    job_position_id = models.ForeignKey(
        JobPosition,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Job Position"),
    )
    job_role_id = models.ForeignKey(
        JobRole,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Job Role"),
    )
    reporting_manager_id = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="reporting_manager",
        verbose_name=_("Reporting Manager"),
    )
    shift_id = models.ForeignKey(
        EmployeeShift,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        verbose_name=_("Shift"),
    )
    work_type_id = models.ForeignKey(
        WorkType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Work Type"),
    )

    employee_type_id = models.ForeignKey(
        EmployeeType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Employee Type"),
    )
    tags = models.ManyToManyField(
        EmployeeTag, blank=True, verbose_name=_("Employee tag")
    )
    location = models.CharField(
        max_length=254, null=True, blank=True, verbose_name=_("Work Location")
    )
    company_id = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_("Company"),
    )
    email = models.EmailField(
        max_length=254, blank=True, null=True, verbose_name=_("Work Email")
    )
    mobile = models.CharField(
        max_length=254,
        blank=True,
        null=True,
        verbose_name=_("Work Phone"),
        validators=[phone_validator],
    )

    date_joining = models.DateField(
        null=True, blank=True, verbose_name=_("Joining Date")
    )
    contract_end_date = models.DateField(
        blank=True, null=True, verbose_name=_("Contract End Date")
    )
    basic_salary = models.IntegerField(
        null=True, blank=True, default=0, verbose_name=_("Basic Salary")
    )
    salary_hour = models.IntegerField(
        null=True, blank=True, default=0, verbose_name=_("Salary Per Hour")
    )
    additional_info = models.JSONField(null=True, blank=True)
    experience = models.FloatField(null=True, blank=True, default=0)
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )
    objects = HorillaCompanyManager()

    def __str__(self) -> str:
        return f"{self.employee_id} - {self.job_position_id}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.skip_history = False

    def calculate_progress(self):
        fields_to_focus = [
            "job_position_id",
            "department_id",
            "work_type_id",
            "employee_type_id",
            "job_role_id",
            "reporting_manager_id",
            "company_id",
            "location",
            "email",
            "mobile",
            "shift_id",
            "date_joining",
            "contract_end_date",
            "basic_salary",
            "salary_hour",
        ]

        completed_field_count = sum(
            1 for field_name in fields_to_focus if getattr(self, field_name) is not None
        )
        total_fields = len(fields_to_focus)
        percent = (
            (completed_field_count / total_fields) * 100 if total_fields > 0 else 0
        )
        return round(percent, 1)

    def progress_col(self):
        """
        This method for get custome coloumn for progress.
        """

        return render_template(
            path="cbv/dashboard/progress.html",
            context={"instance": self},
        )

    def get_edit_url(self):
        """
        To get edit url
        """

        url = reverse("update-emp-workinfo", kwargs={"pk": self.pk})
        return url

    def tracking(self):
        """
        This method is used to return the tracked history of the instance
        """
        return get_diff(self)

    def experience_calculator(self):
        """
        This method is to calculate the default value for experience field
        """
        joining_date = self.date_joining
        if joining_date is None:
            return 0
        current_date = datetime.now().date()

        # Calculate the difference between the current date and joining date
        delta = current_date - joining_date

        # Calculate the total number of days
        total_days = delta.days

        # Calculate the number of experience as a float
        experience = total_days / 365.0
        self.experience = experience
        self.save()
        return self


class EmployeeBankDetails(HorillaModel):
    """
    EmployeeBankDetails model
    """

    employee_id = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        null=True,
        related_name="employee_bank_details",
        verbose_name=_("Employee"),
    )
    bank_name = models.CharField(max_length=50, null=True, verbose_name=_("Bank Name"))
    account_number = models.CharField(
        max_length=50,
        null=True,
        blank=False,
    )
    branch = models.CharField(max_length=50, null=True)
    address = models.TextField(max_length=255, null=True)
    country = models.CharField(max_length=50, null=True, blank=True)
    state = models.CharField(max_length=50, null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    any_other_code1 = models.CharField(
        max_length=50, verbose_name="Bank Code #1", null=True
    )
    any_other_code2 = models.CharField(
        max_length=50, null=True, blank=True, verbose_name="Bank Code #2"
    )
    additional_info = models.JSONField(null=True, blank=True)
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )

    class Meta:
        verbose_name = _("Employee Bank Details")
        verbose_name_plural = _("Employee Bank Details")

    def __str__(self) -> str:
        return f"{self.employee_id}-{self.bank_name}"

    def clean(self):
        if self.account_number is not None:
            bank_details = EmployeeBankDetails.objects.exclude(
                employee_id=self.employee_id
            ).filter(account_number=self.account_number)
            if bank_details:
                raise ValidationError(
                    {
                        "account_number": _(
                            "Bank details for an employee with this account number already exist"
                        )
                    }
                )


class NoteFiles(HorillaModel):
    files = models.FileField(upload_to=upload_path, blank=True, null=True)
    objects = models.Manager()

    def __str__(self):
        return self.files.name.split("/")[-1]


class EmployeeNote(HorillaModel):
    """
    EmployeeNote model
    """

    employee_id = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="employee_name",
    )
    description = models.TextField(verbose_name=_("Description"), null=True)  # 905
    note_files = models.ManyToManyField(NoteFiles, blank=True)
    updated_by = models.ForeignKey(Employee, on_delete=models.CASCADE)
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )

    def __str__(self) -> str:
        return f"{self.description}"


class PolicyMultipleFile(HorillaModel):
    """
    PoliciesMultipleFile model
    """

    attachment = models.FileField(upload_to=upload_path)

    @property
    def _attachment_name(self):
        """Never None: an attachment row whose file failed to save has no name."""
        return (self.attachment.name or "").lower()

    @property
    def is_pdf(self):
        """Lets templates inline the document instead of linking an icon."""
        return self._attachment_name.endswith(".pdf")

    @property
    def is_image(self):
        """Images get the same inline treatment as PDFs.

        SVG is deliberately absent: it is browser-executable, and inlining one
        from this origin would be stored XSS.
        """
        return self._attachment_name.endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp")
        )


class Policy(HorillaModel):
    """
    Policies model
    """

    title = models.CharField(max_length=50)
    body = models.TextField()
    employees = models.ManyToManyField(
        Employee,
        related_name="policy_employees",
        blank=True,
        help_text=_(
            "Used only when 'Publish' is disabled below -- restricts the "
            "policy to these employees plus anyone in the selected department(s) "
            "or job position(s)."
        ),
    )
    department = models.ManyToManyField(Department, blank=True)
    job_position = models.ManyToManyField(
        JobPosition, blank=True, verbose_name=_("Job Position")
    )
    filtered_employees = models.ManyToManyField(
        Employee, related_name="policy_filtered_employees", editable=False
    )
    attachments = models.ManyToManyField(PolicyMultipleFile, blank=True)
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))
    is_visible_to_all = models.BooleanField(
        default=True,
        verbose_name=_("Publish to all"),
        help_text=_(
            "When enabled, the policy is visible to every employee in the "
            "selected company. Disable it to restrict visibility to the "
            "employees/department/job position selected above."
        ),
    )

    objects = HorillaCompanyManager("company_id")

    class Meta:
        verbose_name = _("Policy")
        verbose_name_plural = _("Policies")

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.attachments.all().delete()


class BonusPoint(HorillaModel):
    """
    Model representing bonus points for employees with associated conditions.
    """

    CONDITIONS = [
        ("==", _("equals")),
        (">", _("greater than")),
        ("<", _("less than")),
        (">=", _("greater than or equal")),
        ("<=", _("less than or equal")),
    ]
    employee_id = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="bonus_point",
    )
    points = models.IntegerField(
        default=0, help_text=_("Use negative numbers to reduce points.")
    )
    encashment_condition = models.CharField(
        max_length=100, choices=CONDITIONS, blank=True, null=True
    )
    redeeming_points = models.IntegerField(blank=True, null=True)
    reason = models.TextField(blank=True, null=True, max_length=255)
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )

    def __str__(self):
        return f"{self.employee_id} - {self.points} Points"

    def tracking(self):
        """
        This method is used to return the tracked history of the instance
        """
        return get_diff(self)

    @receiver(post_save, sender=Employee)
    def bonus_post_save(sender, instance, **_kwargs):
        """
        Creates a BonusPoint instance for a newly created Employee if one doesn't already exist.

        Args:
            sender (Employee): The model class (Employee) sending the signal.
            instance (Employee): The instance of the Employee model triggering the
                                post-save signal.
            **_kwargs: Additional keyword arguments passed by the signal.
        """
        if not BonusPoint.objects.filter(employee_id__id=instance.id).exists():
            BonusPoint.objects.create(employee_id=instance)


class Actiontype(HorillaModel):
    """
    Action type model
    """

    choice_actions = [
        ("warning", _("Warning")),
        ("suspension", _("Suspension")),
        ("dismissal", _("Dismissal")),
    ]

    title = models.CharField(max_length=50)
    action_type = models.CharField(
        max_length=30, choices=choice_actions, verbose_name=_("Action Type")
    )
    block_option = models.BooleanField(
        default=False,
        verbose_name=_("Enable login block :"),
        help_text=_(
            "If is enabled, employees log in will be blocked based on period of suspension or dismissal."
        ),
    )

    class Meta:
        verbose_name = _("Action Type")
        verbose_name_plural = _("Action Types")

    def __str__(self) -> str:
        return f"{self.title}"

    def get_block_option(self):
        """
        To get block option
        """
        if self.block_option:
            return _("Yes")
        return _("No")

    def get_action_type_display(self):
        """
        Display action type
        """
        return dict(self.choice_actions).get(self.action_type)

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("update-action-type", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("generic-delete")
        return url

    def get_instance_id(self):
        """
        To get instance in list view
        """
        return self.id


class DisciplinaryAction(HorillaModel):
    """
    Disciplinary model
    """

    choices = [("days", _("Days")), ("hours", _("Hours"))]
    employee_id = models.ManyToManyField(Employee, verbose_name=_("Employees"))
    action = models.ForeignKey(Actiontype, on_delete=models.CASCADE)
    description = models.TextField(max_length=255)
    unit_in = models.CharField(max_length=10, choices=choices, default="days")
    days = models.IntegerField(null=True, default=1)
    hours = models.CharField(
        max_length=6,
        default="00:00",
        null=True,
        validators=[validate_time_format],
    )
    start_date = models.DateField(null=True)
    attachment = models.FileField(upload_to=upload_path, null=True, blank=True)
    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    def __str__(self) -> str:
        return f"{self.action}"

    class Meta:
        ordering = ["-id"]

    def employee_column(self):
        """
        This method for get custom column for employee.
        """

        return render_template(
            path="cbv/disciplinary_actions/employee_col.html",
            context={"instance": self},
        )

    def action_taken_col(self):
        """
        This method for get custom column for employee.
        """

        return render_template(
            path="cbv/disciplinary_actions/action_taken.html",
            context={"instance": self},
        )

    def block_option_col(self):
        """
        block option column
        """
        if self.action.block_option:
            return _("Yes")
        else:
            return _("No")

    def action_date_col(self):
        """
        This method for get custom column for action date.
        """

        return render_template(
            path="cbv/disciplinary_actions/action_date.html",
            context={"instance": self},
        )

    def get_avatar(self):
        """
        Method will retun the api to the avatar or path to the profile image
        """
        url = f"https://ui-avatars.com/api/?name={self.action}&background=random"
        return url

    def attachments_col(self):
        """
        This method for get custom column for attachments.
        """

        return render_template(
            path="cbv/disciplinary_actions/attachments.html",
            context={"instance": self},
        )

    def actions(self):
        """
        This method for get custom column for actions.
        """

        return render_template(
            path="cbv/disciplinary_actions/actions.html",
            context={"instance": self},
        )

    def detail_actions(self):
        """
        This method for get custom column for actions.
        """

        return render_template(
            path="cbv/disciplinary_actions/detail_action.html",
            context={"instance": self},
        )

    def employee_detail(self):
        """
        interviewer in detail view
        """
        employees = self.employee_id.all()
        employee_names_string = "<br>".join([str(employee) for employee in employees])
        return employee_names_string

    def dis_action_detail_view(self):
        """
        detail view
        """
        url = reverse("disciplinary-actions-detail-view", kwargs={"pk": self.pk})
        return url


class EmployeeGeneralSetting(HorillaModel):
    """
    EmployeeGeneralSetting
    """

    badge_id_prefix = models.CharField(max_length=5, default="PEP")
    company_id = models.ForeignKey(Company, null=True, on_delete=models.CASCADE)
    objects = HorillaCompanyManager("company_id")


class ProfileEditFeature(HorillaModel):
    """
    ProfileEditFeature
    """

    is_enabled = models.BooleanField(default=False)
    objects = models.Manager()


ACCESSBILITY_FEATURE.append(("gender_chart", _("Can view Gender Chart")))
ACCESSBILITY_FEATURE.append(("department_chart", _("Can view Department Chart")))
ACCESSBILITY_FEATURE.append(("employees_chart", _("Can view Employees Chart")))
ACCESSBILITY_FEATURE.append(("birthday_view", _("Can view Birthdays")))
