from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.cbv.tab_shell import AttendanceTabContentShell
from base.methods import filter_own_records
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)
from payroll.filters import ReimbursementFilter
from payroll.forms.component_forms import ReimbursementForm
from payroll.models.models import Reimbursement


@method_decorator(login_required, name="dispatch")
class ReimbursementsView(TemplateView):
    """
    for reimbursements and encashments page
    """

    template_name = "cbv/reimbursements/reimbursements.html"


@method_decorator(login_required, name="dispatch")
class ReimbursementsAndEncashmentsTabView(HorillaTabView):
    """
    Tab View
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "reimbursmentContainer"
        self.tabs = [
            {
                "title": _("Reimbursements"),
                "url": f"{reverse('reimbursement-tab-shell')}",
            },
            {
                "title": _("Leave Encashments"),
                "url": f"{reverse('leave-encash-tab-shell')}",
            },
            {
                "title": _("Bonus Encashments"),
                "url": f"{reverse('bonus-encash-tab-shell')}",
            },
        ]

    def get_context_data(self, **kwargs):
        from payroll.filters import ReimbursementFilter
        from payroll.models.models import Reimbursement

        qs = Reimbursement.objects.all()
        if self.request.GET.get("search"):
            qs = ReimbursementFilter(
                data=self.request.GET, queryset=qs, request=self.request
            ).qs

        reimb_count = filter_own_records(
            self.request, qs.filter(type="reimbursement"), "payroll.view_reimbursement"
        ).count()
        leave_encash_count = filter_own_records(
            self.request,
            qs.filter(type="leave_encashment"),
            "payroll.view_reimbursement",
        ).count()
        bonus_encash_count = filter_own_records(
            self.request,
            qs.filter(type="bonus_encashment"),
            "payroll.view_reimbursement",
        ).count()

        reimb_url = reverse("reimbursement-tab-shell")
        leave_url = reverse("leave-encash-tab-shell")
        bonus_url = reverse("bonus-encash-tab-shell")

        for tab in self.tabs:
            url = tab.get("url", "")
            if reimb_url in url:
                tab["badge"] = reimb_count
            elif leave_url in url:
                tab["badge"] = leave_encash_count
            elif bonus_url in url:
                tab["badge"] = bonus_encash_count

        context = super().get_context_data(**kwargs)
        return context


@method_decorator(login_required, name="dispatch")
class ReimbursementsAndEncashmentsListView(HorillaListView):
    """
    list view
    """

    model = Reimbursement
    filter_class = ReimbursementFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # actions.html now renders edit/delete alongside approve/reject in one
        # column (it has its own internal permission checks per button), so
        # the separate Options column is no longer needed. action_method is
        # set unconditionally - action_col's own permission check still hides
        # approve/reject for users without change_reimbursement, while still
        # letting a self-service employee see their own edit/delete buttons.
        self.action_method = "actions_col"
        self.option_method = None

    row_status_indications = [
        (
            "rejected--dot",
            _("Rejected"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('rejected');
            $('[name=approved]').val('unknown').change();
            $('[name=requested]').val('unknown').change();
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
            $('[name=rejected]').val('unknown').change();
            $('[name=requested]').val('unknown').change();
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
            $('[name=rejected]').val('unknown').change();
            $('[name=approved]').val('unknown').change();
            $('#applyFilter').click();
            "
            """,
        ),
    ]

    row_status_class = "status-{status}"

    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Date"), "created_at"),
        (_("Title"), "title"),
        (_("Amount"), "amount"),
        (_("Status"), "get_status_display"),
        (_("Description"), "description"),
        (_("Comment"), "comment_col"),
    ]

    header_attrs = {
        "description": """
                        style="width:250px !important;"
                        """,
        "action": """
                        style="width:200px !important;"
                        """,
    }
    # Mirrors ReimbursementsNav.nested_group_by_fields below -- List and
    # Nav are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split). Inherited by
    # ReimbursementsListView/LeaveEncashmentsListView/
    # BonusEncashmentsListView below, covering all 3 tabs.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("title", _("Title")),
        ("amount", _("Amount")),
        ("status", _("Status")),
        ("created_at", _("Date")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employment Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
class ReimbursementsListView(ReimbursementsAndEncashmentsListView):

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Date"), "created_at"),
        (_("Amount"), "amount"),
        (_("Status"), "get_status_display"),
    ]

    row_attrs = """
                hx-get='{reimbursements_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-reimbursement")

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(type="reimbursement")
        queryset = filter_own_records(
            self.request, queryset, "payroll.view_reimbursement"
        )
        return queryset


@method_decorator(login_required, name="dispatch")
class LeaveEncashmentsListView(ReimbursementsAndEncashmentsListView):

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-leave-encash")

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Date"), "created_at"),
        (_("Amount"), "amount"),
        (_("Available days to encash"), "ad_to_encash"),
        (_("Carryforward to encash"), "cfd_to_encash"),
    ]

    columns = [
        column
        for column in ReimbursementsAndEncashmentsListView.columns
        if column[1] != "amount"
    ] + [
        (_("Amount"), "amount_col"),
        (_("Leave type"), "leave_type_id"),
        (_("Available days to encash"), "ad_to_encash"),
        (_("Carryforward to encash"), "cfd_to_encash"),
    ]

    row_attrs = """
                hx-get='{leave_encash_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(type="leave_encashment")
        queryset = filter_own_records(
            self.request, queryset, "payroll.view_reimbursement"
        )
        return queryset


