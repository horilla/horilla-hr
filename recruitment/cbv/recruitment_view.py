"""
recruitment
"""

from typing import Any

from django import forms
from django.contrib import messages
from django.core.cache import cache as CACHE
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.models import IntegrationApps
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
from recruitment.models import Candidate, Recruitment, Skill
from recruitment.views.linkedin import delete_post, post_recruitment_in_linkedin


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

    # Mirrors RecruitmentNav.nested_group_by_fields below -- List and Nav
    # are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split). "Managers"
    # (recruitment_managers) and the M2M "Open Positions" (open_positions)
    # are deliberately left out: they're ManyToManyFields, and the nested
    # engine's `values(*fields).annotate(Count("pk"))` aggregate would fan
    # out one row per related manager/position, double-counting
    # recruitments with more than one assigned. `job_position_id` (a
    # single FK, distinct from the open_positions M2M) is used instead.
    nested_group_by_fields = [
        ("title", _("Recruitment")),
        ("job_position_id", _("Job Position")),
        ("company_id", _("Company")),
        ("closed", _("Is Closed")),
        ("is_published", _("Is Published")),
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
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. RecruitmentFilter.ajax_fields (Managers,
    # Company) already exists from the Pipeline panel work.
    modern_filter = True

    # Mirrors RecruitmentList.nested_group_by_fields
    nested_group_by_fields = [
        ("title", _("Recruitment")),
        ("job_position_id", _("Job Position")),
        ("company_id", _("Company")),
        ("closed", _("Is Closed")),
        ("is_published", _("Is Published")),
        ("start_date", _("Start Date")),
        ("end_date", _("End Date")),
    ]


class RecruitmentCreationFormExtended(RecruitmentCreationForm):
    """
    extended form view for create
    """

    cols = {
        "title": 12,
        "description": 12,
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
        if not self.instance.pk:
            self.fields["vacancy"].initial = 1
            self.fields["open_positions"].required = True
        if not IntegrationApps.objects.filter(
            app_label="linkedin", is_enabled=True
        ).exists():
            self.fields["publish_in_linkedin"].initial = False
            self.fields["publish_in_linkedin"].widget = forms.HiddenInput()
            self.fields["linkedin_account_id"].widget = forms.HiddenInput()


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
        targets_to_reload = []

        if form.instance.pk:
            recruitment = form.save()
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
            recruitment = form.save()
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
        if self.request.GET.get("pipeline") == "true" or (
            self.request.resolver_match
            and self.request.resolver_match.url_name == "recruitment-update-pipeline"
        ):
            # Refresh pipeline container only, instead of reloading the whole page.
            targets_to_reload.append("#applyFilter")

        return self.HttpResponse(targets_to_reload=targets_to_reload)

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


@method_decorator(login_required, name="dispatch")
class AddCandidateFormView(HorillaFormView):
    """
    form view for add candidate
    """

    form_class = AddCandidateForm
    model = Candidate
    new_display_title = _("Add Candidate")

    def dispatch(self, request, *args, **kwargs):
        # This is a fragment meant to be loaded via htmx into the "Add
        # Candidate" modal from a specific pipeline stage, always carrying
        # stage_id. Visited directly/standalone without it, render nothing
        # rather than the raw, unstyled form fragment.
        if request.method == "GET" and not request.GET.get("stage_id"):
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
class RecruitmentFormDuplicate(HorillaFormView):
    """
    Duplicate form view
    """

    model = Recruitment
    form_class = RecruitmentCreationFormExtended

    def get_context_data(self, **kwargs):
        """
        Return context data for duplicating a Recruitment object form with modified initial values.
        """
        context = super().get_context_data(**kwargs)
        original_object = Recruitment.objects.get(id=self.kwargs["pk"])
        form = self.form_class(instance=original_object)
        for field_name, field in form.fields.items():
            if isinstance(field, forms.CharField):
                if field.initial:
                    initial_value = field.initial
                else:
                    initial_value = f"{form.initial.get(field_name, '')} (copy)"
                form.initial[field_name] = initial_value
                form.fields[field_name].initial = initial_value
        context["form"] = form
        self.form_class.verbose_name = _("Duplicate")
        return context

    def form_valid(self, form: RecruitmentCreationFormExtended) -> HttpResponse:
        """
        Process form submission to add a new recruitment.
        """
        form = self.form_class(self.request.POST)
        if form.is_valid():
            recruitment = form.save()
            message = _("Recruitment added")
            recruitment.save()
            recruitment_managers = self.request.POST.getlist("recruitment_managers")
            job_positions = self.request.POST.getlist("open_positions")
            if recruitment_managers:
                recruitment.recruitment_managers.set(recruitment_managers)
            if job_positions:
                recruitment.open_positions.set(job_positions)
            messages.success(self.request, message)
            return self.HttpResponse(targets_to_reload=["#applyFilter"])

        return super().form_valid(form)


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
