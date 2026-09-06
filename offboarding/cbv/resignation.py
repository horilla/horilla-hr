"""
CBV of resigantions page
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla.methods import handle_no_permission
from horilla_views.cbv_methods import (
    check_feature_enabled,
    login_required,
    permission_required,
)
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from offboarding.filters import LetterFilter
from offboarding.forms import ResignationLetterForm
from offboarding.models import Offboarding, OffboardingGeneralSetting, ResignationLetter


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("offboarding.view_resignationletter"), name="dispatch"
)
@method_decorator(
    check_feature_enabled("resignation_request", OffboardingGeneralSetting),
    name="dispatch",
)
class ResignationLettersView(TemplateView):
    """
    for reimbursements and encashments page
    """

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        offboardings = Offboarding.objects.all()
        context["offboardings"] = offboardings
        return context

    template_name = "cbv/resignation/resignation.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("offboarding.view_resignationletter"), name="dispatch"
)
@method_decorator(
    check_feature_enabled("resignation_request", OffboardingGeneralSetting),
    name="dispatch",
)
class ResignationListView(HorillaListView):
    """
    list view
    """

    model = ResignationLetter
    filter_class = LetterFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-resignation-request")
        if self.request.user.has_perm("offboarding.change_resignationletter"):
            self.action_method = "actions_column"

    option_method = "option_column"

    row_status_indications = [
        (
            "rejected--dot",
            _("Rejected"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('rejected');
            $('#applyFilter').click();
            "
            """,
        ),
        (
            "approved--dot",
            _("Approved"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('approved');
            $('#applyFilter').click();
            "
            """,
        ),
        (
            "requested--dot",
            _("Requested"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('requested');
            $('#applyFilter').click();
            "
            """,
        ),
    ]

    row_status_class = "status-{status}"

    row_attrs = """
                hx-get='{get_detail_url}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """
    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Title"), "title"),
        (_("Planned To Leave"), "planned_to_leave_on"),
        (_("Status"), "get_status"),
        (_("Description"), "description_col"),
    ]

    header_attrs = {
        "description_col": """
                            style="width:200px !important"
                            """
    }

    sortby_mapping = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Planned To Leave"), "planned_to_leave_on"),
        (_("Status"), "get_status"),
    ]

    # Mirrors ResinationLettersNav.nested_group_by_fields below -- List
    # and Nav are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split).
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("planned_to_leave_on", _("Planned to leave date")),
        ("status", _("Status")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("offboarding.view_resignationletter"), name="dispatch"
)
@method_decorator(
    check_feature_enabled("resignation_request", OffboardingGeneralSetting),
    name="dispatch",
)
class ResinationLettersNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-resignation-request")
        request = self.request
        if request:
            selected_company = request.session.get("selected_company")
            if selected_company and selected_company != "all":
                general_setting = OffboardingGeneralSetting.objects.filter(
                    company_id=selected_company
                ).first()
            else:
                general_setting = OffboardingGeneralSetting.objects.filter(
                    company_id=None
                ).first()
            feature_enabled = getattr(general_setting, "resignation_request", False)
            if not feature_enabled and not request.user.is_superuser:
                can_create = False
            else:
                can_create = (
                    feature_enabled
                    or request.user.is_superuser
                    or request.user.has_perm("offboarding.add_resignationletter")
                )
            if can_create:
                self.create_attrs = f"""
                    hx-get="{reverse_lazy("resignation-requests-create")}"
                    hx-target="#genericModalBody"
                    data-target="#genericModal"
                    data-toggle="oh-modal-toggle"
                """

    nav_title = _("Resignations")
    filter_instance = LetterFilter()
    filter_form_context_name = "form"
    filter_body_template = "cbv/resignation/filter.html"
    search_swap_target = "#listContainer"
    apply_first_filter = False
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. LetterFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("planned_to_leave_on", _("Planned to leave date")),
        ("status", _("Status")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
    ]

    # Mirrors ResignationListView.nested_group_by_fields
    nested_group_by_fields = group_by_fields


@method_decorator(login_required, name="dispatch")
class ResignationLettersFormView(HorillaFormView):
    """
    Create and edit form for resignations
    """

    model = ResignationLetter
    form_class = ResignationLetterForm
    new_display_title = _("Create Resignation Letter")

    def dispatch(self, request, *args, **kwargs):
        selected_company = request.session.get("selected_company")
        if selected_company and selected_company != "all":
            general_setting = OffboardingGeneralSetting.objects.filter(
                company_id=selected_company
            ).first()
        else:
            general_setting = OffboardingGeneralSetting.objects.filter(
                company_id=None
            ).first()
        feature_enabled = getattr(general_setting, "resignation_request", False)
        if not feature_enabled and not request.user.is_superuser:
            can_create = False
        else:
            can_create = (
                request.user.is_superuser
                or request.user.has_perm("offboarding.add_resignationletter")
                or feature_enabled
            )
        if not can_create:
            return handle_no_permission(
                request, message=_("Feature is not enabled on the settings")
            )
        pk = kwargs.get("pk")
        if pk:
            instance = ResignationLetter.objects.filter(pk=pk).first()
            if instance and not (
                request.user.has_perm("offboarding.change_resignationletter")
                or instance.employee_id == request.user.employee_get
            ):
                return render(request, "no_perm.html")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: ResignationLetterForm) -> HttpResponse:
        """
        Handle a valid form submission.
        If the form is valid, save the instance and display a success message.
        """
        if form.is_valid():
            if form.instance.pk:
                message = _("Resignation updated successfully")
            else:
                message = _("Resignation created successfully")
            if form.save() is not None:
                messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("offboarding.view_resignationletter"), name="dispatch"
)
@method_decorator(
    check_feature_enabled("resignation_request", OffboardingGeneralSetting),
    name="dispatch",
)
class ResignationLetterDetailView(HorillaDetailedView):
    """
    detail view of resignations
    """

    template_name = "cbv/resignation/detail_view.html"

    def get_context_data(self, **kwargs: Any):
        """
        To set title.
        """
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get("pk")
        letter = ResignationLetter.objects.get(id=pk)
        title = context["resignationletter"].title
        context["title"] = title
        context["letter"] = letter
        return context

    body = [
        (_("Planned To Leave"), "planned_to_leave_on"),
        (_("Status"), "get_status_badge"),
        (_("Description"), "detail_description_col"),
    ]

    cols = {"detail_description_col": 12}

    action_method = "actions_column"

    model = ResignationLetter
    # title = _("Details")
    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "resignation_subtitle",
        "avatar": "employee_id__get_avatar",
    }