@method_decorator(login_required, name="dispatch")
class BonusEncashmentsListView(ReimbursementsAndEncashmentsListView):

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-bonus-encash")

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Date"), "created_at"),
        (_("Amount"), "amount"),
        (_("Status"), "get_status_display"),
        (_("Bonus to encash"), "bonus_to_encash"),
    ]

    columns = [
        column
        for column in ReimbursementsAndEncashmentsListView.columns
        if column[1] != "amount"
    ] + [
        (_("Amount"), "amount_col"),
        (_("Bonus to encash"), "bonus_to_encash"),
    ]

    row_attrs = """
                hx-get='{bonus_encash_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(type="bonus_encashment")
        queryset = filter_own_records(
            self.request, queryset, "payroll.view_reimbursement"
        )
        return queryset


class _ReimbursementTabNavBase(HorillaNavView):
    """
    Shared Search/Filter/Create wiring for each Reimbursements/Encashments
    tab's own, independent Nav - nav_title/search_url/search_swap_target
    differ per tab, since each tab's heading should read as that tab's own
    name, not the page's combined name.
    """

    filter_instance = ReimbursementFilter()
    filter_form_context_name = "form"
    filter_body_template = "cbv/reimbursements/filter.html"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. ReimbursementFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    # Set by each subclass so its own Create button always creates a record
    # of that tab's own type, instead of showing a Type dropdown to pick from.
    create_type = ""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        create_url = reverse_lazy("reimbursement-create")
        if self.create_type:
            create_url = f"{create_url}?type={self.create_type}"
        self.create_attrs = f"""
                            hx-get="{create_url}"
                            hx-target="#genericModalBody"
                            data-target="#genericModal"
                            data-toggle="oh-modal-toggle"
                            """


@method_decorator(login_required, name="dispatch")
class ReimbursementNav(_ReimbursementTabNavBase):
    """
    Independent Nav for the Reimbursements tab.
    """

    nav_title = _("Reimbursements")
    create_type = "reimbursement"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-reimbursement")
        self.search_swap_target = "#reimbursementListContainer"


@method_decorator(login_required, name="dispatch")
class LeaveEncashNav(_ReimbursementTabNavBase):
    """
    Independent Nav for the Leave Encashments tab.
    """

    nav_title = _("Leave Encashments")
    create_type = "leave_encashment"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-leave-encash")
        self.search_swap_target = "#leaveEncashListContainer"


@method_decorator(login_required, name="dispatch")
class BonusEncashNav(_ReimbursementTabNavBase):
    """
    Independent Nav for the Bonus Encashments tab.
    """

    nav_title = _("Bonus Encashments")
    create_type = "bonus_encashment"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-bonus-encash")
        self.search_swap_target = "#bonusEncashListContainer"


class ReimbursementTabShell(AttendanceTabContentShell):
    nav_url_name = "reimbursement-nav"
    container_id = "reimbursementListContainer"
    tabs_root_id = "reimbursmentContainer"


class LeaveEncashTabShell(AttendanceTabContentShell):
    nav_url_name = "leave-encash-nav"
    container_id = "leaveEncashListContainer"
    tabs_root_id = "reimbursmentContainer"


class BonusEncashTabShell(AttendanceTabContentShell):
    nav_url_name = "bonus-encash-nav"
    container_id = "bonusEncashListContainer"
    tabs_root_id = "reimbursmentContainer"

    # Mirrors ReimbursementsAndEncashmentsListView.nested_group_by_fields
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("title", _("Title")),
        ("amount", _("Amount")),
        ("status", _("Status")),
        ("created_at", _("Date")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employment Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
class ReimbursementsDetailView(HorillaDetailedView):
    """
    detail view of reimbursements
    """

    body = [
        (_("Date"), "created_at"),
        (_("Amount"), "amount"),
        (_("Status"), "get_status_display"),
        (_("Attachments"), "attachments_col"),
        (_("Description"), "description"),
    ]
    cols = {
        "description": 12,
    }

    action_method = "detail_action_col"

    model = Reimbursement
    title = _("Details")
    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "title",
        "avatar": "employee_id__get_avatar",
    }


@method_decorator(login_required, name="dispatch")
class LeaveEncashmentsDetailedView(ReimbursementsDetailView):

    position = 3
    body = [
        body for body in ReimbursementsDetailView.body if body[1] != "attachments_col"
    ]
    body.insert(position, (_("Leave type"), "leave_type_id"))
    body.insert(position + 1, (_("Available days to encash"), "ad_to_encash"))
    body.insert(position + 2, (_("Carryforward to encash"), "cfd_to_encash"))


@method_decorator(login_required, name="dispatch")
class BonusEncashmentsDetailedView(ReimbursementsDetailView):

    body = [
        body for body in ReimbursementsDetailView.body if body[1] != "attachments_col"
    ]
    body.insert(3, (_("Bonus to encash"), "bonus_to_encash"))


@method_decorator(login_required, name="dispatch")
class ReimbursementsFormView(HorillaFormView):
    """
    Create and edit form for reimbursements
    """

    model = Reimbursement
    form_class = ReimbursementForm
    template_name = "cbv/reimbursements/forms.html"

    # Maps Reimbursement.type -> the singular, tab-matching label to show
    # on the form (Reimbursement.get_type_display() exists too, but its
    # "Bonus Point Encashment" wording doesn't match the Bonus Encashments
    # tab this form was opened from).
    type_display_titles = {
        "reimbursement": _("Reimbursement"),
        "leave_encashment": _("Leave Encashment"),
        "bonus_encashment": _("Bonus Encashment"),
    }

    @property
    def new_display_title(self):
        # Each tab's Create button passes ?type=... (see
        # _ReimbursementTabNavBase) so the title reflects the tab it was
        # opened from; a generic fallback covers reaching this form any
        # other way.
        create_type = self.request.GET.get("type")
        return self.type_display_titles.get(
            create_type, _("Reimbursement / Encashment")
        )

    def get_context_data(self, **kwargs):
        """
        Get context data for rendering the form view.
        """
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            title = self.type_display_titles.get(
                self.form.instance.type, _("Reimbursement / Encashment")
            )
            self.form_class.verbose_name = _("Update %(title)s") % {"title": title}
        return context

    def form_valid(self, form: ReimbursementForm) -> HttpResponse:
        """
        Handle a valid form submission.
        If the form is valid, save the instance and display a success message.
        """
        if form.is_valid():
            title = self.type_display_titles.get(
                form.instance.type, _("Reimbursement / Encashment")
            )
            if form.instance.pk:
                message = _("%(title)s updated successfully") % {"title": title}
            else:
                message = _("%(title)s created successfully") % {"title": title}
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)
