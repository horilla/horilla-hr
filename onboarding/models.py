"""
models.py

This module is used to register models for onboarding app

"""

from ast import literal_eval
from datetime import datetime
from urllib.parse import urlencode

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from employee.models import Employee
from horilla.models import HorillaModel
from horilla_audit.models import HorillaAuditInfo, HorillaAuditLog
from horilla_views.cbv_methods import render_template
from recruitment.models import Candidate, Recruitment


class OnboardingStage(HorillaModel):
    """
    OnboardingStage models
    """

    stage_title = models.CharField(max_length=200, verbose_name=_("Stage Title"))
    recruitment_id = models.ForeignKey(
        Recruitment,
        verbose_name=_("Recruitment"),
        null=True,
        related_name="onboarding_stage",
        on_delete=models.CASCADE,
    )
    employee_id = models.ManyToManyField(Employee, verbose_name=_("Stage Managers"))
    sequence = models.IntegerField(null=True)
    is_final_stage = models.BooleanField(
        default=False, verbose_name=_("Is Final Stage")
    )
    objects = HorillaCompanyManager("recruitment_id__company_id")

    def __str__(self):
        return f"{self.stage_title}"

    class Meta:
        """
        Meta class for additional options
        """

        verbose_name = _("Onboarding Stage")
        verbose_name_plural = _("Onboarding Stages")
        ordering = ["sequence"]


@receiver(post_save, sender=Recruitment)
def create_initial_stage(sender, instance, created, **kwargs):
    """
    This is post save method, used to create initial stage for the recruitment
    """
    if created or not instance.onboarding_stage.first():
        initial_stage = OnboardingStage()
        initial_stage.sequence = 0
        initial_stage.stage_title = "Initial"
        initial_stage.recruitment_id = instance
        initial_stage.save()


class OnboardingTask(HorillaModel):
    """
    OnboardingTask models
    """

    task_title = models.CharField(max_length=200, verbose_name=_("Task Title"))
    # recruitment_id = models.ManyToManyField(Recruitment, related_name="onboarding_task")
    stage_id = models.ForeignKey(
        OnboardingStage,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="onboarding_task",
    )
    candidates = models.ManyToManyField(
        Candidate,
        blank=True,
        related_name="cand_onboarding_task",
        verbose_name=_("Candidates"),
    )
    employee_id = models.ManyToManyField(
        Employee, related_name="onboarding_task", verbose_name=_("Task Managers")
    )
    is_required = models.BooleanField(
        default=False,
        verbose_name=_("Is Required"),
        help_text=_(
            "Required tasks must be completed by the candidate to move to the next stage."
        ),
    )

    objects = HorillaCompanyManager("stage_id__recruitment_id__company_id")

    def get_detail_url(self):
        """
        To get edit url
        """
        query_params = {
            "task_id": self.pk,
        }
        url = reverse("candidate-tasks-status")
        return f"{url}?{urlencode(query_params)}"

    def __str__(self):
        return f"{self.task_title}"

    class Meta:
        """
        Meta class to add some additional options
        """

        verbose_name = _("Onboarding Task")
        verbose_name_plural = _("Onboarding Tasks")


class OnboardingCandidate(Candidate):

    def get_detail_url_pipeline(self):
        """
        Get detail url pipeline
        """
        return reverse("onboarding-cand-detail-view", kwargs={"pk": self.pk})

    class Meta:
        proxy = True
        verbose_name = _("Onboarding Candidate")
        verbose_name_plural = _("Onboarding Candidates")
        app_label = "onboarding"


