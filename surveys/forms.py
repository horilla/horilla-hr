"""Forms of the surveys app; widgets are styled by base.forms.ModelForm."""

from django import forms
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from surveys.models import Questionnaire, Survey, SurveyQuestion


class SurveyForm(ModelForm):
    verbose_name = _("Survey")
    # A new survey starts blank or from a questionnaire of the library. "Blank"
    # is a value of its own: Horilla's selects disable the empty option
    BLANK = "blank"
    questionnaire = forms.ChoiceField(
        required=False,
        initial=BLANK,
        label=_("Start from"),
        help_text=_(
            "A questionnaire of the library gives the survey its questions; "
            "they can be changed afterwards."
        ),
    )
    field_order = ["questionnaire"]
    cols = {
        "questionnaire": 12,
        "title": 12,
        "description": 12,
        "is_anonymous": 6,
        "audience": 6,
        "departments": 12,
        "job_positions": 12,
        "employees": 12,
        "managers": 12,
        "opens_at": 6,
        "closes_at": 6,
    }

    class Meta:
        model = Survey
        fields = [
            "title",
            "description",
            "is_anonymous",
            "audience",
            "departments",
            "job_positions",
            "employees",
            "managers",
            "opens_at",
            "closes_at",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "opens_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "closes_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        library = [(str(q.pk), q.title) for q in Questionnaire.objects.all()]
        if self.instance.pk or not library:
            del self.fields["questionnaire"]
        else:
            self.fields["questionnaire"].choices = [
                (self.BLANK, _("Blank survey"))
            ] + library
        if self.instance.pk and self.instance.status != Survey.STATUS_DRAFT:
            # People were told "anonymous" or "named" when they were invited; a
            # disabled field ignores what is posted and keeps the stored value
            anonymous = self.fields["is_anonymous"]
            anonymous.disabled = True
            anonymous.help_text = _("Fixed once the survey has been opened.")

    def clean_questionnaire(self):
        value = self.cleaned_data.get("questionnaire")
        if not value or value == self.BLANK:
            return None
        return Questionnaire.objects.filter(pk=value).first()

    def clean(self):
        cleaned = super().clean()
        audience = cleaned.get("audience")
        chosen = {
            Survey.AUDIENCE_DEPARTMENTS: cleaned.get("departments"),
            Survey.AUDIENCE_POSITIONS: cleaned.get("job_positions"),
            Survey.AUDIENCE_EMPLOYEES: cleaned.get("employees"),
        }
        fields = {
            Survey.AUDIENCE_DEPARTMENTS: "departments",
            Survey.AUDIENCE_POSITIONS: "job_positions",
            Survey.AUDIENCE_EMPLOYEES: "employees",
        }
        if audience in chosen and not chosen[audience]:
            self.add_error(
                fields[audience], _("Choose at least one for this audience.")
            )
        # The form shows only the field of the chosen audience: what is left in
        # the hidden ones from an earlier choice is not kept
        for key, field in fields.items():
            if key != audience and field in cleaned:
                cleaned[field] = cleaned[field].none()
        return cleaned


class SurveyQuestionForm(ModelForm):
    """One question; the options of a choice question come as lines in a textarea."""

    verbose_name = _("Question")
    options_text = forms.CharField(
        required=False,
        label=_("Options"),
        help_text=_(
            "One option per line, at least two - for single and multiple choice."
        ),
        widget=forms.Textarea(attrs={"rows": 4, "class": "oh-input w-100"}),
    )
    cols = {"question": 12, "type": 6, "is_required": 6, "options_text": 12}

    class Meta:
        model = SurveyQuestion
        fields = ["question", "type", "is_required"]
        widgets = {"question": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The help text sits behind an icon; the field itself says what to type
        self.fields["options_text"].widget.attrs["placeholder"] = _(
            "One option per line, at least two"
        )
        if self.instance.pk and self.instance.options:
            self.fields["options_text"].initial = "\n".join(self.instance.options)

    def clean(self):
        cleaned = super().clean()
        lines = [
            line.strip() for line in (cleaned.get("options_text") or "").splitlines()
        ]
        self.instance.options = [line for line in lines if line]
        self.instance.type = cleaned.get("type") or self.instance.type
        try:
            self.instance.clean()
        except forms.ValidationError as error:
            for field, messages in error.message_dict.items():
                self.add_error("options_text" if field == "options" else None, messages)
        return cleaned

    def _post_clean(self):
        # The model's clean() ran above and its "options" error was already
        # attached to options_text; Django would otherwise run it again and
        # choke on a field the form does not have
        if self.errors:
            return
        super()._post_clean()


class QuestionnaireForm(ModelForm):
    """A questionnaire of the library: what it is called and starts a survey with."""

    verbose_name = _("Questionnaire")
    cols = {"title": 12, "description": 12, "is_anonymous": 12}

    class Meta:
        model = Questionnaire
        fields = ["title", "description", "is_anonymous"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class SaveToLibraryForm(QuestionnaireForm):
    """A survey's questions kept as a questionnaire: a new one or in place of one."""

    NEW = "new"
    replace = forms.ChoiceField(
        required=False,
        initial=NEW,
        label=_("Save as"),
        help_text=_(
            "A new questionnaire, or one of the library to put this survey's "
            "questions in place of."
        ),
    )
    field_order = ["replace"]
    cols = {"replace": 12, "title": 12, "description": 12, "is_anonymous": 12}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        library = [
            (str(q.pk), _("Replace: %(title)s") % {"title": q.title})
            for q in Questionnaire.objects.all()
        ]
        if library:
            self.fields["replace"].choices = [
                (self.NEW, _("A new questionnaire"))
            ] + library
        else:
            del self.fields["replace"]

    def clean_replace(self):
        value = self.cleaned_data.get("replace")
        if not value or value == self.NEW:
            return None
        return Questionnaire.objects.filter(pk=value).first()
