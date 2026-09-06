"""
Stage.py
"""

import contextlib
from typing import Any

from django import forms
from django.contrib import messages
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from employee.models import Employee
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from notifications.signals import notify
from recruitment.filters import StageFilter
from recruitment.forms import StageCreationForm
from recruitment.models import Stage


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="recruitment.view_stage"), name="dispatch")
class StageView(TemplateView):
    """
    Stage
    """

    template_name = "cbv/stages/stages.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="recruitment.view_stage"), name="dispatch")
class StageList(HorillaListView):
    """
    List view of stage
    """

    bulk_update_fields = [
        "stage_managers",
    ]

    model = Stage
    filter_class = StageFilter

    def get_queryset(self):
        """
        Returns a filtered queryset of active recruitments.
        """
        queryset = super().get_queryset()
        queryset = (
            queryset.filter(recruitment_id__is_active=True)
            .select_related("recruitment_id")
            .prefetch_related(
                # Employee's manager silently filters is_active=True on .all()
                # (HorillaCompanyManager), but prefetch_related builds its batch
                # query from get_queryset() and skips that filter. Mismatched
                # query shapes mean the prefetch cache never matches what the
                # row template actually calls, causing a fresh query per stage.
                # Prefetch() pins the exact queryset so the cache hits.
                Prefetch(
                    "stage_managers",
                    queryset=Employee.objects.filter(is_active=True),
                )
            )
            # managers_count comes from Stage.managers_count() using the
            # prefetch cache — Count()+M2M joins made every group page slow.
        )
        return queryset

    columns = [
        (_("Title"), "title_col"),
        (_("Managers"), "managers_col"),
        (_("Type"), "get_type"),
    ]
    sortby_mapping = [
        (_("Type"), "get_type"),
    ]
    action_method = "actions_col"

    row_status_indications = [
        (
            "hired--dot",
            _("Hired"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=stage_type]').val('hired');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "cancelled--dot",
            _("Cancelled"),
            """
            onclick="
                 $('#applyFilter').closest('form').find('[name=stage_type]').val('cancelled');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "interview--dot",
            _("Interview"),
            """
            onclick=" $('#applyFilter').closest('form').find('[name=stage_type]').val('interview');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "test--dot",
            _("Test"),
            """
            onclick=" $('#applyFilter').closest('form').find('[name=stage_type]').val('test');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "initial--dot",
            _("Initial"),
            """
            onclick=" $('#applyFilter').closest('form').find('[name=stage_type]').val('initial');
                $('#applyFilter').click();
            "
            """,
        ),
    ]

    row_status_class = "stage-type-{stage_type}"

    row_attrs = """
                class="oh-permission-table--collapsed"
                hx-get='{stage_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """
    header_attrs = {
        "title_col": """
                      style='width:250px !important'
                      """,
        "managers_col": """
                      style='width:250px !important'
                      """,
        "get_type": """
                      style='width:250px !important'
                      """,
        "action": """
                   style="width:250px !important"
                   """,
    }


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="recruitment.view_stage"), name="dispatch")
class StageNav(HorillaNavView):
    """
    For nav bar
    """

    template_name = "cbv/stages/stage_main.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-stage")
        self.create_attrs = f"""
                          hx-get='{reverse_lazy('rec-stage-create')}'
                          hx-target="#genericModalBody"
                          data-target="#genericModal"
                          data-toggle="oh-modal-toggle"
                          """

    nav_title = _("Stage")
    filter_instance = StageFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    filter_body_template = "cbv/stages/filter.html"
    default_group_by = "recruitment_id"
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. StageFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    group_by_fields = [("recruitment_id", _("Recruitment"))]


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="recruitment.add_stage"), name="dispatch")
class StageFormView(HorillaFormView):
    """
    Form View
    """

    model = Stage
    form_class = StageCreationForm
    new_display_title = _("Add Stage")

    def get_context_data(self, **kwargs):
        """
        Returns context with a form for creating or editing a stage.
        """
        context = super().get_context_data(**kwargs)
        rec_id = self.request.GET.get("recruitment_id")
        self.form.fields["recruitment_id"].initial = rec_id
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Edit Stage")
            self.form_class(instance=self.form.instance)
        context["form"] = self.form
        return context

    def form_valid(self, form: StageCreationForm) -> HttpResponse:
        """
        Handles valid form submission, updating or saving a stage.
        """
        if form.is_valid():
            targets_to_reload = []
            if form.instance.pk:
                stage = form.save()
                stage.save()
                stage_managers = self.request.POST.getlist("stage_managers")
                if stage_managers:
                    stage.stage_managers.set(stage_managers)
                message = _("Stage updated")
            else:
                stage_obj = form.save()
                stage_obj.stage_managers.set(
                    Employee.objects.filter(id__in=form.data.getlist("stage_managers"))
                )
                stage_obj.save()
                recruitment_obj = stage_obj.recruitment_id
                rec_stages = (
                    Stage.objects.filter(recruitment_id=recruitment_obj, is_active=True)
                    .order_by("sequence")
                    .last()
                )
                if rec_stages.sequence is None:
                    stage_obj.sequence = 1
                else:
                    stage_obj.sequence = rec_stages.sequence + 1
                stage_obj.save()
                message = _("Stage added")
                with contextlib.suppress(Exception):
                    managers = stage_obj.stage_managers.select_related(
                        "employee_user_id"
                    )
                    users = [employee.employee_user_id for employee in managers]
                    notify.send(
                        self.request.user.employee_get,
                        recipient=users,
                        verb=f"Stage {stage_obj} is updated on recruitment {stage_obj.recruitment_id},\
                            You are chosen as one of the managers",
                        verb_ar=f"تم تحديث المرحلة {stage_obj} في التوظيف\
                            {stage_obj.recruitment_id}، تم اختيارك كأحد المديرين",
                        verb_de=f"Stufe {stage_obj} wurde in der Rekrutierung {stage_obj.recruitment_id}\
                            aktualisiert. Sie wurden als einer der Manager ausgewählt",
                        verb_es=f"La etapa {stage_obj} ha sido actualizada en la contratación\
                            {stage_obj.recruitment_id}. Has sido elegido/a como uno de los gerentes",
                        verb_fr=f"L'étape {stage_obj} a été mise à jour dans le recrutement\
                            {stage_obj.recruitment_id}. Vous avez été choisi(e) comme l'un des responsables",
                        icon="people-circle",
                        redirect=reverse("pipeline"),
                    )
                # Refresh pipeline tab content immediately after creating a stage.
                targets_to_reload.append("#applyFilter")
            messages.success(self.request, message)
            return self.HttpResponse(targets_to_reload=targets_to_reload)
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="recruitment.change_stage"), name="dispatch")
class StageDuplicateForm(HorillaFormView):
    """
    Duplicate form view
    """

    model = Stage
    form_class = StageCreationForm

    def get_context_data(self, **kwargs):
        """
        Prepares form context for duplicating a stage.
        """
        context = super().get_context_data(**kwargs)
        original_object = Stage.objects.get(id=self.kwargs["pk"])
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
        self.form_class.verbose_name = "Duplicate"
        return context

    def form_valid(self, form: StageCreationForm) -> HttpResponse:
        """
        Handles valid submission of a stage creation form.
        """
        form = self.form_class(self.request.POST)
        if form.is_valid():
            message = "Stage added"
            stage = form.save()
            stage.save()
            stage_managers = self.request.POST.getlist("stage_managers")
            if stage_managers:
                stage.stage_managers.set(stage_managers)
            messages.success(self.request, _(message))
            return self.HttpResponse()

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="recruitment.view_stage"), name="dispatch")
class StageDetailView(HorillaDetailedView):
    """
    detail view of page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Title"), "stage"),
            (_("Managers"), "detail_managers_col"),
            (_("Type"), "get_type"),
        ]

    action_method = "detail_action"

    model = Stage
    title = _("Details")
    header = {
        "title": "recruitment_id",
        "subtitle": "Stages",
        "avatar": "get_avatar",
    }
