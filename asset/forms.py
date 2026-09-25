"""
forms.py
Asset Management Forms

This module contains Django ModelForms for handling various aspects of asset management,
including asset creation, allocation, return, category assignment, and batch handling.
"""

import uuid
from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from asset.models import (
    Asset,
    AssetAssignment,
    AssetCategory,
    AssetDocuments,
    AssetItem,
    AssetLot,
    AssetReport,
    AssetRequest,
)
from base.forms import ModelForm
from base.methods import reload_queryset
from employee.forms import MultipleFileField
from employee.models import Employee
from horilla.horilla_middlewares import _thread_locals


def set_date_field_initial(instance):
    """this is used to update change the date value format"""
    initial = {}
    if instance.asset_purchase_date is not None:
        initial["asset_purchase_date"] = instance.asset_purchase_date.strftime(
            "%Y-%m-%d"
        )

    return initial


class AssetForm(ModelForm):
    """
    A ModelForm for creating and updating asset information.
    """

    class Meta:
        model = Asset
        fields = "__all__"
        exclude = ["is_active", "owner"]
        widgets = {
            "asset_purchase_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100"}
            ),
            "expiry_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "oh-input w-100",
                    "onchange": "toggleNotify($(this))",
                }
            ),
            "asset_lot_number_id": forms.Select(
                attrs={"onchange": "batchNoChange($(this))"}
            ),
        }
        labels = {
            "asset_name": _("Asset Name"),
            "asset_description": _("Description"),
            # "asset_tracking_id": "Tracking ID", #commented for translation
            "asset_purchase_date": _("Purchase Date"),
            "expiry_date": _("Warranty Expiry Date"),
            "asset_purchase_cost": _("Cost"),
            "asset_category_id": _("Category"),
            "asset_status": _("Status"),
            "asset_lot_number_id": _("Batch Number"),
        }

    def __init__(self, *args, **kwargs):
        request = getattr(_thread_locals, "request", None)
        instance = kwargs.get("instance")

        if instance:
            kwargs.setdefault("initial", set_date_field_initial(instance))

        super().__init__(*args, **kwargs)

        if self.instance.pk is None:
            self.fields["expiry_date"].initial = None

        uuid_map = {
            field: str(uuid.uuid4())
            for field in ["asset_category_id", "asset_lot_number_id", "asset_status"]
        }
        for field, uuid_value in uuid_map.items():
            self.fields[field].widget.attrs["id"] = uuid_value

        if request and request.user.has_perm("asset.add_assetlot"):
            batch_no_choices = list(
                self.fields["asset_lot_number_id"].queryset.values_list(
                    "id", "lot_number"
                )
            )
            batch_no_choices.insert(0, ("", _("---Choose Batch No.---")))

            if not self.instance.pk:
                batch_no_choices.append(("create", _("Create new batch number")))

            self.fields["asset_lot_number_id"].choices = batch_no_choices

    def clean(self):
        instance = self.instance
        prev_instance = Asset.objects.filter(id=instance.pk).first()
        if instance.pk:
            if (
                self.cleaned_data.get("asset_status", None)
                and self.cleaned_data.get("asset_status", None)
                != prev_instance.asset_status
            ):
                if instance.assetassignment_set.filter(
                    return_status__isnull=True
                ).exists():
                    raise ValidationError(
                        {"asset_status": 'Asset in use you can"t change the status'}
                    )
            if (
                Asset.objects.filter(asset_tracking_id=self.data["asset_tracking_id"])
                .exclude(id=instance.pk)
                .exists()
            ):
                raise ValidationError(
                    {"asset_tracking_id": "Already asset with this serial no. exists."}
                )


