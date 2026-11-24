from base.forms import ModelForm, forms
from horilla_meet.models import *
from recruitment.models import Candidate


class GoogleCloudCredentialForm(ModelForm):
    class Meta:
        model = GoogleCloudCredential
        fields = "__all__"


class GoogleMeetingForm(ModelForm):
    attendees = forms.MultipleChoiceField(choices=[], widget=forms.SelectMultiple)

    class Meta:
        model = GoogleMeeting
        fields = ["title", "description", "start_time", "duration", "attendees"]
        widgets = {
            "start_time": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control oh-input"}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        employees = [
            (emp.get_mail(), emp.get_full_name())
            for emp in Employee.objects.all()
            if emp.get_mail()
        ]
        candidates = [(cand.get_mail(), cand.name) for cand in Candidate.objects.all()]

        self.fields["attendees"].choices = [
            ("Employees", employees),
            ("Candidates", candidates),
        ]
