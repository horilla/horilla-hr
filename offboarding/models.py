import json
from ast import literal_eval
from collections.abc import Iterable
from datetime import date, timedelta
from urllib.parse import urlencode

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse, reverse_lazy
from django.utils.timesince import timesince
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company
from employee.models import Employee
from horilla import horilla_middlewares
from horilla.horilla_middlewares import _thread_locals
from horilla.methods import get_horilla_model_class
from horilla.models import HorillaModel, upload_path
from horilla_audit.models import HorillaAuditInfo, HorillaAuditLog
from horilla_views.cbv_methods import render_template
from notifications.signals import notify

# Create your models here.


class Offboarding(HorillaModel):
    """
    Offboarding model
    """

    statuses = [("ongoing", _("Ongoing")), ("completed", _("Completed"))]
    title = models.CharField(max_length=20)
    description = models.TextField(max_length=255)
    managers = models.ManyToManyField(Employee)
    status = models.CharField(max_length=10, default="ongoing", choices=statuses)
    company_id = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        null=True,
        verbose_name="Company",
    )
    objects = HorillaCompanyManager("company_id")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        is_new = not self.pk
        super().save(*args, **kwargs)
        if is_new:
            stages = [
                ("Exit interview", "interview"),
                ("Work Handover", "handover"),
                ("FNF", "fnf"),
                ("Farewell", "other"),
                ("Archived", "archived"),
            ]
            for stage in stages:
                new = OffboardingStage()
                new.offboarding_id = self
                new.title = stage[0]
                new.type = stage[1]
                new.save()

        return


class OffboardingStage(HorillaModel):
    """
    Offboarding model
    """

    types = [
        ("notice_period", _("Notice period")),
        ("fnf", _("FnF Settlement")),
        ("other", _("Other")),
        ("interview", _("Interview")),
        ("handover", _("Work handover")),
        ("archived", _("Archived")),
    ]

    title = models.CharField(max_length=20)
    type = models.CharField(max_length=13, choices=types)
    offboarding_id = models.ForeignKey(Offboarding, on_delete=models.CASCADE)
    managers = models.ManyToManyField(Employee)
    sequence = models.IntegerField(default=0, editable=False)

    def __str__(self) -> str:
        return str(self.title)

    def is_archived_stage(self):
        """
        This method is to check the stage is archived or not
        """
        return self.type == "archived"

    def get_delete_url(self):
        """
        This method is used to get delete url
        """
        query = urlencode(
            {
                "model": "offboarding.OffboardingStage",
                "pk": str(self.pk),
                "reload_target": "#applyFilter",
            }
        )
        return f"{reverse('generic-delete')}?{query}"

    def get_update_url(self):
        """
        This method is used to get update url
        """
        return f'{reverse_lazy("create-offboarding-stage", kwargs={"pk": self.pk})}?offboarding_id={self.offboarding_id.pk}'

    def get_add_employee_url(self):
        """
        This method is used to get add employee url
        """
        url = f'{reverse_lazy("add-offboarding-employee")}?stage_id={self.id}'

        return url


@receiver(post_save, sender=Offboarding)
def create_initial_stage(sender, instance, created, **kwargs):
    """
    This is post save method, used to create initial stage for the recruitment
    """
    # Not while loading a fixture: the dump already carries its own stages, so
    # an extra "Notice Period" here would sit next to the loaded one.
    if created and not kwargs.get("raw"):
        initial_stage = OffboardingStage()
        initial_stage.title = "Notice Period"
        initial_stage.offboarding_id = instance
        initial_stage.type = "notice_period"
        initial_stage.save()


class OffboardingStageMultipleFile(HorillaModel):
    """
    OffboardingStageMultipleFile
    """

    attachment = models.FileField(upload_to=upload_path)