class AssetItemForm(forms.ModelForm):
    """
    Row form for the asset item bulk-edit table - tracking ID plus a
    manually-settable status (e.g. Damaged -> Available once repaired).
    """

    class Meta:
        model = AssetItem
        fields = ["tracking_id", "status"]
        widgets = {
            "tracking_id": forms.TextInput(attrs={"class": "oh-input w-100"}),
            "status": forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_status = self.instance.status if self.instance.pk else None
        # "In use" only ever comes from an actual assignment - never hand-set here.
        self.fields["status"].choices = [
            choice
            for choice in AssetItem.STATUS
            if choice[0] != "In use" or choice[0] == current_status
        ]
        if current_status == "In use":
            self.fields["status"].disabled = True


AssetItemFormSet = forms.modelformset_factory(
    AssetItem,
    form=AssetItemForm,
    extra=0,
)


class DocumentForm(forms.ModelForm):
    """
    Form for uploading documents related to an asset.

    Attributes:
    - file: A FileField with a TextInput widget for file upload, allowing multiple files.
    """

    file = forms.FileField(
        widget=forms.TextInput(
            attrs={
                "name": "file",
                "type": "File",
                "class": "form-control",
                "multiple": "True",
                "accept": ".jpeg, .jpg, .png, .pdf",
            }
        )
    )

    class Meta:
        """
        Metadata options for the DocumentForm.

        Attributes:
        - model: The model associated with this form (AssetDocuments).
        - fields: Fields to include in the form ('file').
        - exclude: Fields to exclude from the form ('is_active').
        """

        model = AssetDocuments
        fields = [
            "file",
        ]
        exclude = ["is_active"]


class AssetReportForm(ModelForm):
    """
    Form for creating and updating asset reports.

    Metadata:
    - model: The model associated with this form (AssetReport).
    - fields: Fields to include in the form ('title', 'asset_id').
    - exclude: Fields to exclude from the form ('is_active').

    Methods:
    - __init__: Initializes the form, disabling the 'asset_id' field.
    """

    file = forms.FileField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "name": "file",
                "type": "File",
                "class": "form-control",
                "multiple": "True",
                "accept": ".jpeg, .jpg, .png, .pdf",
            }
        ),
    )

    class Meta:
        """
        Metadata options for the AssetReportForm.

        Attributes:
        - model: The model associated with this form (AssetReport).
        - fields: Fields to include in the form ('title', 'asset_id').
        - exclude: Fields to exclude from the form ('is_active').
        """

        model = AssetReport
        fields = ["title", "asset_id", "file"]
        exclude = ["is_active"]

    def __init__(self, *args, **kwargs):
        """
        Initialize the AssetReportForm, disabling the 'asset_id' field.

        Args:
        - *args: Variable length argument list.
        - **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        # self.fields["asset_id"].widget.attrs["disabled"] = "disabled"


class AssetCategoryForm(ModelForm):
    """
    A form for creating and updating AssetCategory instances.
    """

    cols = {
        "asset_category_name": 12,
        "asset_category_description": 12,
        "company_id": 12,
    }

    class Meta:
        """
        Specifies the model and fields to be used for the AssetForm.
        Attributes:
            model (class): The model class AssetCategory to be used for the form.
            fields (str): A special value "__all__" to include all fields
                          of the model in the form.
        """

        model = AssetCategory
        fields = "__all__"
        exclude = ["is_active"]


class AssetRequestForm(ModelForm):
    """
    A Django ModelForm for creating and updating AssetRequest instances.
    """

    cols = {"requested_employee_id": 12, "asset_category_id": 12, "description": 12}

    class Meta:
        """
        Specifies the model and fields to be used for the AssetRequestForm.
        Attributes:
            model (class): The model class AssetRequest to be used for the form.
            fields (str): A special value "__all__" to include all fields
                          of the model in the form.
            widgets (dict): A dictionary containing widget configurations for
                            specific form fields.
        """

        model = AssetRequest
        fields = "__all__"
        exclude = ["is_active"]
        widgets = {
            "requested_employee_id": forms.Select(
                attrs={
                    "class": "oh-select  oh-select-2 select2-hidden-accessible",
                }
            ),
            "asset_category_id": forms.Select(
                attrs={
                    "class": "oh-select  oh-select-2 select2-hidden-accessible",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "type": "text",
                    "id": "objective_description",
                    "placeholder": _(
                        "Requesting a laptop for software development purposes."
                    ),
                    "class": "oh-input oh-input--textarea oh-input--block",
                    "rows": 3,
                    "cols": 40,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        # user = kwargs.pop("user", None)
        request = getattr(_thread_locals, "request", None)
        user = request.user
        super(AssetRequestForm, self).__init__(
            *args,
            **kwargs,
        )
        reload_queryset(self.fields)
        if user is not None and user.has_perm("asset.add_assetrequest"):

            self.fields["requested_employee_id"].queryset = Employee.objects.all()
            self.fields["requested_employee_id"].initial = Employee.objects.filter(
                id=user.employee_get.id
            ).first()
        else:
            self.fields["requested_employee_id"].queryset = Employee.objects.filter(
                employee_user_id=user
            )
            self.fields["requested_employee_id"].initial = user.employee_get

        self.fields["asset_category_id"].widget.attrs.update({"id": str(uuid.uuid4())})


class AssetAllocationForm(ModelForm):
    """
    A Django ModelForm for creating and updating AssetAssignment instances.
    """

    cols = {
        "assigned_to_employee_id": 12,
        "asset_id": 12,
        "asset_item_id": 12,
        "assigned_by_employee_id": 12,
    }

    def __init__(self, *args, **kwargs):
        request = getattr(_thread_locals, "request", None)
        user = request.user
        super(AssetAllocationForm, self).__init__(*args, **kwargs)
        reload_queryset(self.fields)
        self.fields["asset_id"].queryset = Asset.available_assets()
        self.fields["assigned_by_employee_id"].initial = user.employee_get

        self.fields["assign_images"] = MultipleFileField(
            label=_("Assign Condition Images")
        )
        self.fields["assign_images"].required = True

        asset = None
        submitted_asset_id = self.data.get("asset_id") if self.data else None
        if submitted_asset_id:
            asset = Asset.objects.filter(pk=submitted_asset_id).first()
        elif self.instance.pk:
            asset = self.instance.asset_id
        if asset:
            self.fields["asset_item_id"].queryset = asset.asset_items.filter(
                Q(status="Available") | Q(pk=self.instance.asset_item_id_id)
            )
        else:
            self.fields["asset_item_id"].queryset = AssetItem.objects.none()
        self.fields["asset_id"].widget.attrs.update(
            {
                "hx-target": "#id_asset_item_id_parent_div",
                "hx-include": "#id_asset_item_id",
                "hx-trigger": "change,load",
                "hx-swap": "innerHTML",
                "hx-get": "/asset/get-asset-items-hx/",
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        asset = cleaned_data.get("asset_id")
        asset_item = cleaned_data.get("asset_item_id")
        if asset:
            if not asset_item:
                available_items = asset.asset_items.filter(status="Available")
                if available_items.count() == 1:
                    asset_item = available_items.first()
                    cleaned_data["asset_item_id"] = asset_item
                elif available_items.count() > 1:
                    raise ValidationError(
                        {"asset_item_id": _("Please select an asset item to assign.")}
                    )
            elif asset_item.asset_id_id != asset.id:
                raise ValidationError(
                    {
                        "asset_item_id": _(
                            "The selected item does not belong to the chosen asset."
                        )
                    }
                )
        return cleaned_data

    class Meta:
        """
        Specifies the model and fields to be used for the AssetAllocationForm.
        Attributes:
            model (class): The model class AssetAssignment to be used for the form.
            fields (str): A special value "__all__" to include all fields
                          of the model in the form.
            widgets (dict): A dictionary containing widget configurations for
                            specific form fields.
        """

        model = AssetAssignment
        fields = "__all__"
        exclude = [
            "return_date",
            "return_condition",
            "assigned_date",
            "return_images",
            "assign_images",
            "is_active",
        ]
        widgets = {
            "asset_id": forms.Select(attrs={"class": "oh-select oh-select-2 "}),
            "asset_item_id": forms.Select(attrs={"class": "oh-select oh-select-2 "}),
            "assigned_to_employee_id": forms.Select(
                attrs={"class": "oh-select oh-select-2 "}
            ),
            "assigned_by_employee_id": forms.Select(
                attrs={
                    "class": "oh-select oh-select-2 ",
                },
            ),
        }


class AssetReturnForm(ModelForm):
    """
    A Django ModelForm for updating AssetAssignment instances during asset return.
    """

    class Meta:
        """
        Specifies the model and fields to be used for the AssetReturnForm.
        Attributes:
            model (class): The model class AssetAssignment to be used for the form.
            fields (list): The fields to include in the form, referring to
                           related AssetAssignment fields.
            widgets (dict): A dictionary containing widget configurations for
                            specific form fields.
        """

        model = AssetAssignment
        fields = ["return_date", "return_condition", "return_status", "return_images"]
        widgets = {
            "return_date": forms.DateInput(
                attrs={"type": "date", "class": "oh-input w-100", "required": "true"}
            ),
            "return_condition": forms.Textarea(
                attrs={
                    "class": "oh-input oh-input--textarea oh-input--block",
                    "rows": 3,
                    "cols": 40,
                    "placeholder": _(
                        "on returns the laptop. However, it has suffered minor damage."
                    ),
                }
            ),
            "return_status": forms.Select(
                attrs={"class": "oh-select oh-select-2", "required": "true"},
            ),
        }

    def __init__(self, *args, **kwargs):
        """
        Initializes the AssetReturnForm with initial values and custom field settings.
        """
        super().__init__(*args, **kwargs)
        self.fields["return_date"].initial = date.today()

        self.fields["return_images"] = MultipleFileField(
            label=_("Return Condition Images")
        )
        self.fields["return_images"].required = True

    def clean_return_date(self):
        """
        Validates the 'return_date' field.

        Ensures that the return date is not in the future. If the return date is in the future,
        a ValidationError is raised.

        Returns:
        - The cleaned return date.

        Raises:
        - forms.ValidationError: If the return date is in the future.
        """
        return_date = self.cleaned_data.get("return_date")

        if return_date and return_date > date.today():
            raise forms.ValidationError(_("Return date cannot be in the future."))

        return return_date


class AssetBatchForm(ModelForm):
    """
    A Django ModelForm for creating or updating AssetLot instances.
    """

    cols = {"lot_description": 12, "lot_number": 12}

    class Meta:
        """
        Specifies the model and fields to be used for the AssetBatchForm.
        Attributes:
            model (class): The model class AssetLot to be used for the form.
            fields (str): A special value "__all__" to include all fields
                          of the model in the form.
            widgets (dict): A dictionary containing widget configurations for
                            specific form fields.
        """

        model = AssetLot
        fields = "__all__"
        exclude = ["is_active"]


class AssetReassignForm(ModelForm):
    """
    ModelForm to swap the asset on an existing assignment to a replacement asset.
    Only exposes asset_id with queryset scoped to the same category.
    """

    class Meta:
        model = AssetAssignment
        fields = ["asset_id"]
        labels = {"asset_id": _("Replacement Asset")}
        widgets = {
            "asset_id": forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["asset_id"].queryset = (
                Asset.available_assets()
                .filter(asset_category_id=self.instance.asset_id.asset_category_id)
                .exclude(id=self.instance.asset_id.id)
            )
        else:
            self.fields["asset_id"].queryset = Asset.available_assets()


_ASSET_HISTORY_EXPORT_EXCLUDED = {
    "id",
    "created_at",
    "is_active",
    "additional_info",
    "return_images",
    "assign_images",
    "return_request",
}

_asset_history_field_choices = [
    (field.name, field.verbose_name)
    for field in AssetAssignment._meta.get_fields()
    if hasattr(field, "verbose_name")
    and field.name not in _ASSET_HISTORY_EXPORT_EXCLUDED
]


class AssetHistoryExportForm(forms.Form):
    """
    Column picker for Asset History Excel export (same pattern as employee export).
    """

    selected_fields = forms.MultipleChoiceField(
        choices=_asset_history_field_choices,
        widget=forms.CheckboxSelectMultiple,
        initial=[
            "asset_id",
            "assigned_to_employee_id",
            "assigned_date",
            "assigned_by_employee_id",
            "return_date",
            "return_status",
            "return_condition",
        ],
    )
