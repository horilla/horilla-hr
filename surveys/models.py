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

A survey starts blank or from the library: a Questionnaire is one
kept for reuse, and a survey made from it gets a copy of its questions, which
are then changed like any others.
"""

import secrets
from datetime import datetime, time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company, Department, JobPosition
from employee.models import Employee
from horilla.models import HorillaModel, has_xss
from horilla_views.cbv_methods import render_template

TOKEN_BYTES = 32  # 43 url-safe characters


def _pill(text, colour):
    """A status as a pill, inline-styled like the other modules' badges."""
    return (
        f'<span style="background-color:{colour};color:#fff;padding:3px 10px;'
        f'border-radius:999px;font-size:.8rem;font-weight:600;white-space:nowrap">'
        f"{text}</span>"
    )


def _moment(value, with_time=True):
    """A date and time of the audience list, in the local zone.

    Written the way the survey page writes "closes ...": the locale's short
    format ("11/12/2026 11:35 a.m.") does not fit the column.
    """
    from django.utils import formats

    if not value:
        return "—"
    return formats.date_format(
        timezone.localtime(value), "d.m.Y H:i" if with_time else "d.m.Y"
    )


def local_midnight(moment):
    """The start of the local day of `moment`: all an anonymous response keeps."""
    return timezone.localtime(moment).replace(hour=0, minute=0, second=0, microsecond=0)


def local_midnight_of(day):
    """The start of the local date `day`, as an aware datetime."""
    return timezone.make_aware(datetime.combine(day, time.min))


