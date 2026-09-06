from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.cbv.tab_shell import AttendanceTabContentShell
from base.methods import filtersubordinates, is_reportingmanager
from helpdesk.filter import TicketFilter
from helpdesk.models import Ticket
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.kanban import HorillaKanbanView
from horilla_views.generic.cbv.views import (
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)


@method_decorator(login_required, name="dispatch")
class TicketPipelineView(TemplateView):
    """
    Tickets page view
    """

    template_name = "cbv/pipeline/ticket_section_view.html"


class _TicketTabNavBase(HorillaNavView):
    """
    Shared Filter/Group-by/Actions/Create wiring for each Tickets tab's own,
    independent Nav - only search_url/search_swap_target/view_types differ
    per tab.
    """

    nav_title = _("Tickets")
    filter_body_template = "cbv/pipeline/ticket_filter_form.html"
    filter_instance = TicketFilter()
    filter_form_context_name = "form"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. TicketFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Owner")),
        ("ticket_type", _("Ticket Type")),
        ("status", _("Status")),
        ("priority", _("Priority")),
        ("tags", _("Tags")),
        ("assigned_to", _("Assigner")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]

    actions = [
        {
            "action": _("Archive"),
            "attrs": """
                href="#"
                role="button"
                class="oh-dropdown__link"
                onclick = "ticketBulkArchive(event)"
            """,
        },
        {
            "action": _("Unarchive"),
            "attrs": """
                href="#"
                role="button"
                class="oh-dropdown__link"
                onclick = "ticketBulkUnArchive(event)"
            """,
        },
        {
            "action": _("Delete"),
            "attrs": """
                href="#"
                role="button"
                class="oh-dropdown__link oh-dropdown__link--danger"
                onclick = "ticketsBulkDelete(event)"
            """,
        },
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.create_attrs = f"""
            class="oh-btn oh-btn--secondary"
            hx-get="{reverse('ticket-create')}"
            hx-target="#objectCreateModalTarget"
            data-toggle="oh-modal-toggle"
            data-target="#objectCreateModal"
        """


@method_decorator(login_required, name="dispatch")
class MyTicketsNav(_TicketTabNavBase):
    """
    Independent Nav for the My Tickets tab.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_url = reverse("my-tickets-list")
        self.search_swap_target = "#myTicketsListContainer"
        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": f'{reverse("my-tickets-list")}?view_type=list',
                "attrs": """ title='List' """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": f'{reverse("my-tickets-card")}?view_type=card',
                "attrs": """ title='Card' """,
            },
        ]


@method_decorator(login_required, name="dispatch")
class SuggestedTicketsNav(_TicketTabNavBase):
    """
    Independent Nav for the Suggested Tickets tab.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_url = reverse("suggested-tickets-list")
        self.search_swap_target = "#suggestedTicketsListContainer"
        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": f'{reverse("suggested-tickets-list")}?view_type=list',
                "attrs": """ title='List' """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": f'{reverse("suggested-tickets-card")}?view_type=card',
                "attrs": """ title='Card' """,
            },
        ]


@method_decorator(login_required, name="dispatch")
class AllTicketsNav(_TicketTabNavBase):
    """
    Independent Nav for the All Tickets tab.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_url = reverse("all-tickets-list")
        self.search_swap_target = "#allTicketsListContainer"
        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": f'{reverse("all-tickets-list")}?view_type=list',
                "attrs": """ title='List' """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": f'{reverse("all-tickets-card")}?view_type=card',
                "attrs": """ title='Card' """,
            },
        ]


class MyTicketsTabShell(AttendanceTabContentShell):
    nav_url_name = "my-tickets-nav"
    container_id = "myTicketsListContainer"
    tabs_root_id = "ticketPipelineContainer"


class SuggestedTicketsTabShell(AttendanceTabContentShell):
    nav_url_name = "suggested-tickets-nav"
    container_id = "suggestedTicketsListContainer"
    tabs_root_id = "ticketPipelineContainer"


class AllTicketsTabShell(AttendanceTabContentShell):
    nav_url_name = "all-tickets-nav"
    container_id = "allTicketsListContainer"
    tabs_root_id = "ticketPipelineContainer"


@method_decorator(login_required, name="dispatch")
class TicketTabView(HorillaTabView):
    """
    Pipeline List View
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.view_id = "ticketPipelineContainer"

        if not self.request or not self.request.user.is_authenticated:
            self.tabs = []
            return

        extra_params = self.request.GET.copy()
        extra_params.pop("view", None)
        query_string = extra_params.urlencode()

        def with_query(url):
            return f"{url}?{query_string}" if query_string else url

        employee = self.request.user.employee_get
        base_qs = Ticket.objects.all()
        if self.request.GET.get("is_active") != "false":
            base_qs = base_qs.filter(is_active=True)

        my_tickets_count = TicketFilter(
            self.request.GET, queryset=base_qs.filter(employee_id=employee)
        ).qs.count()

        suggested_qs = base_qs.none()
        if hasattr(employee, "employee_work_info"):
            work_info = employee.employee_work_info
            department = work_info.department_id
            job_position = work_info.job_position_id

            if department:
                suggested_qs |= base_qs.filter(
                    raised_on=department.id, assigning_type="department"
                )

            if job_position:
                suggested_qs |= base_qs.filter(
                    raised_on=job_position.id, assigning_type="job_position"
                )

        suggested_qs |= base_qs.filter(
            raised_on=employee.id, assigning_type="individual"
        )
        suggested_tickets_count = TicketFilter(
            self.request.GET, queryset=suggested_qs.distinct()
        ).qs.count()

        self.tabs = [
            {
                "title": _("My Tickets"),
                "url": with_query(reverse("my-tickets-tab-shell")),
                "badge": my_tickets_count,
            },
            {
                "title": _("Suggested Tickets"),
                "url": with_query(reverse("suggested-tickets-tab-shell")),
                "badge": suggested_tickets_count,
            },
        ]

        if is_reportingmanager(self.request) or self.request.user.has_perm(
            "helpdesk.view_ticket"
        ):
            all_tickets_qs = filtersubordinates(
                self.request, base_qs, "helpdesk.view_ticket"
            )
            all_tickets_count = TicketFilter(
                self.request.GET, queryset=all_tickets_qs
            ).qs.count()
            self.tabs.append(
                {
                    "title": _("All Tickets"),
                    "url": with_query(reverse("all-tickets-tab-shell")),
                    "badge": all_tickets_count,
                }
            )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["show_filter_tags"] = True
        return context