class OffboardingEmployee(HorillaModel):
    """
    OffboardingEmployee model / Employee on stage
    """

    UNIT = [("day", "days"), ("month", "Month")]
    employee_id = models.OneToOneField(
        Employee, on_delete=models.CASCADE, verbose_name="Employee"
    )
    stage_id = models.ForeignKey(
        OffboardingStage, on_delete=models.CASCADE, verbose_name="Stage", null=True
    )
    notice_period = models.IntegerField(null=True)
    unit = models.CharField(max_length=10, choices=UNIT, default="month", null=True)
    notice_period_starts = models.DateField(
        null=True, verbose_name=_("Notice Period Starts")
    )
    notice_period_ends = models.DateField(
        null=True, blank=True, verbose_name=_("Notice Period Ends")
    )
    objects = HorillaCompanyManager(
        related_company_field="employee_id__employee_work_info__company_id"
    )

    def __str__(self) -> str:
        return self.employee_id.get_full_name()

    def detail_subtitle(self):
        """
        Return subtitle containing both department and job position information.
        """
        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def detail_view_task_custom(self):
        """
        This method for get custom column for stage in detail view.
        """
        tasks = self.employeetask_set.all()

        return render_template(
            path="cbv/exit_process/detail_view_tasks.html",
            context={
                "instance": self,
                "tasks": tasks,
            },
        )

    def get_individual_url(self):
        """
        This method is used to get individual view url
        """
        return f'{reverse_lazy("offboarding-individual-view", kwargs={"pk": self.pk})}'

    def get_notice_period_col(self):
        """
        This method for get custom column for notice period in detail view.
        """

        notice_period_ends = self.notice_period_ends
        today = date.today()

        if notice_period_ends:
            col = (
                _("today")
                if notice_period_ends == today
                else (
                    _("Notice period ended")
                    if notice_period_ends < today
                    else (
                        _("In") + " " + timesince(today, notice_period_ends)
                        if notice_period_ends
                        else ""
                    )
                )
            )

        return col if notice_period_ends else ""

    def get_stage_col(self):
        """
        This method for get custom column for stage in Pipeline view.
        """
        from offboarding.forms import StageSelectForm

        return render_template(
            path="cbv/exit_process/pipeline_stage_col.html",
            context={
                "employee": self,
                "stage_form": StageSelectForm(
                    offboarding=self.stage_id.offboarding_id,
                    initial={"stage_id": self.stage_id.pk},
                ),
                "stages": self.stage_id.offboarding_id.offboardingstage_set.all(),
            },
        )

    def pending_required_tasks(self, stage=None):
        """
        Required offboarding tasks assigned to this employee in ``stage``
        (defaults to the employee's current stage) that are not yet completed.
        """
        stage = stage or self.stage_id
        completed_task_ids = EmployeeTask.objects.filter(
            employee_id=self,
            task_id__stage_id=stage,
            status="completed",
        ).values_list("task_id", flat=True)
        return (
            OffboardingTask.objects.filter(
                stage_id=stage,
                is_required=True,
                employeetask__employee_id=self,
            )
            .exclude(id__in=completed_task_ids)
            .distinct()
        )

    def get_task_status_col(self):
        """
        This method for get custom column for task status in Pipeline view.
        """
        completed_tasks = self.employeetask_set.filter(status="completed").count()
        total_tasks = self.employeetask_set.all().count()

        task_status = f"{completed_tasks} / {total_tasks}"
        col = f"""
            <div class="oh-checkpoint-badge oh-checkpoint-badge--primary" title="{_('Completed')} {completed_tasks} {_('of')} {total_tasks} {_('tasks')}">
                {task_status}
            </div>
        """
        return col

    def get_action_col(self):
        """
        This method for get custom column for action in Pipeline view.
        """
        return render_template(
            path="cbv/exit_process/pipeline_action_col.html",
            context={"employee": self, "stage": self.stage_id},
        )

    def detail_action_col(self):
        """
        Action buttons for the exit process detail modal - same buttons,
        same conditions, as get_action_col's pipeline card actions.
        """
        return render_template(
            path="cbv/exit_process/detail_action_col.html",
            context={"instance": self},
        )

    def __getattribute__(self, name):
        if name.startswith("get_") and name.endswith("_task"):
            task_id = literal_eval(name[4:-5])
            task = EmployeeTask.objects.filter(
                task_id__id=task_id,
                employee_id_id=self.id,
                task_id__stage_id=self.stage_id,
            ).first()

            return render_template(
                "cbv/exit_process/tasks_cols.html",
                {"instance": self, "task": task, "task_id": task_id},
            )
        value = super().__getattribute__(name)

        return value

    def ordered_group_json(self):
        """
        This method is used to get ordered group json
        """
        Offboarding = self.stage_id.offboarding_id
        offboarding_stages = Offboarding.offboardingstage_set.all().order_by("sequence")
        ordered_group_json = json.dumps(
            [
                {
                    "id": stage.id,
                    "stage": stage.title,
                }
                for stage in offboarding_stages
            ]
        )
        return ordered_group_json

    def get_archive_title(self):
        """
        This method is used to get title for the archive in actions
        """
        return "Archive" if self.employee_id.is_active else "Un-Archive"

    def get_mail_send_url(self):
        """
        This method is used to get the mail send url
        """
        return f'{reverse_lazy("send-mail-employee", kwargs={"emp_id": self.pk})}'

    def get_notes_url(self):
        """
        This method is used to get the employee note view url
        """
        return (
            f'{reverse_lazy("view-offboarding-note", kwargs={"employee_id": self.pk})}'
        )

    def get_archive_url(self):
        """
        This method is used to get the mail send url
        """
        return f'{reverse_lazy("employee-archive", kwargs={"obj_id": self.pk})}'

    def get_edit_url(self):
        """
        This method is used to get the mail send url
        """
        return f'{reverse_lazy("add-employee", kwargs={"pk": self.pk})}?stage_id={self.stage_id.id}'

    def get_managing_record_url(self):
        """
        This method is used to get the mail send url
        """
        return f'{reverse_lazy("get-manager-in")}?employee_id={self.employee_id.id}&offboarding=True'