class CandidateStage(HorillaModel):
    """
    CandidateStage model
    """

    candidate_id = models.OneToOneField(
        Candidate, on_delete=models.PROTECT, related_name="onboarding_stage"
    )
    onboarding_stage_id = models.ForeignKey(
        OnboardingStage,
        on_delete=models.PROTECT,
        related_name="candidate",
        verbose_name=_("Stage"),
    )
    onboarding_end_date = models.DateField(blank=True, null=True)
    sequence = models.IntegerField(null=True, default=0)
    objects = HorillaCompanyManager("candidate_id__recruitment_id__company_id")

    def __str__(self):
        return f"{self.candidate_id}  |  {self.onboarding_stage_id}"

    def save(self, *args, **kwargs):
        if self.onboarding_stage_id.is_final_stage:
            self.onboarding_end_date = datetime.today()
        super(CandidateStage, self).save(*args, **kwargs)

    def task_completion_ratio(self):
        """
        function that used for getting the numbers between task completed v/s tasks assigned
        """
        cans_tasks = self.candidate_id.candidate_task
        completed_tasks = cans_tasks.filter(status="done")
        return f"{completed_tasks.count()}/{cans_tasks.count()}"

    def pending_required_tasks(self, stage=None):
        """
        Required onboarding tasks assigned to this candidate in ``stage``
        (defaults to the candidate's current stage) that are not yet done.
        """
        stage = stage or self.onboarding_stage_id
        completed_task_ids = CandidateTask.objects.filter(
            candidate_id=self.candidate_id,
            stage_id=stage,
            status="done",
        ).values_list("onboarding_task_id", flat=True)
        return OnboardingTask.objects.filter(
            stage_id=stage,
            is_required=True,
            candidates=self.candidate_id,
        ).exclude(id__in=completed_task_ids)

    def __getattribute__(self, name):
        if name.startswith("get_") and name.endswith("_task"):
            task_id = literal_eval(name[4:-5])
            task = CandidateTask.objects.filter(
                onboarding_task_id__id=task_id,
                candidate_id=self.candidate_id,
                stage_id=self.onboarding_stage_id,
            ).first()

            return render_template(
                "cbv/pipeline/onboarding/tasks.html",
                {"instance": self, "task": task, "task_id": task_id},
            )
        value = super().__getattribute__(name)

        return value

    class Meta:
        """
        Meta class for additional options
        """

        verbose_name = _("Candidate Onboarding Stage")
        ordering = ["sequence"]


class CandidateTask(HorillaModel):
    """
    CandidateTask model
    """

    choice = (
        ("todo", _("Todo")),
        ("scheduled", _("Scheduled")),
        ("ongoing", _("Ongoing")),
        ("stuck", _("Stuck")),
        ("done", _("Done")),
    )
    candidate_id = models.ForeignKey(
        Candidate, on_delete=models.PROTECT, related_name="candidate_task"
    )
    # managers = models.ManyToManyField(Employee)
    stage_id = models.ForeignKey(
        OnboardingStage,
        null=True,
        on_delete=models.PROTECT,
        related_name="candidate_task",
    )
    status = models.CharField(
        max_length=50, choices=choice, blank=True, null=True, default="todo"
    )
    onboarding_task_id = models.ForeignKey(OnboardingTask, on_delete=models.PROTECT)
    objects = HorillaCompanyManager("candidate_id__recruitment_id__company_id")
    history = HorillaAuditLog(
        related_name="history_set",
        bases=[
            HorillaAuditInfo,
        ],
    )

    def __str__(self):
        return f"{self.candidate_id}|{self.onboarding_task_id}"

    def status_col(self):
        """
        This method for get custom column for status.
        """

        return render_template(
            path="cbv/dashboard/status.html",
            context={"instance": self},
        )

    class Meta:
        """
        Meta class to add some additional options
        """

        verbose_name = _("Onboarding Task")
        verbose_name_plural = _("Onboarding Tasks")


class OnboardingPortal(HorillaModel):
    """
    OnboardingPortal model
    """

    candidate_id = models.OneToOneField(
        Candidate, on_delete=models.PROTECT, related_name="onboarding_portal"
    )
    token = models.CharField(max_length=200)
    used = models.BooleanField(default=False)
    count = models.IntegerField(default=0)
    profile = models.ImageField(upload_to="employee/profile", null=True, blank=True)
    objects = HorillaCompanyManager("candidate_id__recruitment_id__company_id")

    def __str__(self):
        return str(self.candidate_id)
