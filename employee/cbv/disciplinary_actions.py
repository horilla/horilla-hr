"""
disciplinary actions
"""

import contextlib
from typing import Any

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.methods import filtersubordinates
from employee.filters import DisciplinaryActionFilter
from employee.forms import ActiontypeForm, DisciplinaryActionForm
from employee.models import Actiontype, DisciplinaryAction
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from notifications.signals import notify


@method_decorator(login_required, name="dispatch")
class DisciplinaryActionsView(TemplateView):
    """
    disciplinary actions
    """

    template_name = "cbv/disciplinary_actions/disciplinary_actions.html"


@method_decorator(login_required, name="dispatch")
class DisciplinaryActionsList(HorillaListView):
    """
    List view of disciplinary actions
    """

    columns = [
        (_("Employee"), "employee_column"),
        (_("Action Taken"), "action_taken_col"),
        (_("Login Block"), "block_option_col"),
        (_("Action Date"), "action_date_col"),
        (_("Attachments"), "attachments_col"),
        (_("Description"), "description"),
    ]

    header_attrs = {"employee_column": 'style="width:300px !important;"'}

    sortby_mapping = [
        (_("Action Taken"), "action_taken_col"),
        (_("Action Date"), "action_date_col"),
    ]

    row_attrs = """
        class ="oh-sticky-table__tr oh-permission-table__tr oh-permission-table--collapsed"
        hx-get='{dis_action_detail_view}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """

    model = DisciplinaryAction
    filter_class = DisciplinaryActionFilter

    def get_queryset(self):
        queryset = super().get_queryset()
        data = queryset

        employee = self.request.user.employee_get
        queryset = filtersubordinates(
            self.request, queryset, "employee.view_disciplinaryaction"
        ).distinct()
        queryset = queryset | data.filter(employee_id=employee).distinct()

        return queryset

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("disciplinary-actions-list")
        self.view_id = "dis-container"
        if any(
            self.request.user.has_perm(perm)
            for perm in [
                "employee.change_disciplinaryaction",
                "employee.delete_disciplinaryaction",
                "employee.add_disciplinaryaction",
            ]
        ):
            self.action_method = "actions"


@method_decorator(login_required, name="dispatch")
class DisciplinaryActionsNav(HorillaNavView):
    """
    For nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("disciplinary-actions-list")
        if self.request.user.has_perm("employee.view_disciplinaryaction"):
            self.filter_body_template = "cbv/disciplinary_actions/filters.html"
        if self.request.user.has_perm("employee.add_disciplinaryaction"):
            self.create_attrs = f"""
                                hx-get='{reverse_lazy('create-actions')}'"
                                hx-target="#genericModalBody"
                                data-target="#genericModal"
                                data-toggle="oh-modal-toggle"
                                """

    nav_title = _("Disciplinary Actions")
    filter_instance = DisciplinaryActionFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    template_name = "generic/inline_nav.html"
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch, mirroring horilla_nav.html's
    # .oh-filter-modern styles) -- same treatment as every other panel
    # this session. DisciplinaryActionFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True


class DynamicActionTypeFormView(HorillaFormView):

    model = Actiontype
    form_class = ActiontypeForm
    new_display_title = _("Create Action Type")
    is_dynamic_create_view = True

    def form_valid(self, form: ActiontypeForm) -> HttpResponse:

        if form.is_valid():
            message = _("Action Created")
            messages.success(self.request, _(message))
            form.save()
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("employee.add_disciplinaryaction"), name="dispatch"
)
class DisciplinaryActionsFormView(HorillaFormView):
    """
    Form View
    """

    model = DisciplinaryAction
    form_class = DisciplinaryActionForm
    template_name = "cbv/disciplinary_actions/forms/create_form.html"
    new_display_title = _("Take An Action")
    dynamic_create_fields = [("action", DynamicActionTypeFormView)]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # form = super().get_form(self.form_class)
        if self.form.instance.pk:
            self.form_class(instance=self.form.instance)
            self.form_class.verbose_name = "Edit Action"
        context["form"] = self.form
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: DisciplinaryActionForm) -> HttpResponse:
        self.form_class(self.request.FILES)
        if form.is_valid():
            if form.instance.pk:
                message = _("Disciplinary action updated Successfully")
            else:
                employees = []
                employee_ids = form.cleaned_data["employee_id"]
                for employee in employee_ids:
                    user = employee.employee_user_id
                    employees.append(user)
                    with contextlib.suppress(Exception):
                        notify.send(
                            self.request.user.employee_get,
                            recipient=employees,
                            verb="Disciplinary action is taken on you.",
                            verb_ar="تم اتخاذ إجراء disziplinarisch ضدك.",
                            verb_de="Disziplinarische Maßnahmen wurden gegen Sie ergriffen.",
                            verb_es="Se ha tomado acción disciplinaria en tu contra.",
                            verb_fr="Des mesures disciplinaires ont été prises à votre encontre.",
                            redirect="/employee/disciplinary-actions/",
                            icon="chatbox-ellipses",
                        )
                message = _("Disciplinary action created Successfully")
            form.save()
            messages.success(self.request, _(message))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("employee.add_disciplinaryaction"), name="dispatch"
)
class DisciplinaryActionsFormDuplicate(HorillaFormView):
    """
    Duplicate form view
    """

    model = DisciplinaryAction
    form_class = DisciplinaryActionForm
    template_name = "cbv/disciplinary_actions/forms/create_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        original_object = DisciplinaryAction.objects.get(id=self.kwargs["pk"])
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

    def form_invalid(self, form: Any) -> HttpResponse:
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: DisciplinaryActionForm) -> HttpResponse:
        form = self.form_class(self.request.POST)
        if form.is_valid():
            message = _("Disciplinary action created Successfully")
            form.save()
            messages.success(self.request, _(message))
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class DisciplinaryActionsDetailView(HorillaDetailedView):
    """
    detail view of page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Employees"), "employee_detail"),
            (_("Login Block"), "block_option_col"),
            (_("Action Date"), "action_date_col"),
            (_("Attachments"), "attachments_col"),
            (_("Description"), "description"),
        ]

    cols = {
        "description": 12,
    }

    action_method = "detail_actions"

    model = DisciplinaryAction
    title = _("Details")
    header = {
        "title": "action",
        "subtitle": "",
        "avatar": "get_avatar",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = context.get("object")
        if instance is None:
            # No matching row (e.g. a stale/invalid pk) -- the parent's own
            # get_context_data already skips setting instance_ids for this
            # case, and its get() renders empty_template / redirects with
            # "No record found" once this returns, so there's nothing to
            # attach ordered_ids to here.
            return context
        instance.ordered_ids = context.get("instance_ids", [])
        return context