def with_counts(queryset):
    """Surveys with their invited and answered numbers, counted in the same query.

    The lists and the dashboard show both for every row; asked of each survey
    they are two queries per row.
    """
    return queryset.annotate(
        n_invited=Count("invitations", distinct=True),
        n_answered=Count(
            "invitations",
            filter=Q(invitations__status="submitted"),
            distinct=True,
        ),
    )


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
            "Answers are stored without the employee; HR sees who has answered, "
            "not what they answered. Results appear once the survey is closed."
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
            "Can see this survey, its audience and results, export the results "
            "and send reminders. They cannot change the survey or its questions."
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
        if self.pk:
            stored = (
                Survey._base_manager.filter(pk=self.pk)
                .values_list("is_anonymous", "status")
                .first()
            )
            if (
                stored
                and stored[1] != self.STATUS_DRAFT
                and stored[0] != self.is_anonymous
            ):
                raise ValidationError(
                    {
                        "is_anonymous": _(
                            "Anonymity is fixed once the survey has been opened."
                        )
                    }
                )

    # --- state -------------------------------------------------------------

    AVAILABLE, NOT_OPEN, SCHEDULED, CLOSED, ENDED = (
        "available",
        "not_open",
        "scheduled",
        "closed",
        "ended",
    )

    def availability(self, now=None):
        """What an employee meets at the link: answerable, or why not."""
        now = now or timezone.now()
        if self.status == self.STATUS_DRAFT:
            return self.NOT_OPEN
        if self.status == self.STATUS_CLOSED:
            return self.CLOSED
        if self.closes_at and now > self.closes_at:
            return self.ENDED
        if self.opens_at and now < self.opens_at:
            return self.SCHEDULED
        return self.AVAILABLE

    def is_accepting(self, now=None):
        """Whether an answer may be submitted right now."""
        return self.availability(now) == self.AVAILABLE

    def is_ended(self, now=None):
        """Open on paper, but past its closing time."""
        return self.availability(now) == self.ENDED

    def shown_status(self):
        """The status as a person should read it: a survey past its end is closed."""
        return self.STATUS_CLOSED if self.is_ended() else self.status

    @classmethod
    def close_ended(cls):
        """Close the surveys whose closing time has passed; returns how many.

        Run when the lists and the dashboard load, so a survey past its end is
        closed in the database too (filters, counts, the audience list) and an
        anonymous one gets its unfinished drafts dropped like on a manual close.
        """
        ended = list(
            cls._base_manager.filter(
                status=cls.STATUS_OPEN, closes_at__lt=timezone.now()
            )
        )
        for survey in ended:
            survey.drop_anonymous_drafts()
            cls._base_manager.filter(pk=survey.pk, status=cls.STATUS_OPEN).update(
                status=cls.STATUS_CLOSED
            )
        return len(ended)

    # --- what an anonymous survey may show -----------------------------------

    def min_responses(self):
        """How many people must have answered before results and export show.

        Only anonymous surveys wait: with fewer answers than this, one answer
        points at its author. SURVEYS_MIN_RESPONSES changes it (default 5).
        Even then they show only once the survey is closed (see results_hold).
        """
        if not self.is_anonymous:
            return 0
        return max(0, int(getattr(settings, "SURVEYS_MIN_RESPONSES", 5)))

    def submitted_count(self):
        return SurveyResponse._base_manager.filter(survey=self, is_draft=False).count()

    HOLD_UNTIL_CLOSED = "until_closed"
    HOLD_TOO_FEW = "too_few"

    def results_hold(self):
        """Why results and export are not shown yet, or "" when they are.

        An anonymous survey shows nothing while it is open: two looks at the
        results, before and after one person answers, would give that answer
        away. Once it is closed nothing can change, so the results appear, but
        only when enough people answered for no answer to point at its author.
        """
        if not self.is_anonymous:
            return ""
        if self.status == self.STATUS_OPEN:
            return self.HOLD_UNTIL_CLOSED
        if 0 < self.submitted_count() < self.min_responses():
            return self.HOLD_TOO_FEW
        return ""

    def results_withheld(self):
        return bool(self.results_hold())

    def drop_anonymous_drafts(self):
        """Delete the unfinished drafts of an anonymous survey; returns how many.

        A draft still knows its invitation, so it is the one place where an
        anonymous answer is tied to a person. It is not part of any result.
        """
        if not self.is_anonymous:
            return 0
        drafts = SurveyResponse._base_manager.filter(survey=self, is_draft=True)
        invitation_ids = [
            i for i in drafts.values_list("invitation_id", flat=True) if i
        ]
        count = drafts.count()
        drafts.delete()
        SurveyInvitation._base_manager.filter(
            pk__in=invitation_ids, status=SurveyInvitation.STATUS_STARTED
        ).update(status=SurveyInvitation.STATUS_INVITED)
        return count

    # --- audience ----------------------------------------------------------

    def audience_employees(self):
        """The active employees the survey goes to, by its audience rule."""
        # The survey's own company, not the one the admin happens to have selected
        # in Horilla: that is what Employee.objects would filter by
        base = Employee._base_manager.filter(is_active=True)
        if self.company_id_id:
            base = base.filter(employee_work_info__company_id=self.company_id_id)
        if self.audience == self.AUDIENCE_DEPARTMENTS:
            return base.filter(
                employee_work_info__department_id__in=Department._base_manager.filter(
                    survey=self
                )
            )
        if self.audience == self.AUDIENCE_POSITIONS:
            return base.filter(
                employee_work_info__job_position_id__in=JobPosition._base_manager.filter(
                    survey=self
                )
            )
        if self.audience == self.AUDIENCE_EMPLOYEES:
            return base.filter(surveys_invited_to=self)
        return base

    def invite(self):
        """Create the missing invitations for the current audience.

        Returns the new ones.
        """
        existing = set(
            SurveyInvitation._base_manager.filter(survey=self).values_list(
                "employee_id", flat=True
            )
        )
        new = [
            SurveyInvitation(
                survey=self, employee=employee, token=SurveyInvitation.new_token()
            )
            for employee in self.audience_employees().exclude(pk__in=existing)
        ]
        return SurveyInvitation.objects.bulk_create(new)

    def has_answers(self):
        return self.submitted_count() > 0

    # --- for the list and the detail page -----------------------------------

    def get_detail_url(self):
        return reverse("survey-detail", args=[self.pk])

    def get_update_url(self):
        return reverse("survey-edit", args=[self.pk])

    def get_delete_url(self):
        return f"{reverse('generic-delete')}?model=surveys.Survey&pk={self.pk}"

    def status_badge(self):
        """The status as a pill, inline-styled like the other modules' badges."""
        colour = {
            self.STATUS_DRAFT: "#808080",
            self.STATUS_OPEN: "#3b82f6",
            self.STATUS_CLOSED: "#ef4444",
        }[self.shown_status()]
        label = dict(self.STATUSES)[self.shown_status()]
        return _pill(label, colour)

    def title_display(self):
        """The title for the list and the cards, which print what they are given."""
        return format_html("{}", self.title)

    def audience_label(self):
        # Department and position names are typed by people: escaped here, as
        # the list and the cards print the label as it is
        if self.audience == self.AUDIENCE_DEPARTMENTS:
            text = (
                ", ".join(str(d) for d in self.departments.all())
                or self.get_audience_display()
            )
        elif self.audience == self.AUDIENCE_POSITIONS:
            text = (
                ", ".join(p.job_position for p in self.job_positions.all())
                or self.get_audience_display()
            )
        elif self.audience == self.AUDIENCE_EMPLOYEES:
            text = str(self.employees.count()) + " " + str(_("employees"))
        else:
            text = self.get_audience_display()
        return format_html("{}", text)

    def invited_count(self):
        if hasattr(self, "n_invited"):  # from with_counts()
            return self.n_invited
        return self.invitations.count()

    def answered_count(self):
        if hasattr(self, "n_answered"):
            return self.n_answered
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
            formats.date_format(timezone.localtime(self.closes_at), "d.m.Y")
            if self.closes_at
            else "—"
        )

    def row_actions(self):
        # render_template, not render_to_string: the buttons depend on perms,
        # which only a context made with the request carries
        return render_template("surveys/row_actions.html", {"survey": self})

    # --- numbers -----------------------------------------------------------

    def response_rate(self):
        total = self.invited_count()
        if not total:
            return 0
        return round(100 * self.answered_count() / total)


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
    TYPE_NPS = "nps"
    TYPES = [
        (TYPE_TEXT, _("Short text")),
        (TYPE_TEXTAREA, _("Long text")),
        (TYPE_CHOICE, _("Single choice")),
        (TYPE_MULTIPLE, _("Multiple choice")),
        (TYPE_RATING, _("Rating 1–5")),
        (TYPE_NPS, _("Scale 0–10 (NPS)")),
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
    NPS_MAX = 10
    # Net Promoter Score: 9-10 promote, 0-6 detract
    NPS_PROMOTER_FROM, NPS_DETRACTOR_TILL = 9, 6

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
                raise ValidationError(
                    {
                        "options": _(
                            "A choice question needs at least two options, "
                            "one per line."
                        )
                    }
                )
            if len(set(options)) != len(options):
                raise ValidationError({"options": _("Options must differ.")})
            if any(has_xss(option) for option in options):
                # options are JSON, so the text-field check never sees them
                raise ValidationError(
                    {"options": _("Options cannot contain markup or scripts.")}
                )
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
        if self.type == self.TYPE_NPS:
            return [(str(i), str(i)) for i in range(0, self.NPS_MAX + 1)]
        return []

    def answered_options(self):
        """The options that at least one answer has chosen."""
        chosen = set()
        for value in self.answers.values_list("value", flat=True):
            for item in value if isinstance(value, list) else [value]:
                if item not in (None, ""):
                    chosen.add(str(item))
        return chosen & set(self.options or [])

    def charted(self):
        """Whether the answers are counted into a chart (vs. listed)."""
        return self.type not in (self.TYPE_TEXT, self.TYPE_TEXTAREA, self.TYPE_DATE)


class Questionnaire(HorillaModel):
    """A questionnaire of the library; a survey made from it copies the questions."""

    title = models.CharField(max_length=150, verbose_name=_("Title"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    is_anonymous = models.BooleanField(
        default=True,
        verbose_name=_("Anonymous"),
        help_text=_("What a survey made from this questionnaire starts with."),
    )
    # [{"type", "question", "options", "is_required"}], in the order asked
    questions = models.JSONField(default=list, blank=True, verbose_name=_("Questions"))
    # Set on the standard questionnaires, so loading them again adds no copies
    code = models.CharField(max_length=50, blank=True, editable=False)
    company_id = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Company"),
    )

    objects = HorillaCompanyManager("company_id")

    class Meta:
        verbose_name = _("Questionnaire")
        verbose_name_plural = _("Questionnaires")
        ordering = ["title"]
        constraints = [
            # loading the standard questionnaires twice at once must not add copies
            models.UniqueConstraint(
                fields=["code"],
                condition=~models.Q(code=""),
                name="surveys_questionnaire_unique_code",
            )
        ]

    def __str__(self):
        return self.title

    @staticmethod
    def questions_of(survey):
        """The questions of a survey as a questionnaire keeps them."""
        return [
            {
                "type": q.type,
                "question": q.question,
                "options": list(q.options or []),
                "is_required": q.is_required,
            }
            for q in survey.questions.all()
        ]

    def build_questions(self):
        """Unsaved SurveyQuestions of this questionnaire, checked, in order."""
        built = []
        for sequence, item in enumerate(self.questions or [], start=1):
            question = SurveyQuestion(
                sequence=sequence,
                type=item.get("type"),
                question=item.get("question", ""),
                options=list(item.get("options") or []),
                is_required=bool(item.get("is_required")),
            )
            question.clean_fields(exclude=["survey"])
            question.clean()
            built.append(question)
        return built

    def clean(self):
        super().clean()
        try:
            self.build_questions()
        except ValidationError as error:
            raise ValidationError({"questions": error.messages}) from None

    def copy_questions_to(self, survey):
        """Give `survey` this questionnaire's questions, after any it has."""
        last = (
            survey.questions.order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
        ) or 0
        questions = self.build_questions()
        for question in questions:
            question.survey = survey
            question.sequence += last
        return SurveyQuestion.objects.bulk_create(questions)

    def question_rows(self):
        """For the library page: each question with its type as a person reads it."""
        return [
            {
                "question": q.question,
                "type": q.get_type_display(),
                "options": q.options,
                "is_required": q.is_required,
            }
            for q in self.build_questions()
        ]

    def question_count(self):
        return len(self.questions or [])

    def title_display(self):
        """The title for the library's list and cards, which print what they get."""
        return format_html("{}", self.title)

    # --- for the library's cards, list and detail ------------------------------

    def question_count_label(self):
        count = self.question_count()
        return ngettext("%(count)s question", "%(count)s questions", count) % {
            "count": count
        }

    def anonymity_label(self):
        return _("Anonymous") if self.is_anonymous else _("Not anonymous")

    def get_detail_url(self):
        return reverse("questionnaire-detail", args=[self.pk])

    def get_update_url(self):
        return reverse("questionnaire-edit", args=[self.pk])

    def get_use_url(self):
        """The create form of a survey, filled in from this questionnaire."""
        return f"{reverse('survey-create')}?questionnaire={self.pk}"

    def get_delete_url(self):
        return f"{reverse('generic-delete')}?model=surveys.Questionnaire&pk={self.pk}"

    def questions_html(self):
        return render_template(
            "surveys/library/questions.html", {"questionnaire": self}
        )

    def row_actions(self):
        return render_template(
            "surveys/library/row_actions.html", {"questionnaire": self}
        )

    def detail_actions(self):
        return render_template(
            "surveys/library/detail_actions.html", {"questionnaire": self}
        )


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

    def person_is_active(self):
        """False once the employee, or the login that goes with them, is switched off.

        A link kept from before somebody left must not keep working.
        """
        employee = self.employee
        if not employee.is_active:
            return False
        user = employee.employee_user_id
        return user is None or user.is_active

    # --- for the audience list -------------------------------------------------

    def status_badge(self):
        colour = {
            self.STATUS_INVITED: "#808080",
            self.STATUS_STARTED: "#f59e0b",
            self.STATUS_SUBMITTED: "#22c55e",
        }[self.status]
        return _pill(self.get_status_display(), colour)

    def department_label(self):
        return format_html("{}", str(self.employee.get_department() or "—"))

    def sent_label(self):
        return _moment(self.sent_at)

    def reminded_label(self):
        return _moment(self.reminded_at)

    def submitted_label(self):
        # an anonymous survey keeps the day only, whatever the list shows
        return _moment(self.submitted_at, with_time=not self.survey.is_anonymous)

    def row_actions(self):
        return render_template("surveys/invitation_actions.html", {"invitation": self})


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

    @classmethod
    def start(cls, survey, invitation):
        """A new draft for `invitation`, written without Horilla's user stamp.

        HorillaModel.save() records the logged-in user as created_by. An
        employee who answers with a Horilla session open would otherwise be
        written onto the response of an anonymous survey, so drafts are
        inserted without going through save().
        """
        response = cls(survey=survey, invitation=invitation)
        cls._base_manager.bulk_create([response])
        if response.pk is None:  # a database that does not return the new key
            response = cls._base_manager.get(invitation=invitation)
        return response

    @classmethod
    def finish(cls, response, invitation, *, anonymous, now):
        """Close a draft; returns the moment recorded for the submission.

        An anonymous response is cut loose from its invitation here and keeps
        no user and no time of day, only the date: the exact moment and the
        creation stamp would otherwise match it to the audience list.
        """
        if anonymous:
            day = local_midnight(now)
            cls._base_manager.filter(pk=response.pk).update(
                is_draft=False,
                invitation=None,
                created_by=None,
                modified_by=None,
                created_at=day,
                started_at=day,
                submitted_at=day,
            )
            return day
        cls._base_manager.filter(pk=response.pk).update(
            is_draft=False, invitation=invitation, submitted_at=now
        )
        return now

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
