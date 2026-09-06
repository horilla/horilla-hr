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

from base.methods import (
    choosesubordinates,
    get_key_instances,
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
    For HTMX requests originating from the document request list page, return a
    fragment that refetches the list into #view-container and refreshes toasts,
    avoiding HX-Redirect full page reloads.
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
                    verb=f"{self.request.user.employee_get} requested a document.",
                    verb_ar=f"طلب {self.request.user.employee_get} مستنداً.",
                    verb_de=f"{self.request.user.employee_get} hat ein Dokument angefordert.",
                    verb_es=f"{self.request.user.employee_get} solicitó un documento.",
                    verb_fr=f"{self.request.user.employee_get} a demandé un document.",
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
                        verb=f"{self.request.user.employee_get} uploaded a document",
                        verb_ar=f"قام {self.request.user.employee_get} بتحميل مستند",
                        verb_de=f"{self.request.user.employee_get} hat ein Dokument hochgeladen",
                        verb_es=f"{self.request.user.employee_get} subió un documento",
                        verb_fr=f"{self.request.user.employee_get} a téléchargé un document",
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
    # Modern slide-over filter panel (generic/inline_nav.html's own
    # {% if modern_filter %} branch, mirroring horilla_nav.html's
    # .oh-filter-modern styles) -- same treatment as every other panel
    # this session. DocumentRequestFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True


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
        # Pipeline (unlike HorillaListView) never builds filter_dict itself,
        # so generic/filter_tags.html - included by cbv/documents/pipeline.html
        # to give the nav's search/filter dropdown a working "remove filter"
        # tag - would otherwise always render empty. Mirrors the same
        # get_key_instances()-based construction HorillaListView uses.
        data_dict = parse_qs(self.request.GET.urlencode())
        data_dict = {
            key: list(dict.fromkeys(values)) for key, values in data_dict.items()
        }
        data_dict = get_key_instances(self.model, data_dict)
        for key in ("filter_applied", "nav_url", "referrer", "grouper", "page"):
            data_dict.pop(key, None)
        context["filter_dict"] = data_dict

        # Pipeline never wired up the saved-filter chip row (quick_actions.html)
        # that every HorillaListView/HorillaCardView gets for free, so there
        # was nothing to click "Save" on and no chips to show here. Mirror
        # their stored_filters construction, but WITHOUT the referrer-based OR
        # match those use: every chip re-submits its own historically-saved
        # "referrer" GET param when clicked, so matching on "current referrer"
        # made the "Filter (N)" count shift depending on which chip was last
        # selected. path/nav_url are stable regardless of which filter (if
        # any) is currently applied, so match on those alone.
        context["saved_filters"] = self.request.GET
        context["stored_filters"] = horilla_views_models.SavedFilter.objects.filter(
            saved_filter_path_query(self.request), created_by=self.request.user
        ).distinct()

        # The outer group list (one accordion row per document type) was
        # rendered in full with no paging, unlike every other list in the
        # app - fine while there were a couple of document types, but it
        # just keeps growing as more get added. Page it like everything
        # else, keeping the total (not just the current page's count) for
        # the tab badge in the template's script block.
        all_groups = context["groups"].order_by("-id")
        context["groups_total_count"] = all_groups.count()
        context["groups"] = paginator_qry(all_groups, self.request.GET.get("page"))

        preserved_query = self.request.GET.copy()
        preserved_query.pop("page", None)
        context["groups_preserved_query"] = preserved_query.urlencode()
        context["groups_search_url"] = reverse("document-request-filter-view")

        # quick_actions.html already renders a pagination control in the same
        # row as the Filter dropdown (the "queryset"/"search_url"/"pd" names
        # below are what it expects) - reuse it instead of hand-rolling a
        # second, differently-styled pagination widget underneath.
        context["queryset"] = context["groups"]
        context["search_url"] = context["groups_search_url"]
        context["pd"] = context["groups_preserved_query"]

        # The accordion badge used to show group.document_set.count - the
        # group's grand total, unaffected by the nav's own search/filter.
        # That reads as broken once the inner document list (which *is*
        # filtered, since the accordion's hx-get forwards request.GET into
        # it) only shows a handful of matching rows under a badge still
        # claiming the group's full, unfiltered size. Filter each group's
        # own count the same way DocumentListView filters its document list,
        # so the badge always matches what's actually visible underneath it.
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
    # This per-group list has no filter UI of its own - the only visible
    # search/filter controls on the page belong to the outer nav
    # (DocumentRequestNav). filter_tags.html hardcodes
    # id="filterTagContainerSectionNav", the same id the nav's own template
    # (generic/inline_nav.html) uses for its own container, so leaving this
    # enabled means every group reload's filter_tags.html re-renders into
    # *both* matching elements (jQuery's #id selector matches all of them),
    # clobbering the nav's own search tag with this list's unrelated,
    # forwarded-through-request.GET filter state.
    show_filter_tags = False

    columns = [
        (_("Document"), "document_title_display", "employee_id__get_avatar"),
        (_("Status"), "document_status_display"),
        (_("Date"), "issue_date"),
    ]
    default_columns = columns

    action_method = "document_actions"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Same reasoning as show_filter_tags above: the quick-filter chip row
        # (quick_actions.html's "Filter (N)" dropdown) is a page-level control
        # that already lives once, outside every group, on
        # DocumentRequestPipelineView. HorillaListView always populates
        # stored_filters regardless of show_filter_tags, so left alone every
        # expanded group would render its own identical copy of that dropdown.
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

    # DocumentListView's inherited row_attrs targets #viewFile / #viewFileModal,
    # a modal shell that only exists inside the handful of legacy templates
    # that used to embed it inline (tabs/document_tab.html, documents/
    # requests.html, etc). Now that this tab renders through the generic
    # HorillaListView table template instead of one of those templates, that
    # shell is absent from the DOM and a row click raised htmx:targetError
    # instead of opening a preview. Route through #genericModal /
    # #genericModalBody instead - the page-chrome modal that's always present
    # - matching how every other HorillaProfileView sub-tab in this framework
    # opens its row-click preview (see RotatingShiftAssignIndividualView and
    # RotatingWorkIndividualTab in base/cbv/work_shift_tab.py).
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
        # DocumentListView.get_queryset() (the immediate parent) filters by
        # a document_request_id GET param, which doesn't apply to this tab
        # (it's scoped by the employee_id path param instead), so go
        # straight to HorillaListView.get_queryset() with our own base
        # queryset. That base implementation is what sets self._saved_filters
        # and applies filter_class/session/pagination handling -
        # get_context_data() reads self._saved_filters unconditionally, so
        # skipping it (as a bare `return self.model.objects.filter(...)`
        # override previously did) raised an AttributeError on every load.
        if queryset is None:
            pk = self.kwargs.get("pk")
            queryset = self.model.objects.filter(employee_id=pk)
        return HorillaListView.get_queryset(self, queryset, filtered, *args, **kwargs)
