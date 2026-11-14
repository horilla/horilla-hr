"""
recruitment
"""

import json
from typing import Any

from django import forms
from django.contrib import messages
from django.core.cache import cache as CACHE
from django.db import transaction
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.models import IntegrationApps
from horilla.decorators import hx_request_required
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from recruitment.filters import RecruitmentFilter
from recruitment.forms import AddCandidateForm, RecruitmentCreationForm, SkillsForm
from recruitment.models import Candidate, Recruitment, Skill, Stage
from recruitment.views.linkedin import delete_post, post_recruitment_in_linkedin

# Pipeline offered by default in step 2 of "Add Recruitment": one stage per
# stage type, in the order a candidate moves through them.
DEFAULT_PIPELINE = [
    ("Applied", "applied"),
    ("Initial", "initial"),
    ("Test", "test"),
    ("Interview", "interview"),
    ("Shortlisted", "shortlisted"),
    ("Rejected Candidates", "cancelled"),
]
MAX_PIPELINE_STAGES = 30
# Marker returned instead of the form when step 1 validates, so the wizard
# can move on to step 2 without saving anything yet.
PIPELINE_STEP_OK = "<!--pipeline-step-ok-->"


def create_pipeline(recruitment, stages):
    """
    Replace the stages the post_save signal gave a brand-new recruitment
    (Applied + Initial) with the chosen pipeline, as [(name, type), ...].
    """
    Stage._base_manager.filter(recruitment_id=recruitment).delete()
    for sequence, (name, stage_type, *_stage_id) in enumerate(stages):
        Stage.objects.create(
            recruitment_id=recruitment,
            stage=name,
            stage_type=stage_type,
            sequence=sequence,
        )


def update_pipeline(recruitment, stages):
    """
    Bring the stages of an existing recruitment in line with the edited
    pipeline, as [(name, type, stage_id or None), ...] in the new order: stages
    left out are deleted, the others are renamed / retyped / resequenced and
    rows without an id are created.
    """
    existing = {stage.pk: stage for stage in recruitment.stage_set.all()}
    kept = {row[2] for row in stages if row[2]}
    for stage_id, stage in existing.items():
        if stage_id not in kept:
            stage.delete()
    # Park the stages that change under throwaway values first, so swapping two
    # names (or types) cannot trip the unique constraints half way through.
    changed = [
        row
        for row in stages
        if row[2]
        and (existing[row[2]].stage != row[0] or existing[row[2]].stage_type != row[1])
    ]
    for row in changed:
        Stage._base_manager.filter(pk=row[2]).update(
            stage=f"__tmp_{row[2]}", stage_type="interview"
        )
    for sequence, (name, stage_type, stage_id) in enumerate(stages):
        if stage_id:
            stage = Stage._base_manager.get(pk=stage_id)
            stage.stage = name
            stage.stage_type = stage_type
            stage.sequence = sequence
            stage.save()
        else:
            Stage.objects.create(
                recruitment_id=recruitment,
                stage=name,
                stage_type=stage_type,
                sequence=sequence,
            )


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentView(TemplateView):
    """
    Recuitment page
    """

    template_name = "cbv/recruitment/recruitment.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentList(HorillaListView):
    """
    List view of recruitment
    """

    model = Recruitment
    filter_class = RecruitmentFilter
    view_id = "rec-view-container"

    bulk_update_fields = ["vacancy", "start_date", "end_date", "closed"]

    template_name = "cbv/recruitment/rec_main.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-recruitment")

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        self.queryset = (
            super()
            .get_queryset(queryset, filtered, *args, **kwargs)
            .filter(is_active=self.request.GET.get("is_active", True))
        )
        return self.queryset

    columns = [
        (_("Recruitment"), "recruitment_column"),
        (_("Managers"), "managers_column"),
        (_("Open Positions"), "open_job_col"),
        (_("Vaccancy"), "vacancy"),
        (_("Total Hires"), "tot_hires"),
        (_("Start Date"), "start_date"),
        (_("End date"), "end_date"),
        (_("Status"), "status_col"),
    ]
    action_method = "rec_actions"

    header_attrs = {
        "recruitment_column": 'style="width : 200px !important"',
        "action": 'style="width : 180px !important"',
    }

    row_status_indications = [
        (
            "closed--dot",
            _("Closed"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=closed]').val('true');
                $('#applyFilter').click();

            "
            """,
        ),
        (
            "open--dot",
            _("Open"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=closed]').val('false');
                $('#applyFilter').click();

            "
            """,
        ),
    ]

    row_status_class = "closed-{closed}"

    sortby_mapping = [
        (_("Recruitment"), "recruitment_column"),
        (_("Vaccancy"), "vacancy"),
        (_("Start Date"), "start_date"),
        (_("End date"), "end_date"),
    ]

    row_attrs = """
                class="oh-permission-table--collapsed"
                hx-get='{recruitment_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    nested_group_by_fields = [
        ("title", _("Recruitment")),
        ("job_position_id", _("Job Position")),
        ("company_id", _("Company")),
        ("closed", _("Closed")),
        ("is_published", _("Published")),
        ("start_date", _("Start Date")),
        ("end_date", _("End Date")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentNav(HorillaNavView):
    """
    For nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-recruitment")
        self.search_in = [
            ("title", _("Recruitment")),
            ("candidate", _("Candidate")),
            ("stage", _("Stage")),
            ("job_position_id", _("Job Position")),
            ("company_id", _("Company")),
            ("recruitment_managers", _("Recruitment Managers")),
        ]

        self.create_attrs = f"""
                            hx-get='{reverse_lazy('recruitment-create')}'
                            hx-target="#genericModalBody"
                            data-target="#genericModal"
                            data-toggle="oh-modal-toggle"
                            """

    nav_title = _("Recruitment")
    filter_instance = RecruitmentFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    filter_body_template = "cbv/recruitment/filters.html"
    modern_filter = True

    nested_group_by_fields = [
        ("title", _("Recruitment")),
        ("job_position_id", _("Job Position")),
        ("company_id", _("Company")),
        ("closed", _("Closed")),
        ("is_published", _("Published")),
        ("start_date", _("Start Date")),
        ("end_date", _("End Date")),
    ]