class ResignationLetter(HorillaModel):
    """
    Resignation Request Employee model
    """

    statuses = [
        ("requested", _("Requested")),
        ("approved", _("Approved")),
        ("rejected", _("Rejected")),
    ]
    employee_id = models.ForeignKey(
        Employee, on_delete=models.CASCADE, verbose_name="Employee"
    )
    title = models.CharField(max_length=100, null=True)
    description = models.TextField(null=True, max_length=255)
    planned_to_leave_on = models.DateField(verbose_name=_("Planned To Leave On"))
    status = models.CharField(max_length=10, choices=statuses, default="requested")
    offboarding_employee_id = models.ForeignKey(
        OffboardingEmployee, on_delete=models.CASCADE, editable=False, null=True
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

    def get_status(self):
        """
        Display status
        """
        return dict(self.statuses).get(self.status)

    def get_status_badge(self):
        """
        Display status as a styled badge for the detail view.
        """
        badge_colors = {
            "requested": "#808080",
            "approved": "#8db600",
            "rejected": "#ff0000",
        }
        label = dict(self.statuses).get(self.status, self.status)
        color = badge_colors.get(self.status, "#808080")
        return (
            f'<span style="background-color:{color}; color:#fff; '
            f'padding:3px 10px; border-radius:4px; font-size:0.8rem;">'
            f"{label}</span>"
        )

    def option_column(self):
        """
        This method for get custome coloumn .
        """

        return render_template(
            path="cbv/resignation/options.html",
            context={"instance": self},
        )

    def actions_column(self):
        """
        This method for get custome coloumn .
        """

        return render_template(
            path="cbv/resignation/actions.html",
            context={"instance": self},
        )

    def description_col(self):
        """
        This method for get custome column .
        """

        return render_template(
            path="cbv/resignation/description.html",
            context={"instance": self},
        )

    def detail_description_col(self):
        """
        This method for get custome column .
        """

        return render_template(
            path="cbv/resignation/detail_description.html",
            context={"instance": self},
        )

    def resignation_subtitle(self):
        """
        Detail view subtitle
        """

        return f"{self.employee_id.get_department()} / {self.employee_id.get_job_position()}"

    def get_detail_url(self):
        """
        Detail view url
        """
        url = reverse_lazy("resignation-requests-detail-view", kwargs={"pk": self.pk})
        return url

    def get_detail_tab_url(self):
        """
        Detail view url
        """
        url = reverse_lazy(
            "tab-resignation-requests-detail-view", kwargs={"pk": self.pk}
        )
        return url

    def clean(self):
        super().clean()
        if self.pk:
            original = (
                ResignationLetter.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if original == "rejected":
                raise ValidationError(
                    _("A rejected resignation letter cannot be modified.")
                )
        if self.employee_id_id:
            existing = ResignationLetter.objects.filter(
                employee_id=self.employee_id_id,
                status__in=["requested", "approved"],
            )
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError(
                    _(
                        "A resignation letter for this employee is already in "
                        "'Requested' or 'Approved' status."
                    )
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        if self.status == "approved":
            pass
        return

    def to_offboarding_employee(
        self, offboarding, notice_period_starts, notice_period_ends
    ):
        """
        This method is used to convert/add employee to offboarding
        """
        offboarding_employee = OffboardingEmployee.objects.filter(
            employee_id=self.employee_id
        ).first()
        offboarding_employee = (
            offboarding_employee if offboarding_employee else OffboardingEmployee()
        )
        offboarding_employee.employee_id = self.employee_id
        offboarding_employee.stage_id = (
            OffboardingStage.objects.order_by("created_at")
            .filter(offboarding_id=offboarding)
            .first()
        )
        default_notice_end = (
            get_horilla_model_class(
                app_label="payroll", model="payrollgeneralsetting"
            ).objects.first()
            if apps.is_installed("payroll")
            else None
        )

        try:
            if not notice_period_ends:
                notice_period_ends = (
                    notice_period_starts + timedelta(default_notice_end.notice_period)
                    if default_notice_end
                    else notice_period_ends
                )
        except:
            notice_period_ends = notice_period_ends

        offboarding_employee.notice_period_starts = notice_period_starts
        offboarding_employee.notice_period_ends = notice_period_ends
        if (
            notice_period_starts
            and notice_period_ends
            and not isinstance(notice_period_starts, str)
            and not isinstance(notice_period_ends, str)
        ):
            diffs = date(
                day=notice_period_ends.day,
                month=notice_period_ends.month,
                year=notice_period_ends.year,
            ) - date(
                day=notice_period_starts.day,
                month=notice_period_starts.month,
                year=notice_period_starts.year,
            )
            diffs = diffs.days
            offboarding_employee.notice_period = diffs if diffs > 0 else None
            offboarding_employee.unit = "day" if diffs > 0 else None
        offboarding_employee.save()


class OffboardingTask(HorillaModel):
    """
    OffboardingTask model
    """

    title = models.CharField(max_length=30)
    managers = models.ManyToManyField(Employee)
    stage_id = models.ForeignKey(
        OffboardingStage,
        on_delete=models.PROTECT,
        verbose_name="Stage",
        null=True,
        blank=True,
    )
    is_required = models.BooleanField(default=False, verbose_name=_("Is Required"))

    class Meta:
        unique_together = ["title", "stage_id"]

    def __str__(self) -> str:
        return self.title


class EmployeeTask(HorillaModel):
    """
    EmployeeTask model
    """

    statuses = [
        ("todo", _("Todo")),
        ("in_progress", _("In progress")),
        ("stuck", _("Stuck")),
        ("completed", _("Completed")),
    ]
    employee_id = models.ForeignKey(
        OffboardingEmployee,
        on_delete=models.CASCADE,
        verbose_name="Employee",
        null=True,
    )
    status = models.CharField(max_length=20, choices=statuses, default="todo")
    task_id = models.ForeignKey(OffboardingTask, on_delete=models.CASCADE)
    description = models.TextField(null=True, editable=False, max_length=255)
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )

    class Meta:
        unique_together = ["employee_id", "task_id"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        request = getattr(_thread_locals, "request", None)
        notify.send(
            request.user.employee_get,
            recipient=self.employee_id.employee_id.employee_user_id,
            verb=gettext_noop('Offboarding task "%(title)s" has been assigned'),
            verb_params={"title": str(self.task_id.title)},
            redirect="offboarding/offboarding-pipeline",
            icon="information",
        )


class ExitReason(HorillaModel):
    """
    ExitReason model
    """

    title = models.CharField(max_length=50)
    description = models.TextField(max_length=255)
    offboarding_employee_id = models.ForeignKey(
        OffboardingEmployee, on_delete=models.CASCADE
    )
    attachments = models.ManyToManyField(OffboardingStageMultipleFile)


class OffboardingNote(HorillaModel):
    """
    OffboardingNote
    """

    attachments = models.ManyToManyField(
        OffboardingStageMultipleFile, blank=True, editable=False
    )
    description = models.TextField(null=True, blank=True, max_length=255)
    note_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, editable=False
    )
    employee_id = models.ForeignKey(
        OffboardingEmployee, on_delete=models.CASCADE, null=True, editable=False
    )
    stage_id = models.ForeignKey(
        OffboardingStage, on_delete=models.PROTECT, null=True, editable=False
    )

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if request:
            updated_by = request.user.employee_get
            self.note_by = updated_by
        if self.employee_id:
            self.stage_id = self.employee_id.stage_id
        return super().save(*args, **kwargs)


class OffboardingGeneralSetting(HorillaModel):
    """
    OffboardingGeneralSettings
    """

    resignation_request = models.BooleanField(default=False)
    company_id = models.ForeignKey(Company, on_delete=models.CASCADE, null=True)
    objects = HorillaCompanyManager("company_id")