@method_decorator(login_required, name="dispatch")
class TicketListBase(HorillaListView):
    """
    Shared columns/actions/queryset base for each Tickets tab's own list.
    """

    model = Ticket
    filter_class = TicketFilter
    filter_keys_to_remove = ["ticket_tab", "view_type"]
    # custom_empty_template = "cbv/pipeline/empty_list.html"
    bulk_update_fields = [
        "ticket_type",
        "status",
        "priority",
        "assigned_to",
        "tags",
    ]
    columns = [
        (_("Ticket ID"), "get_ticket_id_col"),
        (_("Title"), "title"),
        (_("Owner"), "employee_id"),
        (_("Type"), "ticket_type"),
        (_("Forward to"), "get_raised_on"),
        (_("Assigned to"), "get_assigned_to"),
        (_("Status"), "get_status_col"),
        (_("Priority"), "get_priority_stars"),
        (_("Tags"), "get_tags_col"),
    ]

    row_attrs = """
        onclick="window.location.href = `{get_ticket_detail_url}`"
        class = "{row_colors}"
    """

    action_method = """ticket_action_col"""
    header_attrs = {"action": "style='width:170px'"}
    selected_instances_key_id = "selectedTickets"

    row_status_indications = [
        (
            "canceled--dot",
            _("Canceled"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('canceled');
            $('[name=new]').val('unknown').change();
            $('[name=in_progress]').val('unknown').change();
            $('[name=on_hold]').val('unknown').change();
            $('[name=resolved]').val('unknown').change();
            $('#applyFilter').click();
            "

            """,
        ),
        (
            "resolved--dot",
            _("Resolved"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('resolved');
            $('[name=new]').val('unknown').change();
            $('[name=in_progress]').val('unknown').change();
            $('[name=on_hold]').val('unknown').change();
            $('[name=canceled]').val('unknown').change();
            $('#applyFilter').click();
            "

            """,
        ),
        (
            "on_hold--dot",
            _("On Hold"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('on_hold');
            $('[name=new]').val('unknown').change();
            $('[name=in_progress]').val('unknown').change();
            $('[name=resolved]').val('unknown').change();
            $('[name=canceled]').val('unknown').change();
            $('#applyFilter').click();
            "

            """,
        ),
        (
            "in_progress--dot",
            _("In Progress"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('in_progress');
            $('[name=new]').val('unknown').change();
            $('[name=on_hold]').val('unknown').change();
            $('[name=resolved]').val('unknown').change();
            $('[name=canceled]').val('unknown').change();
            $('#applyFilter').click();
            "

            """,
        ),
        (
            "new--dot",
            _("New"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('new');
            $('[name=on_hold]').val('unknown').change();
            $('[name=in_progress]').val('unknown').change();
            $('[name=resolved]').val('unknown').change();
            $('[name=canceled]').val('unknown').change();
            $('#applyFilter').click();
            "

            """,
        ),
    ]
    row_status_class = "new-{new} in_progress-{in_progress} on_hold-{on_hold} resolved-{resolved} canceled-{canceled}"

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.GET.get("is_active") != "false":
            queryset = queryset.filter(is_active=True)
        return queryset


@method_decorator(login_required, name="dispatch")
class MyTicketsList(TicketListBase):
    """
    List view of the My Tickets tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("my-tickets-list")
        self.request.GET = self.request.GET.copy()
        self.request.GET["ticket_tab"] = "my_tickets"

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(employee_id=self.request.user.employee_get)


@method_decorator(login_required, name="dispatch")
class SuggestedTicketsList(TicketListBase):
    """
    List view of the Suggested Tickets tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("suggested-tickets-list")
        self.request.GET = self.request.GET.copy()
        self.request.GET["ticket_tab"] = "suggested_tickets"

    def get_queryset(self):
        queryset = super().get_queryset()
        employee = self.request.user.employee_get
        qs_cpy = queryset
        queryset = queryset.none()
        if hasattr(employee, "employee_work_info"):
            work_info = employee.employee_work_info
            department = work_info.department_id
            job_position = work_info.job_position_id

            if department:
                queryset |= qs_cpy.filter(
                    raised_on=department.id, assigning_type="department"
                )

            if job_position:
                queryset |= qs_cpy.filter(
                    raised_on=job_position.id, assigning_type="job_position"
                )

        queryset |= qs_cpy.filter(raised_on=employee.id, assigning_type="individual")
        return queryset.distinct()


@method_decorator(login_required, name="dispatch")
class AllTicketsList(TicketListBase):
    """
    List view of the All Tickets tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("all-tickets-list")
        self.request.GET = self.request.GET.copy()
        self.request.GET["ticket_tab"] = "all_tickets"
        if (
            self.request.user.has_perm("helpdesk.view_claimrequest")
            or self.request.user.has_perm("helpdesk.change_claimrequest")
            or self.request.user.has_perm("helpdesk.change_ticket")
            or self.request.user.has_perm("helpdesk.delete_ticket")
        ):
            self.action_method = "ticket_action_col"
        else:
            self.action_method = None

    def get_queryset(self):
        queryset = super().get_queryset()
        return filtersubordinates(self.request, queryset, "helpdesk.view_ticket")


@method_decorator(login_required, name="dispatch")
class TicketCardBase(HorillaKanbanView):
    """
    Shared columns/actions/queryset base for each Tickets tab's own kanban
    board.
    """

    model = Ticket
    filter_class = TicketFilter
    group_key = "status"
    records_per_page = 10
    show_kanban_confirmation = False
    filter_keys_to_remove = ["ticket_tab", "view_type"]

    details = {
        "title": "{title} ({ticket_type__prefix}-{pk})",
        "Owner": "{employee_id__get_full_name}",
        "Priority": "{get_priority_stars}",
    }

    kanban_attrs = """ onclick="window.location.href = `{get_ticket_detail_url}`" """

    action_method = "kanban_action_method"

    def get_queryset(self):
        self.queryset = super().get_queryset()
        if self.request.GET.get("is_active") != "false":
            self.queryset = self.queryset.filter(is_active=True)
        return self.queryset


@method_decorator(login_required, name="dispatch")
class MyTicketsCard(TicketCardBase):
    """
    Kanban board of the My Tickets tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("my-tickets-card")
        self.request.GET = self.request.GET.copy()
        self.request.GET["ticket_tab"] = "my_tickets"

    def get_queryset(self):
        self.queryset = (
            super().get_queryset().filter(employee_id=self.request.user.employee_get)
        )
        return self.queryset


@method_decorator(login_required, name="dispatch")
class SuggestedTicketsCard(TicketCardBase):
    """
    Kanban board of the Suggested Tickets tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("suggested-tickets-card")
        self.request.GET = self.request.GET.copy()
        self.request.GET["ticket_tab"] = "suggested_tickets"

    def get_queryset(self):
        base_qs = super().get_queryset()
        employee = self.request.user.employee_get
        queryset = base_qs.none()
        if hasattr(employee, "employee_work_info"):
            work_info = employee.employee_work_info
            department = work_info.department_id
            job_position = work_info.job_position_id

            if department:
                queryset |= base_qs.filter(
                    raised_on=department.id, assigning_type="department"
                )

            if job_position:
                queryset |= base_qs.filter(
                    raised_on=job_position.id, assigning_type="job_position"
                )

        queryset |= base_qs.filter(raised_on=employee.id, assigning_type="individual")
        self.queryset = queryset.distinct()
        return self.queryset


@method_decorator(login_required, name="dispatch")
class AllTicketsCard(TicketCardBase):
    """
    Kanban board of the All Tickets tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("all-tickets-card")
        self.request.GET = self.request.GET.copy()
        self.request.GET["ticket_tab"] = "all_tickets"

    def get_queryset(self):
        queryset = super().get_queryset()
        self.queryset = filtersubordinates(
            self.request, queryset, "helpdesk.view_ticket"
        )
        return self.queryset