class RecruitmentCreationFormExtended(RecruitmentCreationForm):
    """
    extended form view for create
    """

    # Texts of the shared pipeline wizard (recruitment/pipeline_wizard.html).
    wizard_details_label = _("Recruitment")
    wizard_details_hint = _("Title, dates and managers.")
    wizard_intro_edit = _(
        "Drag the stages to reorder them, rename them, change their type or remove "
        "the ones you do not need. Changes are saved with the recruitment."
    )
    wizard_intro_create = _(
        "Choose the stages candidates move through for this recruitment. You can "
        "always add, rename or reorder stages later from the pipeline."
    )
    wizard_required_type = "applied"
    wizard_name_max = 50
    wizard_required_message = _(
        "The pipeline needs at least one stage of type Applied."
    )
    wizard_locked_message = _(
        "This stage has candidates. Move them to another stage before deleting it."
    )

    cols = {
        "title": 12,
        "description": 12,
        "recruitment_managers": 12,
        "is_published": 4,
        "optional_profile_image": 4,
        "optional_resume": 4,
    }

    class Meta:
        """
        Meta class to add the additional info
        """

        model = Recruitment
        fields = [
            "title",
            "description",
            "open_positions",
            "recruitment_managers",
            "start_date",
            "end_date",
            "vacancy",
            "company_id",
            "survey_templates",
            "skills",
            "is_published",
            "optional_profile_image",
            "optional_resume",
            "publish_in_linkedin",
            "linkedin_account_id",
        ]
        exclude = ["is_active"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"data-summernote": ""}),
            "vacancy": forms.NumberInput(attrs={"min": 1}),
        }
        labels = {
            "description": _("Description"),
            "start_date": _("Start Date"),
            "end_date": _("End Date"),
            "survey_templates": _("Survey Templates"),
            "is_published": _("Publish"),
            "vacancy": _("Vacancy"),
            "open_positions": _("Job Position"),
            "recruitment_managers": _("Managers"),
            "optional_profile_image": _("Optional Profile Image?"),
            "optional_resume": _("Optional Resume?"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # None on edit: the stages are only touched when the builder sent them.
        self.pipeline_stage_list = None if self.instance.pk else list(DEFAULT_PIPELINE)
        # The model allows a blank title; the form does not.
        self.fields["title"].required = True
        if not self.instance.pk:
            self.fields["vacancy"].initial = 1
            self.fields["open_positions"].required = True
        self.vacancy_line_list = None
        self.setup_vacancy_step()
        self.setup_pipeline_step()
        self.linkedin_enabled = IntegrationApps.objects.filter(
            app_label="linkedin", is_enabled=True
        ).exists()
        if not self.linkedin_enabled:
            self.fields["publish_in_linkedin"].initial = False
            self.fields["publish_in_linkedin"].widget = forms.HiddenInput()
            self.fields["linkedin_account_id"].widget = forms.HiddenInput()

    # Stage types that older data carries under a name the app no longer offers: "Hired" is the shortlisted type.
    # Shown (and saved, if the pipeline is saved) as the current type, so such a stage can still be edited.
    LEGACY_STAGE_TYPES = {"hired": "shortlisted"}

    def setup_vacancy_step(self):
        """
        Vacancies are set on a step of their own, one line per job position chosen on the first step.

        The lines travel in a hidden field as JSON, like the pipeline's stages, and ``vacancy`` becomes a hidden
        total the lines overwrite. A form shown without the wizard (duplicate) keeps the plain Vacancy field.
        """
        self.wizard_vacancy = True
        # The job positions are chosen on the vacancy step, a line each. The field stays (it is what is saved) but
        # as hidden inputs the step keeps in step with its lines; the plain select is kept for the duplicate form.
        positions = self.fields["open_positions"]
        self._open_positions_widget = positions.widget
        positions.widget = forms.MultipleHiddenInput()
        positions.required = False
        self.position_options_json = json.dumps(
            [
                {"id": position.pk, "label": str(position)}
                for position in positions.queryset
            ]
        )
        self.fields["vacancy"].widget = forms.HiddenInput()
        self.fields["vacancy"].required = False
        initial = self.instance.vacancy_rows() if self.instance.pk else []
        self.fields["vacancy_lines"] = forms.CharField(
            required=False, initial=json.dumps(initial), widget=forms.HiddenInput()
        )

    def parse_vacancy_lines(self):
        """
        Read the vacancy lines the step sent: ``{job position: vacancy}``, one per chosen position, and make
        their total the recruitment's vacancy. Problems are reported on the vacancy step.
        """
        raw = self.cleaned_data.get("vacancy_lines") or ""
        if not raw:
            return  # nothing from the wizard (a duplicate, say): the Vacancy field stands
        try:
            rows = json.loads(raw)
            assert isinstance(rows, list)
        except (ValueError, AssertionError):
            self.add_error(
                "vacancy_lines",
                _("The Vacancy Lines Could Not Be Read. Please Review Them."),
            )
            return
        # The job positions are the lines' own: each line names the position it is for.
        wanted = [str((row or {}).get("position")) for row in rows]
        positions = {
            str(p.pk): p
            for p in self.fields["open_positions"].queryset.filter(
                pk__in=[pk for pk in wanted if pk.isdigit()]
            )
        }
        if len(set(wanted)) != len(wanted):
            self.add_error(
                "vacancy_lines", _("A Job Position Can Only Be On One Line.")
            )
            return
        lines = {}
        for row in rows:
            position = positions.get(str((row or {}).get("position")))
            given = (row or {}).get("vacancy")
            try:
                # Empty is "not specified": the line stays, with no number.
                number = None if given in (None, "") else int(given)
            except (TypeError, ValueError):
                number = -1
            if position is None:
                self.add_error(
                    "vacancy_lines", _("Choose A Job Position For Every Line.")
                )
                return
            if number is not None and number < 0:
                self.add_error(
                    "vacancy_lines",
                    _(
                        "Vacancy For %(position)s Must Be A Whole Number Of Zero Or More."
                    )
                    % {"position": position.job_position},
                )
                return
            lines[position] = number
        if not lines:
            self.add_error("vacancy_lines", _("Add At Least One Job Position."))
            return
        self.vacancy_line_list = lines
        self.cleaned_data["open_positions"] = self.fields[
            "open_positions"
        ].queryset.filter(pk__in=[position.pk for position in lines])
        self.cleaned_data["vacancy"] = sum(number or 0 for number in lines.values())

    def _post_clean(self):
        super()._post_clean()
        # The vacancy total is not on screen: what the model says about it belongs on the vacancy step.
        if "vacancy_lines" in self.fields and "vacancy" in self._errors:
            for message in self._errors.pop("vacancy"):
                self.add_error("vacancy_lines", message)
        # A blank title is reported by the required field and again by
        # Recruitment.clean(); show it once.
        title_errors = self.errors.get("title")
        if title_errors and len(title_errors) > 1:
            self._errors["title"] = self.error_class(title_errors.as_data()[:1])

    def clean_publish_in_linkedin(self):
        # The LinkedIn fields are hidden while the integration is off, so a
        # recruitment saved earlier with "publish" on would fail on an account
        # field nobody can see (and Next would seem to do nothing).
        if not self.linkedin_enabled:
            return False
        return self.cleaned_data.get("publish_in_linkedin")

    def setup_pipeline_step(self):
        """
        Turn the form into a two step wizard: the recruitment details, then the
        pipeline. On create the pipeline is default or custom, and the choice
        travels in two hidden fields that the wizard template keeps in sync.
        On edit the same builder starts from the existing stages.
        """
        self.wizard_template = "recruitment/pipeline_wizard.html"
        self.stage_types_json = json.dumps(
            [[key, str(label)] for key, label in Stage.stage_types]
        )
        if self.instance.pk:
            # Editing: step 2 is the builder, started from the stages the
            # recruitment already has. Stages with candidates cannot be deleted.
            with_candidates = set(
                Candidate._base_manager.filter(
                    stage_id__recruitment_id=self.instance
                ).values_list("stage_id", flat=True)
            )
            self.default_pipeline_json = "[]"
            existing = [
                {
                    "id": stage.pk,
                    "name": stage.stage,
                    "type": self.LEGACY_STAGE_TYPES.get(
                        stage.stage_type, stage.stage_type
                    ),
                    "locked": stage.pk in with_candidates,
                }
                for stage in self.instance.stage_set.order_by("sequence")
            ]
            self.fields["pipeline_mode"] = forms.CharField(
                required=False, initial="custom", widget=forms.HiddenInput()
            )
            self.fields["pipeline_stages"] = forms.CharField(
                required=False,
                initial=json.dumps(existing),
                widget=forms.HiddenInput(),
            )
            return
        self.default_pipeline = [
            {
                "name": name,
                "type": stage_type,
                "label": str(dict(Stage.stage_types)[stage_type]),
            }
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
        # The details step alone ("Next" from step 1) does not know the vacancies yet.
        if "vacancy_lines" in self.fields and self.data.get("validate_step") != "1":
            self.parse_vacancy_lines()
        super().clean()
        # "Next" only checks the step it leaves (1: the details, 2: the vacancies); the pipeline is checked when it
        # is saved. Checking it on the way to its own step would block the person from ever reaching it.
        if (
            "pipeline_mode" in self.fields
            and self.data.get("validate_step") not in ("1", "2")
            and self.cleaned_data.get("pipeline_mode") == "custom"
        ):
            self.pipeline_stage_list = self.clean_custom_pipeline()
        return self.cleaned_data

    def clean_custom_pipeline(self):
        """
        Validate the custom pipeline sent by step 2 and return it as
        [(name, type, stage_id or None), ...]. Problems are reported on the
        pipeline step.
        """
        valid_types = {key for key, _label in Stage.stage_types}
        try:
            rows = json.loads(self.cleaned_data.get("pipeline_stages") or "[]")
            assert isinstance(rows, list)
        except (ValueError, AssertionError):
            self.add_error("pipeline_stages", _("The pipeline could not be read."))
            return [(name, stage_type, None) for name, stage_type in DEFAULT_PIPELINE]

        own_ids = (
            set(self.instance.stage_set.values_list("pk", flat=True))
            if self.instance.pk
            else set()
        )
        # Stages saved before the once-per-type rule may repeat a type; only a
        # new or retyped stage is held to it.
        existing_types = (
            dict(self.instance.stage_set.values_list("pk", "stage_type"))
            if self.instance.pk
            else {}
        )
        stages, seen, kept_ids = [], set(), set()
        for row in rows:
            name = str(row.get("name", "")).strip() if isinstance(row, dict) else ""
            stage_type = row.get("type") if isinstance(row, dict) else None
            if not name:
                self.add_error("pipeline_stages", _("Every stage needs a name."))
                break
            if len(name) > 50:
                self.add_error(
                    "pipeline_stages",
                    _("Stage names can be at most 50 characters."),
                )
                break
            if name.casefold() in seen:
                self.add_error(
                    "pipeline_stages",
                    _('Stage names must be unique ("%(name)s" is repeated).')
                    % {"name": name},
                )
                break
            if stage_type not in valid_types:
                self.add_error("pipeline_stages", _("Choose a valid stage type."))
                break
            stage_id = row.get("id") if isinstance(row, dict) else None
            if stage_id is not None and (
                stage_id not in own_ids or stage_id in kept_ids
            ):
                self.add_error("pipeline_stages", _("The pipeline could not be read."))
                break
            seen.add(name.casefold())
            kept_ids.add(stage_id)
            stages.append((name, stage_type, stage_id))
        else:
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
            elif any(
                [row[1] for row in stages].count(row[1]) > 1
                and row[1] in Stage.UNIQUE_STAGE_TYPES
                and (row[2] is None or existing_types.get(row[2]) != row[1])
                for row in stages
            ):
                self.add_error(
                    "pipeline_stages",
                    _(
                        "Applied, Shortlisted and Rejected stages can only be used "
                        "once in a pipeline."
                    ),
                )
            elif (
                own_ids - kept_ids
                and Candidate._base_manager.filter(
                    stage_id__in=own_ids - kept_ids
                ).exists()
            ):
                self.add_error(
                    "pipeline_stages",
                    _(
                        "A stage that still has candidates cannot be deleted. "
                        "Move the candidates to another stage first."
                    ),
                )
            elif not any(row[1] == "applied" for row in stages):
                # Candidates who apply are placed in the "applied" stage.
                self.add_error(
                    "pipeline_stages",
                    _("The pipeline needs at least one stage of type Applied."),
                )
        return stages


@method_decorator(login_required, name="dispatch")
class RecruitmentNewSkillForm(HorillaFormView):
    """
    form view for add new skill
    """

    model = Skill
    form_class = SkillsForm
    new_display_title = _("Skills")
    is_dynamic_create_view = True

    def form_valid(self, form: SkillsForm) -> HttpResponse:
        if form.is_valid():
            message = _("New Skill Created Successfully")
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentForm(HorillaFormView):
    """
    Form View
    """

    model = Recruitment
    form_class = RecruitmentCreationFormExtended
    new_display_title = _("Add Recruitment")
    dynamic_create_fields = [("skills", RecruitmentNewSkillForm)]
    # Lists to refresh after saving, on top of what the caller asked for (a subclass opened from a list sets it).
    reload_targets = ()
    # template_name = "cbv/recruitment/recruitment_form.html"

    def get_context_data(self, **kwargs):
        """
        Return context data with optional verbose name for form based on instance state.
        """
        context = super().get_context_data(**kwargs)

        if self.form.instance.pk:
            self.form_class.verbose_name = "Edit Recruitment"
        return context

    def form_valid(self, form: RecruitmentCreationFormExtended) -> HttpResponse:
        """
        Process form submission to save or update a Recruitment object and display success message.
        """
        targets_to_reload = list(self.reload_targets)
        is_create = not form.instance.pk

        if self.request.POST.get("validate_step") in ("1", "2"):
            # "Next" on a step of the wizard: what is on it is valid, nothing
            # is saved until the last step is submitted.
            return HttpResponse(PIPELINE_STEP_OK)

        if not is_create:
            try:
                with transaction.atomic():
                    recruitment = form.save()
                    if form.vacancy_line_list is not None:
                        recruitment.set_vacancy_lines(form.vacancy_line_list)
                    if form.pipeline_stage_list is not None:
                        update_pipeline(recruitment, form.pipeline_stage_list)
            except ProtectedError:
                form.add_error(
                    "pipeline_stages",
                    _("A stage that is still in use cannot be deleted."),
                )
                return self.form_invalid(form)
            recruitment_managers = self.request.POST.getlist("recruitment_managers")
            if recruitment_managers:
                recruitment.recruitment_managers.set(recruitment_managers)
            if recruitment.publish_in_linkedin and recruitment.linkedin_account_id:
                delete_post(recruitment)
                post_recruitment_in_linkedin(
                    self.request, recruitment, recruitment.linkedin_account_id
                )
            message = _("Recruitment Updated Successfully")
        else:
            with transaction.atomic():
                recruitment = form.save()
                if form.vacancy_line_list is not None:
                    recruitment.set_vacancy_lines(form.vacancy_line_list)
                create_pipeline(recruitment, form.pipeline_stage_list)
            recruitment_managers = self.request.POST.getlist("recruitment_managers")
            if recruitment_managers:
                recruitment.recruitment_managers.set(recruitment_managers)
            if recruitment.publish_in_linkedin and recruitment.linkedin_account_id:
                post_recruitment_in_linkedin(
                    self.request, recruitment, recruitment.linkedin_account_id
                )
            message = _("Recruitment Created Successfully")
        CACHE.delete(f"matching_resumes_{recruitment.pk}")
        messages.success(self.request, message)

        from_pipeline = self.request.GET.get("pipeline") == "true" or (
            self.request.resolver_match
            and self.request.resolver_match.url_name == "recruitment-update-pipeline"
        )
        if from_pipeline and is_create:
            script = f"window.location.href = '{reverse('cbv-pipeline')}';"
            return self.HttpResponse(script=script)
        if from_pipeline:
            targets_to_reload.append("#applyFilter")

        return self.HttpResponse(targets_to_reload=targets_to_reload)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class AddCandidateFormView(HorillaFormView):
    """
    form view for add candidate
    """

    form_class = AddCandidateForm
    model = Candidate
    new_display_title = _("Add Candidate")

    def dispatch(self, request, *args, **kwargs):
        """
        Return an empty response for a GET request without a stage or
        recruitment.
        """
        if (
            request.method == "GET"
            and not request.GET.get("stage_id")
            and not request.GET.get("rec_id")
        ):
            return HttpResponse()
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self) -> dict:
        initial = super().get_initial()
        stage_id = self.request.GET.get("stage_id")
        rec_id = self.request.GET.get("rec_id")
        initial["stage_id"] = stage_id
        initial["rec_id"] = rec_id
        return initial

    def form_valid(self, form: AddCandidateForm) -> HttpResponse:
        if form.is_valid():
            message = _("Candidate Added successfully.")
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse("<script>window.location.reload</script>")
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentFormDuplicate(RecruitmentForm):
    """
    Duplicate a recruitment through the same steps as a new one: the form opens filled in from the original
    (title marked as a copy, positions, vacancy lines, managers, dates), and saving creates a new recruitment.
    """

    new_display_title = _("Duplicate Recruitment")
    reload_targets = ("#applyFilter",)

    def init_form(self, *args, data={}, files={}, instance=None, **kwargs):
        """No instance: the copy is a new recruitment, the original only fills the form in (see get_initial)."""
        return super().init_form(*args, data=data, files=files, instance=None, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if form.instance.pk:
            # A URL with a pk makes the base view put the original back as the form's instance; a copy is new.
            form.instance = Recruitment()
            self.form_class.verbose_name = self.new_display_title
        return form

    def get_initial(self):
        initial = super().get_initial()
        original = Recruitment.objects.filter(pk=self.kwargs.get("pk")).first()
        if original is None:
            return initial
        initial.update(
            {
                "title": f"{original.title or ''} (copy)",
                "description": original.description,
                "start_date": original.start_date,
                "end_date": original.end_date,
                "vacancy": original.vacancy,
                "open_positions": list(
                    original.open_positions.values_list("pk", flat=True)
                ),
                "recruitment_managers": list(
                    original.recruitment_managers.values_list("pk", flat=True)
                ),
                "survey_templates": list(
                    original.survey_templates.values_list("pk", flat=True)
                ),
                "skills": list(original.skills.values_list("pk", flat=True)),
                "is_published": original.is_published,
                "optional_profile_image": original.optional_profile_image,
                "optional_resume": original.optional_resume,
                "company_id": original.company_id_id,
                "vacancy_lines": json.dumps(original.vacancy_rows()),
            }
        )
        return initial


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="recruitment.view_recruitment"), name="dispatch"
)
class RecruitmentDetailView(HorillaDetailedView):
    """
    detail view of page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Managers"), "managers_detail"),
            (_("Open Positions"), "open_job_detail"),
            (_("Vaccancy"), "vacancy"),
            (_("Total Hires"), "tot_hires"),
            (_("Start Date"), "start_date"),
            (_("End date"), "end_date"),
        ]

    action_method = "detail_actions"

    model = Recruitment
    title = _("Details")
    header = {
        "title": "title",
        "subtitle": "status_col",
        "avatar": "get_avatar",
    }
