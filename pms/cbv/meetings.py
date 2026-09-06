"""
Meetings page
"""

import contextlib
from typing import Any

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from notifications.signals import notify
from pms.filters import MeetingsFilter
from pms.forms import MeetingResponseForm, MeetingsForm
from pms.models import Meetings


@method_decorator(login_required, name="dispatch")
class MeetingsView(TemplateView):
    """
    for meeting page
    """

    template_name = "cbv/meetings/meetings.html"


@method_decorator(login_required, name="dispatch")
class MeetingsList(HorillaListView):
    """
    List view of the page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("meetings-list")
        self.view_id = "meetingManagerContainer"

    def get_queryset(self):
        queryset = super().get_queryset()
        active = (
            True
            if self.request.GET.get("is_active", True)
            in ["unknown", "True", "true", True]
            else False
        )
        queryset = queryset.filter(is_active=active)

        if not self.request.user.has_perm("pms.view_meetings"):
            employee_id = self.request.user.employee_get
            queryset = queryset.filter(
                Q(employee_id=employee_id) | Q(manager=employee_id)
            ).distinct()
            return queryset.order_by("-id")
        return queryset.order_by("-id")

    model = Meetings
    filter_class = MeetingsFilter

    header_attrs = {
        "title_col": 'style="min-width:280px;width:32%;"',
        "mom_col": 'style="width:90px;max-width:110px;"',
        "get_model_history": 'style="width:70px;max-width:80px;"',
        "action": 'style="width:200px"',
    }

    columns = [
        (_("Title"), "title_col"),
        (_("Employees"), "employees_col"),
        (_("Managers"), "managers_col"),
        (_("Date"), "date_col"),
        (_("MoM"), "mom_col"),
    ]

    sortby_mapping = [("Date", "date_col")]

    bulk_update_fields = ["manager"]

    action_method = "action_col"

    row_attrs = """
                {diff_cell}
                class="oh-permission-table--collapsed"
                hx-get='{meeting_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    # Mirrors MeetingsNav.nested_group_by_fields below -- List and Nav
    # are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split). "Employee",
    # "Manager" and "Answerable Employees" are deliberately left out:
    # they're ManyToManyFields, and the nested engine's
    # `values(*fields).annotate(Count("pk"))` aggregate would fan out one
    # row per related employee, double-counting meetings with more than
    # one assigned. That also rules out the filter's
    # employee_id__employee_work_info__* paths (Department, Job Position,
    # etc.), since those traverse the same M2M.
    nested_group_by_fields = [
        ("title", _("Title")),
        ("date", _("Date")),
        ("question_template", _("Question Template")),
        ("company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
class MeetingsNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("meetings-list")
        if self.request.user.has_perm("pms.add_meetings"):
            self.create_attrs = f"""
                            hx-get='{reverse_lazy('create-meeting')}'
                            data-toggle="oh-modal-toggle"
                            data-target="#genericModal"
                            hx-target="#genericModalBody"
                            """

    nav_title = _("Meetings")
    filter_instance = MeetingsFilter()
    filter_body_template = "cbv/meetings/filter.html"
    filter_form_context_name = "filter_form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. MeetingsFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    # Mirrors MeetingsList.nested_group_by_fields
    nested_group_by_fields = [
        ("title", _("Title")),
        ("date", _("Date")),
        ("question_template", _("Question Template")),
        ("company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
class MeetingsDetailedView(HorillaDetailedView):
    """
    detail view of page
    """

    cols = {
        "mom_detail_col": 12,
        "employ_detail_col": 12,
        "manager_detail_col": 12,
        "answerable_col": 12,
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Date"), "date"),
            (_("Question Template"), "question_template"),
            (_("Managers"), "manager_detail_col"),
            (_("Employees"), "employ_detail_col"),
            (_("Answerable employees"), "answerable_col"),
            (_("Minutes of Meeting"), "mom_detail_col"),
        ]

    action_method = "detail_action"

    model = Meetings
    title = _("Details")
    header = {
        "title": "title",
        "subtitle": "Meeting",
        "avatar": "get_avatar",
    }


@method_decorator(login_required, name="dispatch")
class MeetingsFormView(HorillaFormView):
    """
    Form View
    """

    model = Meetings
    form_class = MeetingsForm
    template_name = "cbv/meetings/forms/meet_create.html"
    new_display_title = _("Meetings")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form_class(initial={"manager": self.request.user.employee_get})
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Meeting")
            self.form_class(instance=self.form.instance)
        context["form"] = self.form
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        # form = self.form_class(self.request.POST)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Meeting")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: MeetingsForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Meeting updated successfully")
            else:
                message = _("Meeting added successfully")
            instance = form.save()
            managers = [
                manager.employee_user_id for manager in form.cleaned_data["manager"]
            ]
            answer_employees = [
                answer_emp.employee_user_id
                for answer_emp in form.cleaned_data["answer_employees"]
            ]
            employees = form.cleaned_data["employee_id"]
            employees = [
                employee.employee_user_id
                for employee in employees.exclude(
                    id__in=form.cleaned_data["answer_employees"]
                )
            ]
            messages.success(self.request, _(message))
            with contextlib.suppress(Exception):
                notify.send(
                    self.request.user.employee_get,
                    recipient=managers,
                    verb=f"You have been added as a manager for the meeting {instance.title}",
                    verb_ar=f"لقد تمت إضافتك كمدير للاجتماع {instance.title}",
                    verb_de=f"Sie wurden als Manager für das Meeting {instance.title} hinzugefügt",
                    verb_es=f"Se le ha agregado como administrador de la reunión {instance.title}",
                    verb_fr=f"Vous avez été ajouté en tant que responsable de réunion {instance.title}",
                    icon="information",
                    redirect=reverse("view-meetings") + f"?search={instance.title}",
                )
            with contextlib.suppress(Exception):
                notify.send(
                    self.request.user.employee_get,
                    recipient=employees,
                    verb=f"You have been added to the meeting {instance.title}",
                    verb_ar=f"لقد تمت إضافتك إلى اجتماع {instance.title}.",
                    verb_de=f"Sie wurden zur {instance.title} Besprechung hinzugefügt",
                    verb_es=f"Te han agregado a la reunión {instance.title}",
                    verb_fr=f"Vous avez été ajouté à la réunion {instance.title}",
                    icon="information",
                    redirect=reverse("view-meetings") + f"?search={instance.title}",
                )
            with contextlib.suppress(Exception):
                notify.send(
                    self.request.user.employee_get,
                    recipient=answer_employees,
                    verb=f"You have been added as an answerable employee for the meeting {instance.title}",
                    verb_ar=f"لقد تمت إضافتك كموظف مسؤول عن الاجتماع {instance.title}",
                    verb_de=f"Du wurden als Mitarbeiter zum Ausfüllen für das {instance.title}-Meeting hinzugefügt",
                    verb_es=f"Se le ha agregado como empleado responsable de la reunión {instance.title}",
                    verb_fr=f"Vous avez été ajouté en tant que employé responsable pour la réunion {instance.title}",
                    icon="information",
                    redirect=reverse("view-meetings") + f"?search={instance.title}",
                )
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class MeetingResponseFormView(HorillaFormView):
    """
    Form View
    """

    model = Meetings
    form_class = MeetingResponseForm
    # template_name = "cbv/recruitment/forms/create_form.html"
    new_display_title = _("Add Response")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        meet_id = self.kwargs.get("id")
        meeting = Meetings.objects.filter(id=meet_id).first()
        form = self.form_class(instance=meeting)
        context["form"] = form
        return context

    def form_valid(self, form: MeetingResponseForm) -> HttpResponse:
        meet_id = self.kwargs.get("id")
        meeting = Meetings.objects.filter(id=meet_id).first()
        if not meeting:
            messages.error(self.request, _("Meeting not found."))
            return self.HttpResponse()
        if form.is_valid():
            message = _("Response added successfully")
            response = self.request.POST.get("response")
            meeting.response = response
            meeting.save()
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)
