"""
this page is handling the cbv methods for Job Position in settings
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.filters import DepartmentViewFilter
from base.forms import JobPositionForm
from base.models import Department, JobPosition
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="base.view_jobposition"), name="dispatch")
class JobPositionListView(HorillaListView):
    """
    list view for job positions in settings
    """

    columns = [
        (_("Department"), "get_department_col"),
        (_("Job Position"), "get_job_position_col"),
    ]

    row_attrs = """
        class="oh-sticky-table__tr oh-permission-table__tr oh-permission-table--collapsed"
        data-label="Job Position"
        data-count="{toggle_count}"
    """

    header_attrs = {
        "get_department_col": 'style="width:300px !important; "',
        "get_job_position_col": 'style="width:300px !important; "',
    }

    model = Department
    filter_class = DepartmentViewFilter
    show_toggle_form = False
    # Department is now the accordion group header, not a selectable row --
    # see base/templates/cbv/settings/job_position_group_by.html.
    bulk_select_option = False
    template_name = "cbv/settings/job_position_group_by.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("job-position-list")
        self.view_id = "job_position"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="base.view_jobposition"), name="dispatch")
class JobPositionNavView(HorillaNavView):
    """
    nav bar of the job position view
    """

    nav_title = _("Job Position")
    search_swap_target = "#listContainer"
    filter_instance = DepartmentViewFilter()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("job-position-list")
        if self.request.user.has_perm("base.add_jobposition"):
            self.create_attrs = f"""
                onclick = "event.stopPropagation();"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                hx-get="{reverse('job-position-create-form')}"
            """


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="base.view_jobposition"), name="dispatch")
class JobPositionDetailView(HorillaDetailedView):
    """
    detail view for job position, also registered as the related-object-link
    target for JobPosition via detail_view_url_name
    """

    model = JobPosition
    detail_view_url_name = "job-position-detail-view"
    detail_view_permission = "base.view_jobposition"
    title = _("Job Position")

    header = {
        "title": "job_position",
        "subtitle": "department_id",
        "avatar": "",
    }

    body = [
        (_("Job Position"), "job_position"),
        (_("Department"), "department_id"),
        (_("Headcount"), "headcount"),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="base.view_jobposition"), name="dispatch")
class JobPositionCreateForm(HorillaFormView):
    """
    form view for creating job position in settings
    """

    model = JobPosition
    form_class = JobPositionForm
    new_display_title = _("Create Job Position")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form.fields["department_id"].initial = self.form.instance.department_id
            self.form_class.verbose_name = _("Update Job Position")
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Job Position")
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: JobPositionForm) -> HttpResponse:
        job_position = form.instance
        if self.form.instance.pk and form.is_valid():
            if job_position is not None:
                department_id = form.cleaned_data.get("department_id")
                if department_id:
                    job_position.department_id = department_id
                job_position.save()
                messages.success(self.request, _("Job position updated."))
        elif (
            not form.instance.pk
            and form.data.getlist("department_id")
            and form.data.get("job_position")
        ):
            form.save(commit=True)
        return self.HttpResponse()
