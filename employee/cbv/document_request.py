"""
This page handles the cbv methods for document request page
"""

import os
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

from base.cbv.work_shift_tab import ProfileTabShellView
from base.methods import (
    choosesubordinates,
    get_key_instances,
    humanize_filter_tags,
    is_reportingmanager,
    paginator_qry,
)
from employee.filters import DocumentPipelineFilter, DocumentRequestFilter
from employee.models import Employee
from horilla.decorators import manager_can_enter
from horilla.http.response import HorillaRedirect
from horilla_documents.forms import DocumentForm
from horilla_documents.forms import DocumentRejectCbvForm as RejectForm
from horilla_documents.forms import DocumentRequestForm, DocumentUpdateForm
from horilla_documents.models import Document, DocumentRequest
from horilla_views import models as horilla_views_models
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    saved_filter_path_query,
)
from horilla_views.generic.cbv.pipeline import Pipeline
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
)
from notifications.signals import notify

BLOCKED_EXTENSIONS = {
    ".html",
    ".htm",
    ".js",
    ".svg",
    ".xml",
    ".php",
    ".py",
    ".sh",
    ".exe",
}


def htmx_refresh_document_request_container(request) -> Optional[HttpResponse]:
    """
    For HTMX requests from the document request list page, return a fragment that
    refetches #view-container and refreshes toasts instead of a full HX-Redirect reload.
    """
    if request.headers.get("HX-Request") != "true":
        return None
    referer = request.META.get("HTTP_REFERER", "")
    if (
        "/employee/document-request-view" not in referer
        and "/employee/requests/" not in referer
    ):
        return None
    qs = urlparse(referer).query
    base = reverse("document-request-filter-view")
    url = f"{base}?{qs}" if qs else base
    inner = format_html(
        '<span hx-get="{}" hx-target="#view-container" hx-swap="innerHTML" '
        'hx-trigger="load"></span>',
        url,
    )
    script = (
        "<script>"
        "document.querySelectorAll('.oh-modal--show').forEach(function (m) {"
        "m.classList.remove('oh-modal--show');"
        "});"
        "document.getElementById('reloadMessagesButton')?.click();"
        "</script>"
    )
    return HttpResponse(str(inner) + script)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter("horilla_documents.add_documentrequest"), name="dispatch"
)
class DocumentRequestCreateForm(HorillaFormView):
    """
    form view for create and update document request
    """

    form_class = DocumentRequestForm
    model = DocumentRequest
    new_display_title = _("Create Document Request")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form = choosesubordinates(
            self.request, self.form, "horilla_documents.add_documentrequest"
        )
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Document Request")

        return context

    def form_valid(self, form: DocumentRequestForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                pk = self.form.instance.pk
                documents = Document.objects.filter(document_request_id=pk)
                doc_obj = form.save()
                doc_obj.employee_id.set(
                    Employee.objects.filter(id__in=form.data.getlist("employee_id"))
                )
                documents.exclude(employee_id__in=doc_obj.employee_id.all()).delete()
                messages.success(
                    self.request, _("Document Request Updated Successfully")
                )
            else:
                messages.success(
                    self.request, _("Document request created successfully")
                )
                emp = form.cleaned_data["employee_id"].all()
                users = [user.employee_user_id for user in emp]
                notify.send(
                    self.request.user.employee_get,
                    recipient=users,
                    verb=gettext_noop("%(employee_get)s requested a document."),
                    verb_params={"employee_get": str(self.request.user.employee_get)},
                    redirect=reverse("employee-profile"),
                    icon="chatbox-ellipses",
                )
                form.save()
            refreshed = htmx_refresh_document_request_container(self.request)
            if refreshed is not None:
                return refreshed
            return HorillaRedirect(self.request)

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class DocumentCreateForm(HorillaFormView):
    """
    form view for upload document
    """

    form_class = DocumentForm
    model = Document
    new_display_title = _("Document")

    def get_initial(self) -> dict:
        initial = super().get_initial()
        employee_id = self.kwargs.get("emp_id")
        initial["employee_id"] = employee_id
        initial["expiry_date"] = None
        return initial

    def form_valid(self, form: DocumentForm) -> HttpResponse:
        uploaded_file = self.request.FILES.get("document")
        if uploaded_file:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            if ext in BLOCKED_EXTENSIONS:
                messages.error(
                    self.request, _("File type %(ext)s is not allowed.") % {"ext": ext}
                )
                refreshed = htmx_refresh_document_request_container(self.request)
                if refreshed is not None:
                    return refreshed
                return HorillaRedirect(self.request)

        form.save()
        messages.success(self.request, _("Document Uploaded Successfully"))
        refreshed = htmx_refresh_document_request_container(self.request)
        if refreshed is not None:
            return refreshed
        return HorillaRedirect(self.request)


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("horilla_documents.add_document"), name="dispatch")
class DocumentRejectCbvForm(HorillaFormView):
    """
    form view for rejecting document on document request and employee individual view
    """

    model = Document
    form_class = RejectForm
    hx_confirm = _("Do you want to reject this request")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Reject")
        return context

    def form_valid(self, form: RejectForm) -> HttpResponse:
        if form.is_valid():
            if self.form.instance.document:
                self.form.instance.status = "rejected"
                form.save()
                messages.success(self.request, _("Document request rejected"))
            else:
                messages.error(self.request, _("No document uploaded"))
            refreshed = htmx_refresh_document_request_container(self.request)
            if refreshed is not None:
                return refreshed
            return HorillaRedirect(self.request)

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class DocumentUploadForm(HorillaFormView):
    """
    form view for upload documents on document request and employee individual view
    """

    model = Document
    form_class = DocumentUpdateForm
    template_name = "cbv/documents/inherit_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form.fields["title"].widget = forms.HiddenInput()
        self.form.fields["employee_id"].widget = forms.HiddenInput()
        self.form.fields["document_request_id"].widget = forms.HiddenInput()
        self.form.fields["status"].widget = forms.HiddenInput()
        self.form.fields["reject_reason"].widget = forms.HiddenInput()
        self.form.fields["is_digital_asset"].widget = forms.HiddenInput()

        if self.form.instance.pk:
            self.form_class.verbose_name = _("Upload File")
        return context

    def form_valid(self, form: DocumentUpdateForm) -> HttpResponse:
        uploaded_file = self.request.FILES.get("document")

        if uploaded_file:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            if ext in BLOCKED_EXTENSIONS:
                messages.error(
                    self.request, _("File type %(ext)s is not allowed.") % {"ext": ext}
                )
                refreshed = htmx_refresh_document_request_container(self.request)
                if refreshed is not None:
                    return refreshed
                return HorillaRedirect(self.request)

        if form.is_valid():
            if form.instance.pk:
                messages.success(self.request, _("Document uploaded successfully"))
                try:
                    notify.send(
                        self.request.user.employee_get,
                        recipient=self.request.user.employee_get.get_reporting_manager().employee_user_id,
                        verb=gettext_noop("%(employee_get)s uploaded a document"),
                        verb_params={
                            "employee_get": str(self.request.user.employee_get)
                        },
                        redirect=reverse(
                            "employee-view-individual",
                            kwargs={"obj_id": self.request.user.employee_get.id},
                        ),
                        icon="chatbox-ellipses",
                    )
                except Exception:
                    pass
            form.instance.status = "requested"
            form.save()
            refreshed = htmx_refresh_document_request_container(self.request)
            if refreshed is not None:
                return refreshed
            return HorillaRedirect(self.request)

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class DocumentRequestNav(HorillaNavView):
    """
    For nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("document-request-filter-view")
        self.create_attrs = f"""
                            data-toggle="oh-modal-toggle"
                            data-target="#genericModal"
                            hx-target="#genericModalBody"
                            hx-get="{reverse_lazy('document-request-create')}"
                            """

        if self.request.user.has_perm(
            "employee.change_employee"
        ) or is_reportingmanager(self.request):
            if self.request.user.has_perm(
                "horilla_documents.change_documentrequest"
            ) or is_reportingmanager(self.request):
                self.actions = [
                    {
                        "action": _("Bulk Approve Requests"),
                        "attrs": f"""
                        id="bulkApproveDocument"
                        hx-post="{reverse('document-bulk-approve')}"
                        hx-target="#view-container"
                        hx-swap="innerHTML"
                        hx-confirm='Do you really want to approve all the selected requests?'
                        style="cursor: pointer;"
                        hx-on:click="validateDocsIds(event, 'approved');"
                        data-action="approved"
                        """,
                    },
                    {
                        "action": _("Bulk Reject Requests"),
                        "attrs": f"""
                        hx-get={reverse('document-bulk-reject')}
                        hx-vals='js:{{"ids": JSON.parse(document.getElementById("selectedInstances").getAttribute("data-ids") || "[]")}}'
                        data-target="#objectCreateModal"
                        data-toggle="oh-modal-toggle"
                        hx-on:click="validateDocsIds(event, 'rejected');"
                        data-action="rejected"
                        hx-target="#objectCreateModalTarget"
                        id="bulkRejectDocument"
                        style="cursor: pointer;"
                        """,
                    },
                ]
        else:
            self.actions = None

    nav_title = _("Document Requests")
    template_name = "generic/inline_nav.html"
    filter_body_template = "cbv/documents/document_filter.html"
    filter_instance = DocumentRequestFilter()
    filter_form_context_name = "form"
    search_swap_target = "#view-container"
    # Modern slide-over filter panel; DocumentRequestFilter.ajax_fields feeds its AJAX comboboxes.
    modern_filter = True


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class DocumentRequestPipelineView(Pipeline):
    """
    Pipeline view for document request
    """

    model = Document
    filter_class = DocumentRequestFilter
    grouper = "document_request_id"
    template_name = "cbv/documents/pipeline.html"

    allowed_fields = [
        {
            "field": "document_request_id",
            "model": DocumentRequest,
            "filter": DocumentPipelineFilter,
            "url": reverse_lazy("document-request-list"),
            "parameters": [
                "document_request_id={pk}",
            ],
            "actions": [
                {
                    "action": _("Edit"),
                    "attrs": """
                        class="oh-dropdown__link oh-dropdown__link"
                        data-toggle="oh-modal-toggle"
                        data-target="#objectCreateModal"
                        hx-get="{get_edit_url}"
                        hx-target="#objectCreateModalTarget"
                    """,
                },
                {
                    "action": _("Delete"),
                    "attrs": """
                        class="oh-dropdown__link oh-dropdown__link"
                        hx-confirm="Are you sure you want to delete this document request?"
                        hx-post="{get_delete_url}"
                        hx-target="#view-container"
                        hx-swap="innerHTML"
                    """,
                },
            ],
        }
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pipeline never builds filter_dict itself (unlike HorillaListView), so build it here
        # the same way, or the nav's "remove filter" tags would render empty.
        data_dict = parse_qs(self.request.GET.urlencode())
        data_dict = {
            key: list(dict.fromkeys(values)) for key, values in data_dict.items()
        }
        data_dict = get_key_instances(self.model, data_dict)
        for key in ("filter_applied", "nav_url", "referrer", "grouper", "page"):
            data_dict.pop(key, None)
        # generic/filter_tags.html needs the label/extra maps next to filter_dict
        data_dict, tag_labels, tag_extras = humanize_filter_tags(data_dict)
        context["filter_dict"] = data_dict
        context["filter_tag_labels"] = tag_labels
        context["filter_tag_extras"] = tag_extras
        context["keys_to_remove"] = []

        context["saved_filters"] = self.request.GET
        context["stored_filters"] = horilla_views_models.SavedFilter.objects.filter(
            saved_filter_path_query(self.request), created_by=self.request.user
        ).distinct()

        all_groups = context["groups"].order_by("-id")
        context["groups_total_count"] = all_groups.count()
        context["groups"] = paginator_qry(all_groups, self.request.GET.get("page"))

        preserved_query = self.request.GET.copy()
        preserved_query.pop("page", None)
        context["groups_preserved_query"] = preserved_query.urlencode()
        context["groups_search_url"] = reverse("document-request-filter-view")

        context["queryset"] = context["groups"]
        context["search_url"] = context["groups_search_url"]
        context["pd"] = context["groups_preserved_query"]

        for group in context["groups"]:
            group.filtered_document_count = DocumentRequestFilter(
                self.request.GET, queryset=group.document_set.all()
            ).qs.count()
        return context


@method_decorator(login_required, name="dispatch")
class DocumentListView(HorillaListView):
    """
    List view for document request
    """

    model = Document
    filter_class = DocumentRequestFilter
    filter_keys_to_remove = ["document_request_id"]
    quick_export = False
    show_filter_tags = False

    columns = [
        (_("Document"), "document_title_display", "employee_id__get_avatar"),
        (_("Status"), "document_status_display"),
        (_("Date"), "issue_date"),
    ]
    default_columns = columns

    action_method = "document_actions"

    # One instance of this view loads per expanded document-type group on the
    # Document Requests pipeline page (employee/templates/cbv/documents/pipeline.html),
    # which renders ONE header shared by all of them -- see that template's
    # comment. Row checkboxes and the per-group "Select (N)" toolbar
    # (generic/quick_actions.html, unaffected by show_header) still work
    # normally; only the repeated column-label row is suppressed.
    # DocumentIndividualTabList below (the standalone Documents profile tab)
    # restores it, since it's a normal one-off list, not one of several
    # sharing a header.
    show_header = False
    header_attrs = {
        "document_title_display": 'style="width:280px !important;"',
        "document_status_display": 'style="width:140px !important;"',
        "issue_date": 'style="width:140px !important;"',
        "action": 'style="width:160px !important;"',
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stored_filters"] = horilla_views_models.SavedFilter.objects.none()
        return context

    row_attrs = """
                id="document{id}"
                hx-get='{view_file_url}'
                hx-target="#viewFile"
                data-toggle="oh-modal-toggle"
                data-target="#viewFileModal"
                """

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        queryset = super().get_queryset(queryset, filtered, *args, **kwargs)
        queryset = queryset.filter(
            document_request_id__pk=self.request.GET.get("document_request_id")
        )
        return queryset


@method_decorator(login_required, name="dispatch")
class DocumentIndividualTabList(DocumentListView):
    """
    List view for the Documents tab in employee individual & profile view
    """

    columns = [
        (_("Document"), "title"),
        (_("Status"), "document_status_display"),
        (_("Date"), "issue_date"),
    ]
    default_columns = columns

    sortby_mapping = [
        (_("Document"), "title"),
        (_("Date"), "issue_date"),
    ]

    # A normal standalone list (the profile's own Documents tab), not one of
    # several sharing a header -- restore what the parent class turns off for
    # its own embedded-in-a-pipeline-accordion use (see the comment there).
    show_header = True
    header_attrs = {}

    row_attrs = """
                id="document{id}"
                hx-get='{view_file_url}'
                hx-target="#genericModalBody"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("employee-document-tab-list", kwargs={"pk": pk})
        self.view_id = "document_target"

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        if queryset is None:
            pk = self.kwargs.get("pk")
            queryset = self.model.objects.filter(employee_id=pk)
        return HorillaListView.get_queryset(self, queryset, filtered, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class DocumentIndividualTabShell(ProfileTabShellView):
    """
    Shell for the Documents profile tab: loads the nav (with the Create
    button) and, through it, the employee's documents list.
    """

    shell_target_id = "document-shell"
    nav_url_name = "employee-document-tab-nav"


@method_decorator(login_required, name="dispatch")
class DocumentIndividualNav(HorillaNavView):
    """
    Minimal nav (Create button only) for the Documents profile tab.
    """

    template_name = "generic/inline_nav.html"
    nav_title = _("Documents")
    hide_search = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("employee-document-tab-list", kwargs={"pk": pk})
        self.search_swap_target = "#document-shell"
        self.create_attrs = f"""
            hx-get="{reverse('document-create', kwargs={'emp_id': pk})}"
            hx-target="#genericModalBody"
            data-toggle="oh-modal-toggle"
            data-target="#genericModal"
        """
