"""
offboarding/forms.py

This module is used to register forms for offboarding app
"""

import contextlib
import json
from datetime import date
from typing import Any

from django import forms
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

from base.forms import ModelForm
from base.methods import reload_queryset
from employee.filters import EmployeeFilter
from employee.forms import MultipleFileField
from employee.models import Employee
from horilla import horilla_middlewares
from horilla_widgets.widgets.horilla_multi_select_field import HorillaMultiSelectField
from horilla_widgets.widgets.select_widgets import HorillaMultiSelectWidget
from notifications.signals import notify
from offboarding.models import (
    EmployeeTask,
    Offboarding,
    OffboardingEmployee,
    OffboardingNote,
    OffboardingStage,
    OffboardingStageMultipleFile,
    OffboardingTask,
    ResignationComment,
    ResignationLetter,
)

# Stages a new offboarding starts with in the Pipeline step: the same ones
# Offboarding.save() and its post_save signal create, in pipeline order.
DEFAULT_PIPELINE = [
    ("Notice Period", "notice_period"),
    ("Exit interview", "interview"),
    ("Work Handover", "handover"),
    ("FNF", "fnf"),
    ("Farewell", "other"),
    ("Archived", "archived"),
]
MAX_PIPELINE_STAGES = 30
# Marker returned instead of the form when step 1 validates, so the wizard
# can move on to the Pipeline step without saving anything yet.
PIPELINE_STEP_OK = "<!--pipeline-step-ok-->"


def create_pipeline(offboarding, stages):
    """
    Replace the stages Offboarding.save() gave a brand-new offboarding with the
    chosen pipeline, as [(title, type, ...), ...].
    """
    OffboardingStage._base_manager.filter(offboarding_id=offboarding).delete()
    for sequence, (title, stage_type, *_stage_id) in enumerate(stages, start=1):
        OffboardingStage.objects.create(
            offboarding_id=offboarding,
            title=title,
            type=stage_type,
            sequence=sequence,
        )


def update_pipeline(offboarding, stages):
    """
    Bring the stages of an existing offboarding in line with the edited
    pipeline, as [(title, type, stage_id or None), ...] in the new order:
    stages left out are deleted, the others are renamed / retyped /
    resequenced (keeping their managers, employees and tasks) and rows without
    an id are created.
    """
    existing = {stage.pk: stage for stage in offboarding.offboardingstage_set.all()}
    kept = {row[2] for row in stages if row[2]}
    for stage_id, stage in existing.items():
        if stage_id not in kept:
            stage.delete()
    for sequence, (title, stage_type, stage_id) in enumerate(stages, start=1):
        if stage_id:
            stage = OffboardingStage._base_manager.get(pk=stage_id)
            stage.title = title
            stage.type = stage_type
            stage.sequence = sequence
            stage.save()
        else:
            OffboardingStage.objects.create(
                offboarding_id=offboarding,
                title=title,
                type=stage_type,
                sequence=sequence,
            )


def _managers_field(form, label):
    """
    Swap the plain managers multi-select for the employee picker widget the
    onboarding stage/task forms use (searchable, with the Filter button).
    """
    form.fields["managers"] = HorillaMultiSelectField(
        queryset=Employee.objects.filter(is_active=True),
        widget=HorillaMultiSelectWidget(
            filter_route_name="employee-widget-filter",
            filter_class=EmployeeFilter,
            filter_instance_context_name="f",
            filter_template_path="employee_filters.html",
            required=True,
            instance=form.instance,
        ),
        label=label,
    )


def _clean_managers(form):
    """
    The picker posts raw ids, so drop the default field error and require at
    least one manager (same behaviour as the onboarding forms).
    """
    if isinstance(form.fields["managers"], HorillaMultiSelectField):
        form.errors.pop("managers", None)
        ids = form.data.getlist("managers")
        if not ids:
            raise forms.ValidationError({"managers": _("This field is required.")})
        form.cleaned_data["managers"] = form.fields["managers"].queryset.filter(
            id__in=ids
        )


