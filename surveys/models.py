"""Employee surveys.

An HR-run survey: a questionnaire built in a constructor, sent to an audience
(everyone, departments, job positions or chosen employees), answered through a
personal link that needs no login, with the answers charted per question.

Two things shape the models:

* **Anonymity that still tells HR who has answered.** Each recipient gets a
  SurveyInvitation with a token; the response is tied to the invitation only
  while it is a draft, so the person can come back to it. Submitting an
  anonymous survey cuts that link inside the same transaction and marks the
  invitation submitted. From then on the invitation says "answered" and the
  response says nothing about whom it came from.

* **Drafts.** Answers are saved as they are typed; a half-finished response is
  a SurveyResponse with is_draft=True, reopened by the same link.
"""

import secrets

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company, Department, JobPosition
from employee.models import Employee
from horilla.models import HorillaModel

TOKEN_BYTES = 32  # 43 url-safe characters


class Survey(HorillaModel):
    """A questionnaire and whom it goes to."""

    STATUS_DRAFT, STATUS_OPEN, STATUS_CLOSED = "draft", "open", "closed"
    STATUSES = [
        (STATUS_DRAFT, _("Draft")),
        (STATUS_OPEN, _("Open")),
        (STATUS_CLOSED, _("Closed")),
    ]
    AUDIENCE_ALL, AUDIENCE_DEPARTMENTS, AUDIENCE_POSITIONS, AUDIENCE_EMPLOYEES = (
        "all",
        "departments",
        "positions",
        "employees",
    )
    AUDIENCES = [
        (AUDIENCE_ALL, _("All employees")),
        (AUDIENCE_DEPARTMENTS, _("Departments")),
        (AUDIENCE_POSITIONS, _("Job positions")),
        (AUDIENCE_EMPLOYEES, _("Selected employees")),
    ]

    title = models.CharField(max_length=150, verbose_name=_("Title"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    is_anonymous = models.BooleanField(
        default=True,
        verbose_name=_("Anonymous"),
        help_text=_(
            "Answers are stored without the employee; only who has answered is kept."
        ),
    )
    status = models.CharField(
        max_length=10, choices=STATUSES, default=STATUS_DRAFT, verbose_name=_("Status")
    )
    opens_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Opens at"))
    closes_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Closes at"))
    audience = models.CharField(
        max_length=20,
        choices=AUDIENCES,
        default=AUDIENCE_ALL,
        verbose_name=_("Audience"),
    )
    departments = models.ManyToManyField(
        Department, blank=True, verbose_name=_("Departments")
    )
    job_positions = models.ManyToManyField(
        JobPosition, blank=True, verbose_name=_("Job positions")
    )
    employees = models.ManyToManyField(
        Employee,
        blank=True,
        related_name="surveys_invited_to",
        verbose_name=_("Employees"),
    )
    managers = models.ManyToManyField(
        Employee,
        blank=True,
        related_name="surveys_managed",
        verbose_name=_("Managers"),
        help_text=_(
            "See the results and send reminders without the global permission."
        ),
    )
    company_id = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Company"),
    )

    objects = HorillaCompanyManager("company_id")

    class Meta:
        verbose_name = _("Survey")
        verbose_name_plural = _("Surveys")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            raise ValidationError(
                {"closes_at": _("The survey must close after it opens.")}
            )

    # --- state -------------------------------------------------------------

    def is_accepting(self, now=None):
        """Whether an answer may be submitted right now."""
        now = now or timezone.now()
        if self.status != self.STATUS_OPEN:
            return False
        if self.opens_at and now < self.opens_at:
            return False
        if self.closes_at and now > self.closes_at:
            return False
        return True

    # --- audience ----------------------------------------------------------

    def audience_employees(self):
        """The active employees the survey goes to, by its audience rule."""
        base = Employee.objects.filter(is_active=True)
        if self.audience == self.AUDIENCE_DEPARTMENTS:
            return base.filter(
                employee_work_info__department_id__in=self.departments.all()
            )
        if self.audience == self.AUDIENCE_POSITIONS:
            return base.filter(
                employee_work_info__job_position_id__in=self.job_positions.all()
            )
        if self.audience == self.AUDIENCE_EMPLOYEES:
            return base.filter(pk__in=self.employees.all())
        return base

    def invite(self):
        """Create the missing invitations for the current audience.

        Returns the new ones.
        """
        existing = set(self.invitations.values_list("employee_id", flat=True))
        new = [
            SurveyInvitation(
                survey=self, employee=employee, token=SurveyInvitation.new_token()
            )
            for employee in self.audience_employees().exclude(pk__in=existing)
        ]
        return SurveyInvitation.objects.bulk_create(new)

    # --- for the list and the detail page -----------------------------------

    def get_detail_url(self):
        from django.urls import reverse

        return reverse("survey-detail", args=[self.pk])

    def status_badge(self):
        """The status as a pill, inline-styled like the other modules' badges."""
        colour = {
            self.STATUS_DRAFT: "#808080",
            self.STATUS_OPEN: "#3b82f6",
            self.STATUS_CLOSED: "#ef4444",
        }[self.status]
        return (
            f'<span style="background-color:{colour};color:#fff;padding:3px 10px;'
            f'border-radius:999px;font-size:.8rem;font-weight:600;white-space:nowrap">'
            f"{self.get_status_display()}</span>"
        )

    def audience_label(self):
        if self.audience == self.AUDIENCE_DEPARTMENTS:
            return (
                ", ".join(str(d) for d in self.departments.all())
                or self.get_audience_display()
            )
        if self.audience == self.AUDIENCE_POSITIONS:
            return (
                ", ".join(p.job_position for p in self.job_positions.all())
                or self.get_audience_display()
            )
        if self.audience == self.AUDIENCE_EMPLOYEES:
            return str(self.employees.count()) + " " + str(_("employees"))
        return self.get_audience_display()

    def invited_count(self):
        return self.invitations.count()

    def answered_count(self):
        return self.invitations.filter(status=SurveyInvitation.STATUS_SUBMITTED).count()

    def answered_label(self):
        total = self.invited_count()
        return (
            f"{self.answered_count()} / {total} ({self.response_rate()}%)"
            if total
            else "—"
        )

    def closes_label(self):
        from django.utils import formats

        return (
            formats.date_format(timezone.localtime(self.closes_at), "SHORT_DATE_FORMAT")
            if self.closes_at
            else "—"
        )

    def row_actions(self):
        from django.template.loader import render_to_string

        return render_to_string("surveys/row_actions.html", {"survey": self})

    # --- numbers -----------------------------------------------------------

    def response_rate(self):
        total = self.invitations.count()
        if not total:
            return 0
        return round(
            100
            * self.invitations.filter(status=SurveyInvitation.STATUS_SUBMITTED).count()
            / total
        )


class SurveyQuestion(HorillaModel):
    """One question of a survey; the options of a choice question are a list."""

    TYPE_TEXT, TYPE_TEXTAREA, TYPE_CHOICE, TYPE_MULTIPLE = (
        "text",
        "textarea",
        "choice",
        "multiple",
    )
    TYPE_RATING, TYPE_LIKERT, TYPE_YES_NO, TYPE_NUMBER, TYPE_DATE = (
        "rating",
        "likert",
        "yes_no",
        "number",
        "date",
    )
    TYPES = [
        (TYPE_TEXT, _("Short text")),
        (TYPE_TEXTAREA, _("Long text")),
        (TYPE_CHOICE, _("Single choice")),
        (TYPE_MULTIPLE, _("Multiple choice")),
        (TYPE_RATING, _("Rating 1–5")),
        (TYPE_LIKERT, _("Agreement scale")),
        (TYPE_YES_NO, _("Yes / No")),
        (TYPE_NUMBER, _("Number")),
        (TYPE_DATE, _("Date")),
    ]
    CHOICE_TYPES = (TYPE_CHOICE, TYPE_MULTIPLE)
    LIKERT = [
        ("1", _("Strongly disagree")),
        ("2", _("Disagree")),
        ("3", _("Neutral")),
        ("4", _("Agree")),
        ("5", _("Strongly agree")),
    ]
    RATING_MAX = 5

    survey = models.ForeignKey(
        Survey, on_delete=models.CASCADE, related_name="questions"
    )
    sequence = models.PositiveIntegerField(default=0, verbose_name=_("Order"))
    type = models.CharField(
        max_length=10, choices=TYPES, default=TYPE_CHOICE, verbose_name=_("Type")
    )
    question = models.TextField(verbose_name=_("Question"))
    options = models.JSONField(default=list, blank=True, verbose_name=_("Options"))
    is_required = models.BooleanField(default=False, verbose_name=_("Required"))

    objects = HorillaCompanyManager("survey__company_id")

    class Meta:
        verbose_name = _("Survey question")
        verbose_name_plural = _("Survey questions")
        ordering = ["sequence", "id"]

    def __str__(self):
        return self.question[:80]

    def clean(self):
        super().clean()
        if self.type in self.CHOICE_TYPES:
            options = [str(o).strip() for o in (self.options or []) if str(o).strip()]
            if len(options) < 2:
                raise ValidationError({"options": _("Give at least two options.")})
            if len(set(options)) != len(options):
                raise ValidationError({"options": _("Options must differ.")})
            self.options = options
        else:
            self.options = []

    def choices(self):
        if self.type in self.CHOICE_TYPES:
            return [(o, o) for o in self.options]
        if self.type == self.TYPE_LIKERT:
            return list(self.LIKERT)
        if self.type == self.TYPE_YES_NO:
            return [("yes", _("Yes")), ("no", _("No"))]
        if self.type == self.TYPE_RATING:
            return [(str(i), str(i)) for i in range(1, self.RATING_MAX + 1)]
        return []

    def charted(self):
        """Whether the answers are counted into a chart (vs. listed)."""
        return self.type not in (self.TYPE_TEXT, self.TYPE_TEXTAREA, self.TYPE_DATE)


class SurveyInvitation(HorillaModel):
    """One employee's personal link, and whether they have answered."""

    STATUS_INVITED, STATUS_STARTED, STATUS_SUBMITTED = "invited", "started", "submitted"
    STATUSES = [
        (STATUS_INVITED, _("Invited")),
        (STATUS_STARTED, _("Started")),
        (STATUS_SUBMITTED, _("Submitted")),
    ]

    survey = models.ForeignKey(
        Survey, on_delete=models.CASCADE, related_name="invitations"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="survey_invitations"
    )
    token = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(
        max_length=10,
        choices=STATUSES,
        default=STATUS_INVITED,
        verbose_name=_("Status"),
    )
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Sent at"))
    reminded_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Reminded at")
    )
    submitted_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Submitted at")
    )

    objects = HorillaCompanyManager("survey__company_id")

    class Meta:
        verbose_name = _("Survey invitation")
        verbose_name_plural = _("Survey invitations")
        unique_together = [("survey", "employee")]

    def __str__(self):
        return f"{self.survey} → {self.employee}"

    @staticmethod
    def new_token():
        return secrets.token_urlsafe(TOKEN_BYTES)

    def submitted(self):
        return self.status == self.STATUS_SUBMITTED


class SurveyResponse(HorillaModel):
    """A set of answers.

    A draft knows its invitation; a submitted anonymous one does not.
    """

    survey = models.ForeignKey(
        Survey, on_delete=models.CASCADE, related_name="responses"
    )
    invitation = models.OneToOneField(
        SurveyInvitation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="response",
    )
    is_draft = models.BooleanField(default=True, verbose_name=_("Draft"))
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Submitted at")
    )

    objects = HorillaCompanyManager("survey__company_id")

    class Meta:
        verbose_name = _("Survey response")
        verbose_name_plural = _("Survey responses")

    def __str__(self):
        return f"{self.survey} #{self.pk}"

    def answers_by_question(self):
        return {a.question_id: a.value for a in self.answers.all()}


class SurveyAnswer(models.Model):
    """The value given to one question: a string, a list of strings, or a number."""

    response = models.ForeignKey(
        SurveyResponse, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(
        SurveyQuestion, on_delete=models.CASCADE, related_name="answers"
    )
    value = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = [("response", "question")]

    def __str__(self):
        return f"{self.question_id}: {self.value!r}"
