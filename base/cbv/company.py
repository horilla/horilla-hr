"""
this page is handling the cbv methods for company in settings
"""

from typing import Any

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.filters import CompanyFilter
from base.forms import CompanyForm
from base.models import Company
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.forms import DynamicBulkUpdateForm
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="base.view_company"), name="dispatch")
class CompanyListView(HorillaListView):
    """
    list view for company in settings
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("company-list")
        self.actions = []
        if self.request.user.has_perm("base.change_company"):
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
        if self.request.user.has_perm("base.delete_company"):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "icon": "trash-outline",
                    "attrs": """
                            class="oh-btn oh-btn--danger oh-btn--sq-sm"
                            hx-get="{get_delete_url}?model=base.company&pk={pk}"
                            data-toggle="oh-modal-toggle"
                            data-target="#deleteConfirmation"
                            hx-target="#deleteConfirmationBody"
                        """,
                }
            )

    model = Company
    filter_class = CompanyFilter
    selected_instances_key_id = "selectedInstance"
    bulk_update_fields = ["country", "state", "city", "zip"]

    def get_bulk_form(self):
        """
        Bulk from generating method
        """

        form = DynamicBulkUpdateForm(
            root_model=Company, bulk_update_fields=self.bulk_update_fields
        )

        form.fields["country"] = forms.ChoiceField(
            widget=forms.Select(
                attrs={
                    "class": "oh-select oh-select-2",
                    "required": True,
                    "style": "width: 100%; height:45px;",
                }
            )
        )

        form.fields["state"] = forms.ChoiceField(
            widget=forms.Select(
                attrs={
                    "class": "oh-select oh-select-2",
                    "required": True,
                    "style": "width: 100%; height:45px;",
                }
            )
        )

        return form

    columns = [
        (_("Company"), "company_icon_with_name"),
        (_("Is Hq"), "hq"),
        (_("Address"), "address"),
        (_("Country"), "country"),
        (_("State"), "state"),
        (_("City"), "city"),
        (_("Zip"), "zip"),
    ]

    sortby_mapping = [
        (_("Company"), "company_icon_with_name"),
        (_("Country"), "country"),
        (_("State"), "state"),
        (_("City"), "city"),
        (_("Zip"), "zip"),
    ]

    row_attrs = """
                id="companyTr{get_delete_instance}"
                """

    header_attrs = {
        "company_icon_with_name": """ style="width:180px !important" """,
        "action": """ style="width:180px !important" """,
    }


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="base.view_company"), name="dispatch")
class CompanyNavView(HorillaNavView):
    """
    nav bar of the department view
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("company-list")
        if self.request.user.has_perm("base.add_company"):
            self.create_attrs = f"""
                                onclick = "event.stopPropagation();"
                                data-toggle="oh-modal-toggle"
                                data-target="#genericModal"
                                hx-target="#genericModalBody"
                                hx-get="{reverse('company-create-form')}"
                                """

    nav_title = _("Companies")
    search_swap_target = "#listContainer"
    filter_instance = CompanyFilter()


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="base.add_company"), name="dispatch")
class CompanyCreateForm(HorillaFormView):
    """
    form view for creating and editing company in settings
    """

    model = Company
    form_class = CompanyForm
    new_display_title = _("Create Company")
    template_name = "cbv/company/company_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)

        if self.form.instance and getattr(self.form.instance, "pk", None):
            self.form_class.verbose_name = _("Update Company")

        form.fields["country"].widget = forms.Select(
            attrs={
                "class": "oh-select oh-select-2",
            }
        )
        form.fields["state"].widget = forms.Select(
            attrs={"class": "oh-select oh-select-2"}
        )
        return form

    def form_invalid(self, form: Any) -> HttpResponse:
        """
        Handles and renders form errors or defers to superclass.
        """

        if self.form.instance and getattr(self.form.instance, "pk", None):
            self.form_class.verbose_name = _("Update Company")

        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: CompanyForm) -> HttpResponse:
        if form.is_valid():
            form.save()
            if getattr(self.form.instance, "pk", None):
                messages.success(
                    self.request, _("Company have been successfully updated.")
                )
            else:
                messages.success(
                    self.request, _("Company have been successfully created.")
                )
            return self.HttpResponse()

        return super().form_valid(form)
