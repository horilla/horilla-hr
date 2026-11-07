"""Forms of the surveys app; widgets are styled by base.forms.ModelForm."""

from django import forms
from django.utils.translation import gettext_lazy as _

from base.forms import ModelForm
from surveys.models import Survey, SurveyQuestion


class SurveyForm(ModelForm):
    verbose_name = _("Survey")
    cols = {
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

    def clean(self):
        cleaned = super().clean()
        audience = cleaned.get("audience")
        chosen = {
            Survey.AUDIENCE_DEPARTMENTS: cleaned.get("departments"),
            Survey.AUDIENCE_POSITIONS: cleaned.get("job_positions"),
            Survey.AUDIENCE_EMPLOYEES: cleaned.get("employees"),
        }
        if audience in chosen and not chosen[audience]:
            self.add_error(
                {
                    Survey.AUDIENCE_DEPARTMENTS: "departments",
                    Survey.AUDIENCE_POSITIONS: "job_positions",
                    Survey.AUDIENCE_EMPLOYEES: "employees",
                }[audience],
                _("Choose at least one for this audience."),
            )
        return cleaned


class SurveyQuestionForm(ModelForm):
    """One question; the options of a choice question come as lines in a textarea."""

    verbose_name = _("Question")
    options_text = forms.CharField(
        required=False,
        label=_("Options"),
        help_text=_("One option per line - for single and multiple choice."),
        widget=forms.Textarea(attrs={"rows": 4, "class": "oh-input w-100"}),
    )
    cols = {"question": 12, "type": 6, "is_required": 6, "options_text": 12}

    class Meta:
        model = SurveyQuestion
        fields = ["question", "type", "is_required"]
        widgets = {"question": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