class OffboardingForm(ModelForm):
    """
    OffboardingForm model form class
    """

    verbose_name = "Offboarding"

    cols = {"title": 12, "description": 12, "managers": 12, "status": 12}

    class Meta:
        model = Offboarding
        fields = "__all__"
        exclude = ["is_active"]
        labels = {"title": _("Offboarding Title")}

    # Texts of the shared pipeline wizard (recruitment/pipeline_wizard.html).
    wizard_details_label = _("Basic Information")
    wizard_details_hint = _("Title, description, managers and status.")
    wizard_intro_edit = _(
        "Drag the stages to reorder them, rename them, change their type or remove "
        "the ones you do not need. Changes are saved with the offboarding."
    )
    wizard_intro_create = _(
        "Choose the stages employees move through for this offboarding. You can "
        "always add, rename or reorder stages later from the pipeline."
    )
    wizard_required_type = ""
    wizard_required_message = ""
    wizard_locked_message = _(
        "This stage has employees or tasks. Move or remove them before deleting it."
    )
    wizard_name_max = 20

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        _managers_field(self, _("Managers"))
        # None on edit: the stages are only touched when the builder sent them.
        self.pipeline_stage_list = None if self.instance.pk else list(DEFAULT_PIPELINE)
        self.setup_pipeline_step()

    def setup_pipeline_step(self):
        """
        Turn the form into a two step wizard: the offboarding details, then the
        pipeline. On create the pipeline is default or custom, and the choice
        travels in two hidden fields that the wizard template keeps in sync.
        On edit the same builder starts from the existing stages.
        """
        self.wizard_template = "recruitment/pipeline_wizard.html"
        self.stage_types_json = json.dumps(
            [[key, str(label)] for key, label in OffboardingStage.types]
        )
        if self.instance.pk:
            # Stages holding employees or tasks cannot be deleted.
            locked = set(
                OffboardingEmployee._base_manager.filter(
                    stage_id__offboarding_id=self.instance
                ).values_list("stage_id", flat=True)
            ) | set(
                OffboardingTask._base_manager.filter(
                    stage_id__offboarding_id=self.instance
                ).values_list("stage_id", flat=True)
            )
            self.default_pipeline_json = "[]"
            existing = [
                {
                    "id": stage.pk,
                    "name": stage.title,
                    "type": stage.type,
                    "locked": stage.pk in locked,
                }
                for stage in self.instance.offboardingstage_set.order_by(
                    "sequence", "pk"
                )
            ]
            self.fields["pipeline_mode"] = forms.CharField(
                required=False, initial="custom", widget=forms.HiddenInput()
            )
            self.fields["pipeline_stages"] = forms.CharField(
                required=False, initial=json.dumps(existing), widget=forms.HiddenInput()
            )
            return
        labels = dict(OffboardingStage.types)
        self.default_pipeline = [
            {"name": name, "type": stage_type, "label": str(labels[stage_type])}
            for name, stage_type in DEFAULT_PIPELINE
        ]
        self.default_pipeline_json = json.dumps(
            [
                {"name": name, "type": stage_type}
                for name, stage_type in DEFAULT_PIPELINE
            ]
        )
        self.fields["pipeline_mode"] = forms.CharField(
            required=False, initial="default", widget=forms.HiddenInput()
        )
        self.fields["pipeline_stages"] = forms.CharField(
            required=False, widget=forms.HiddenInput()
        )

    def clean(self):
        super().clean()
        _clean_managers(self)
        # "Next" only checks step 1; the pipeline is checked when it is saved.
        if (
            "pipeline_mode" in self.fields
            and self.data.get("validate_step") != "1"
            and self.cleaned_data.get("pipeline_mode") == "custom"
        ):
            self.pipeline_stage_list = self.clean_custom_pipeline()
        return self.cleaned_data

    def clean_custom_pipeline(self):
        """
        Validate the custom pipeline sent by the Pipeline step and return it as
        [(title, type, stage_id or None), ...]. Problems are reported on the
        pipeline step.
        """
        valid_types = {key for key, _label in OffboardingStage.types}
        default = [(name, stage_type, None) for name, stage_type in DEFAULT_PIPELINE]
        try:
            rows = json.loads(self.cleaned_data.get("pipeline_stages") or "[]")
            assert isinstance(rows, list)
        except (ValueError, AssertionError):
            self.add_error("pipeline_stages", _("The pipeline could not be read."))
            return default

        own_ids = (
            set(self.instance.offboardingstage_set.values_list("pk", flat=True))
            if self.instance.pk
            else set()
        )
        stages, seen, kept_ids = [], set(), set()
        for row in rows:
            is_row = isinstance(row, dict)
            title = str(row.get("name", "")).strip() if is_row else ""
            stage_type = row.get("type") if is_row else None
            stage_id = row.get("id") if is_row else None
            if not title:
                self.add_error("pipeline_stages", _("Every stage needs a name."))
                break
            if len(title) > self.wizard_name_max:
                self.add_error(
                    "pipeline_stages",
                    _("Stage names can be at most %(max)s characters.")
                    % {"max": self.wizard_name_max},
                )
                break
            if title.casefold() in seen:
                self.add_error(
                    "pipeline_stages",
                    _('Stage names must be unique ("%(name)s" is repeated).')
                    % {"name": title},
                )
                break
            if stage_type not in valid_types:
                self.add_error("pipeline_stages", _("Choose a valid stage type."))
                break
            if stage_id is not None and (
                stage_id not in own_ids or stage_id in kept_ids
            ):
                self.add_error("pipeline_stages", _("The pipeline could not be read."))
                break
            seen.add(title.casefold())
            kept_ids.add(stage_id)
            stages.append((title, stage_type, stage_id))
        else:
            removed = own_ids - {i for i in kept_ids if i}
            if not stages:
                self.add_error(
                    "pipeline_stages", _("Add at least one stage to the pipeline.")
                )
            elif len(stages) > MAX_PIPELINE_STAGES:
                self.add_error(
                    "pipeline_stages",
                    _("A pipeline can have at most %(max)s stages.")
                    % {"max": MAX_PIPELINE_STAGES},
                )
            elif removed and (
                OffboardingEmployee._base_manager.filter(stage_id__in=removed).exists()
                or OffboardingTask._base_manager.filter(stage_id__in=removed).exists()
            ):
                self.add_error(
                    "pipeline_stages",
                    _(
                        "A stage that still has employees or tasks cannot be "
                        "deleted. Move or remove them first."
                    ),
                )
        return stages

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class OffboardingStageForm(ModelForm):
    """
    OffboardingStage model form
    """

    verbose_name = "Stage"

    cols = {"title": 12, "type": 12, "managers": 12}

    class Meta:
        model = OffboardingStage
        fields = "__all__"
        exclude = ["is_active"]
        labels = {"title": _("Stage Title")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        reload_queryset(self.fields)
        _managers_field(self, _("Stage Managers"))

    def clean(self):
        super().clean()
        _clean_managers(self)
        return self.cleaned_data

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html


class OffboardingEmployeeForm(ModelForm):
    """
    OffboardingEmployeeForm model form
    """

    verbose_name = "Offboarding "

    class Meta:
        model = OffboardingEmployee
        fields = "__all__"
        exclude = ["notice_period", "unit", "is_active"]
        widgets = {
            "notice_period_starts": forms.DateInput(attrs={"type": "date"}),
            "notice_period_ends": forms.DateInput(attrs={"type": "date"}),
        }

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        attrs = self.fields["employee_id"].widget.attrs
        attrs["onchange"] = "initialNoticePeriod($(this))"
        self.fields["employee_id"].widget.attrs.update(attrs)
        attrs = self.fields["notice_period_starts"].widget.attrs
        attrs["onchange"] = "noticePeriodUpdate($(this))"
        self.fields["notice_period_starts"].widget.attrs.update(attrs)
        if self.instance.pk:
            if self.instance.notice_period_starts:
                self.initial["notice_period_starts"] = (
                    self.instance.notice_period_starts.strftime("%Y-%m-%d")
                )
            if self.instance.notice_period_ends:
                self.initial["notice_period_ends"] = (
                    self.instance.notice_period_ends.strftime("%Y-%m-%d")
                )


class StageSelectForm(ModelForm):
    """
    This form is used to register drop down for the pipeline
    """

    class Meta:
        model = OffboardingEmployee
        fields = [
            "stage_id",
        ]

    def __init__(self, *args, offboarding=None, **kwargs):
        super().__init__(*args, **kwargs)
        attrs = self.fields["stage_id"].widget.attrs
        attrs["onchange"] = "offboardingUpdateStage($(this))"
        attrs["class"] = "w-100 oh-custom-select"
        self.fields["stage_id"].widget.attrs.update(attrs)
        self.fields["stage_id"].empty_label = None
        self.fields["stage_id"].queryset = OffboardingStage.objects.filter(
            offboarding_id=offboarding
        )
        self.fields["stage_id"].label = ""


class NoteForm(ModelForm):
    """
    Offboarding note model form
    """

    verbose_name = "Add Note"

    class Meta:
        model = OffboardingNote
        fields = "__all__"
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attachment"] = MultipleFileField(label="Attachements")
        self.fields["attachment"].required = False

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def save(self, commit: bool = ...) -> Any:
        multiple_attachment_ids = []
        attachments = None
        if self.files.getlist("attachment"):
            attachments = self.files.getlist("attachment")
            self.instance.attachment = attachments[0]
            multiple_attachment_ids = []
            for attachment in attachments:
                file_instance = OffboardingStageMultipleFile()
                file_instance.attachment = attachment
                file_instance.save()
                multiple_attachment_ids.append(file_instance.pk)
        instance = super().save(commit)
        if commit:
            instance.attachments.add(*multiple_attachment_ids)
        return instance, attachments


class TaskForm(ModelForm):
    """
    TaskForm model form
    """

    verbose_name = "Offboarding Task"
    tasks_to = forms.ModelMultipleChoiceField(
        queryset=OffboardingEmployee.objects.all(), required=False, label=_("Task To")
    )
    cols = {"title": 12, "managers": 12, "stage_id": 12, "tasks_to": 12}

    class Meta:
        model = OffboardingTask
        fields = "__all__"
        exclude = ["status", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stage_id"].empty_label = "All Stages in Offboarding"
        _managers_field(self, _("Task Managers"))
        self.fields["title"].label = _("Task Title")
        if not self.instance.pk:
            stage = OffboardingStage.objects.filter(
                id=self.initial.get("stage_id")
            ).first()
            queryset = (
                OffboardingEmployee.objects.filter(
                    stage_id__offboarding_id=stage.offboarding_id
                )
                if stage
                else OffboardingEmployee.objects.none()
            )
            self.fields["tasks_to"].queryset = queryset

    def clean(self):
        super().clean()
        _clean_managers(self)
        return self.cleaned_data

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def save(self, commit: bool = ...) -> Any:
        super().save(commit)
        if commit:
            employees = self.cleaned_data["tasks_to"]
            for employee in employees:
                assigned_task = EmployeeTask.objects.get_or_create(
                    employee_id=employee,
                    task_id=self.instance,
                )


class ResignationLetterForm(ModelForm):
    """
    Resignation Letter
    """

    cols = {
        "employee_id": 12,
        "title": 12,
        "description": 12,
    }

    description = forms.CharField(
        widget=forms.Textarea(attrs={"data-summernote": "", "style": "display:none;"}),
        label="Description",
    )
    verbose_name = "Resignation Letter"

    class Meta:
        model = ResignationLetter
        fields = "__all__"
        # planned_to_leave_on is no longer asked for: the notice period start/end
        # are chosen when the request is approved (see __init__ for the default).
        # status isn't either: new letters start as "requested" (model default) and
        # move to approved/rejected only through the Approve/Reject actions.
        exclude = ["is_active", "planned_to_leave_on", "status"]

    def as_p(self):
        """
        Render the form fields as HTML table rows with Bootstrap styling.
        """
        context = {"form": self}
        table_html = render_to_string("common_form.html", context)
        return table_html

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The column is required, so a new letter starts the notice period today;
        # existing letters keep whatever date they already have.
        if not self.instance.planned_to_leave_on:
            self.instance.planned_to_leave_on = date.today()
        exclude = []
        if self.instance.pk:
            exclude.append("employee_id")
            self.verbose_name = (
                self.instance.employee_id.get_full_name() + "'s Resignation Letter"
            )

        request = getattr(horilla_middlewares._thread_locals, "request", None)
        if request and not request.user.has_perm("offboarding.add_resignationletter"):
            # A regular employee can only resign for themselves, so there is
            # nothing to choose: drop the field and bind the letter to them.
            exclude = exclude + ["status", "employee_id"]
            if not self.instance.pk:
                self.instance.employee_id = request.user.employee_get
        if request and request.user.has_perm("offboarding.add_resignationletter"):
            if request.GET.get("emp_id"):
                emp_id = request.GET.get("emp_id")
                self.fields["employee_id"].queryset = Employee.objects.filter(id=emp_id)
                self.fields["employee_id"].initial = emp_id
        exclude = list(set(exclude))
        for field in exclude:
            self.fields.pop(field, None)

    def save(self, commit: bool = ...) -> Any:
        request = getattr(horilla_middlewares._thread_locals, "request", None)
        instance = self.instance
        if (
            not request.user.has_perm("offboarding.add_resignationletter")
            and instance.status == "requested"
        ) or request.user.has_perm("offboarding.add_resignationletter"):
            instance = super().save(commit)
        else:
            messages.info(
                request, _("You cannot edit a request that has been rejected/approved")
            )
            return None

        if (
            instance.status == "requested"
            and request
            and not request.user.has_perm("offboarding.add_resignationletter")
        ):
            with contextlib.suppress(Exception):
                notify.send(
                    request.user.employee_get,
                    recipient=self.instance.employee_id.get_reporting_manager().employee_user_id,
                    verb=gettext_noop("%(get_full_name)s requested for resignation."),
                    verb_params={
                        "get_full_name": str(self.instance.employee_id.get_full_name())
                    },
                    redirect="#",
                    icon="information",
                )
        return instance


class ResignationCancelForm(forms.Form):
    """
    Reason an employee gives when cancelling a resignation request.
    """

    cancel_reason = forms.CharField(
        label=_("Reason for Cancellation"),
        max_length=255,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "maxlength": 255,
                "class": "p-4 oh-input w-100",
                "placeholder": _("Reason for Cancellation"),
            }
        ),
    )


class ResignationCommentForm(ModelForm):
    """
    Resignation letter comment form
    """

    class Meta:
        model = ResignationComment
        fields = ("comment",)
