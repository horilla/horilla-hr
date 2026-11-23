"""The settings tab where an admin defines the additional info fields."""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from additional_info.filters import AdditionalInfoFieldFilter
from additional_info.forms import AdditionalInfoFieldForm
from additional_info.models import AdditionalInfoField
from horilla.decorators import hx_request_required
from horilla.decorators import login_required as fbv_login_required
from horilla.decorators import permission_required as fbv_permission_required
from horilla.methods import handle_no_permission
from horilla_views.cbv_methods import login_required, permission_required, structured
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
)


@fbv_login_required
@hx_request_required
@fbv_permission_required(perm="additional_info.view_additionalinfofield")
def fields_tab(request):
    """HTMX tab body for additional info fields under Employee Configuration."""
    return render(request, "additional_info/fields_tab.html")


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="additional_info.view_additionalinfofield"),
    name="dispatch",
)
class AdditionalInfoFieldListView(HorillaListView):
    """The list of fields."""

    model = AdditionalInfoField
    filter_class = AdditionalInfoFieldFilter
    show_toggle_form = False
    row_attrs = """ id="additionalInfoFieldTr{get_instance_id}" """
    columns = [
        (_("Label"), "label"),
        (_("Type"), "type_display"),
        (_("Required"), "required_display"),
        (_("Order"), "sequence"),
        (_("Active"), "active_display"),
    ]
    header_attrs = {"action": """ style="width:200px !important" """}

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("additional-info-field-list")
        self.actions = []
        if self.request.user.has_perm("additional_info.change_additionalinfofield"):
            self.actions.append(
                {
                    "action": _("Edit"),
                    "icon": "create-outline",
                    "attrs": """
                        class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                        hx-get='{get_update_url}?instance_ids={ordered_ids}'
                        hx-target="#genericModalBody"
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                    """,
                }
            )
        if self.request.user.has_perm("additional_info.delete_additionalinfofield"):
            confirm = _(
                "Delete this field? The values employees have saved for it are deleted too."
                " Edit it and turn off Active to hide it instead."
            )
            self.actions.append(
                {
                    "action": _("Delete"),
                    "icon": "trash-outline",
                    "attrs": f"""
                        class="oh-btn oh-btn--danger oh-btn--sq-sm"
                        hx-confirm="{confirm}"
                        hx-swap="outerHTML"
                        hx-post="{{get_delete_url}}"
                        hx-target="#additionalInfoFieldTr{{get_instance_id}}"
                    """,
                }
            )


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="additional_info.view_additionalinfofield"),
    name="dispatch",
)
class AdditionalInfoFieldNavView(HorillaNavView):
    """The title, search and create button above the list."""

    template_name = "generic/inline_nav.html"
    nav_title = _("Additional Info Fields")
    search_swap_target = "#listContainer"
    filter_instance = AdditionalInfoFieldFilter()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("additional-info-field-list")
        if self.request.user.has_perm("additional_info.add_additionalinfofield"):
            self.create_attrs = f"""
                onclick="event.stopPropagation();"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                hx-get="{reverse('additional-info-field-create-form')}"
            """


def _structured_with_type_script(form):
    """The generic form markup followed by the script that reacts to the Type."""
    return mark_safe(
        structured(form) + render_to_string("additional_info/field_form_script.html")
    )


@method_decorator(login_required, name="dispatch")
class AdditionalInfoFieldFormView(HorillaFormView):
    """Create or edit a field."""

    model = AdditionalInfoField
    form_class = AdditionalInfoFieldForm
    new_display_title = _("Create Additional Info Field")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # The generic view installs its own renderer on the form; this one adds the script that makes the form
        # follow the chosen type (options only for a dropdown, and a live preview of the input).
        self.form_class.structured = _structured_with_type_script

    def dispatch(self, request, *args, **kwargs):
        needed = "change" if kwargs.get("pk") else "add"
        if not request.user.has_perm(f"additional_info.{needed}_additionalinfofield"):
            return handle_no_permission(request)
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form: Any) -> HttpResponse:
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Additional Info Field")
        return render(
            self.request,
            self.template_name,
            {"form": form, "errors": form.errors.as_data()},
        )

    def form_valid(self, form: AdditionalInfoFieldForm) -> HttpResponse:
        created = not form.instance.pk
        form.save()
        messages.success(
            self.request,
            (
                _("Field has been created successfully!")
                if created
                else _("Field has been updated successfully!")
            ),
        )
        return self.HttpResponse()


@fbv_login_required
@require_POST
@fbv_permission_required(perm="additional_info.delete_additionalinfofield")
def delete_field(request, pk):
    """Delete a field and, with it, every employee's value for it."""
    field = AdditionalInfoField.objects.filter(pk=pk).first()
    if field is None:
        messages.error(request, _("Field not found."))
    else:
        label = field.label
        field.delete()
        messages.success(
            request, _("The field %(label)s has been deleted.") % {"label": label}
        )
    return HttpResponse("<script>$('#reloadMessagesButton').click()</script>")
