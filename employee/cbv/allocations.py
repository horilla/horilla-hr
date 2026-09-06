"""
employee/cbv/allocations.py

Detailed view to manage all modules employee information
"""

import ast
import logging
from datetime import datetime

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from base.forms import AddToUserGroupForm, ModelForm, forms
from base.methods import paginator_qry
from base.templatetags.horillafilters import app_installed
from base.views import get_models_in_app
from employee.models import Employee, EmployeeBankDetails, EmployeeWorkInformation
from employee.models import models as django_models
from horilla.horilla_middlewares import _thread_locals
from horilla.http import HorillaRedirect
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    render_template,
)
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    TemplateView,
)

if app_installed("asset"):
    from asset.cbv.request_and_allocation import Asset
    from asset.filters import AssetFilter
    from asset.models import AssetAssignment, AssetCategory, AssetRequest
    from asset.views import asset_allocate_return
    from asset.forms import AssetReturnForm

from onboarding.cbv_decorators import (
    all_manager_can_enter,
    recruitment_manager_can_enter,
)

if app_installed("leave"):
    from leave.cbv.leave_types import AvailableLeave, LeaveType, LeaveTypeListView

if app_installed("payroll"):
    from payroll.cbv.allowances import Allowance, AllowanceListView
    from payroll.cbv.deduction import Deduction, DeductionListView

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class AllocationView(HorillaDetailedView):
    """
    AllocationView
    """

    menues = []
    template_name = "cbv/allocations/allocations.html"
    model = Employee

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get(self, request, *args, **kwargs):
        pk = self.kwargs["pk"]
        model = request.GET.get("model")
        if model:
            # Only for recruitment and onboarding process
            # expecting model-> recruitment.models.Candidate
            Candidate = apps.get_model("recruitment", "Candidate")
            candidate = Candidate.objects.filter(pk=pk).first()
            if not candidate:
                messages.error(request, _("Record not found."))
                return HorillaFormView.HttpResponse()
            # set candidate to request for accessing inside work info signal
            request.employee_candidate = candidate
            instance = candidate.converted_employee_id
            if instance is None and (candidate.hired or candidate.onboarding_stage):
                instance, _created = Employee.objects.get_or_create(
                    employee_first_name=candidate.name,
                    email=candidate.email,
                    phone=candidate.mobile,
                    address=candidate.address,
                    country=candidate.country,
                    state=candidate.country,
                    city=candidate.city,
                    zip=candidate.zip,
                    dob=candidate.dob,
                    gender=candidate.gender,
                )
                # Candidate may fail business validation on unrelated fields
                # during allocation, so only persist the link directly.
                Candidate.objects.filter(pk=candidate.pk).update(
                    converted_employee_id=instance
                )
                instance.employee_user_id.is_active = False
                instance.employee_user_id.save()

            elif not instance:
                messages.info(
                    request, _("Allocation feature not possible to this candidate")
                )
                return HorillaFormView.HttpResponse()
        else:
            instance = Employee.objects.filter(pk=pk).first()
            if not instance:
                messages.error(request, _("Employee not found."))
                return HorillaFormView.HttpResponse()

        self.instance = instance

        super().get(request, *args, **kwargs)
        context = self.get_context_data(**kwargs)
        context["instance"] = instance
        context["menues"] = self.menues

        return render(request, self.template_name, context)


AllocationView.menues += [
    {
        "menu": _("Summary"),
        # you will get instance_id in url params
        "url": reverse_lazy("allocation-summary"),
    },
    {
        "menu": _("Employee"),
        # you will get instance_id in url params
        "url": reverse_lazy("allocation-employee-forms"),
    },
]


class PersonalForm(ModelForm):
    """
    PersonalForm
    """

    cols = {
        "address": 12,
        "country": 4,
        "state": 4,
        "city": 4,
        "zip": 4,
        "dob": 4,
        "gender": 4,
        "emergency_contact": 4,
        "emergency_contact_name": 4,
        "emergency_contact_relation": 4,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["emergency_contact_name"].label = _("Contact name")
        self.fields["emergency_contact_relation"].label = _("Contact Relation")
        self.fields["badge_id"].label = "Badge ID"

        self.fields["dob"].widget = forms.DateInput(
            attrs={"type": "date", "class": "oh-input w-100"}
        )
        attrs = self.fields["country"].widget.attrs
        attrs["class"] = "oh-select oh-select2 w-100"
        attrs["style"] = "height:45px !important;"
        self.fields["country"].widget = forms.Select(attrs=attrs)
        self.fields["state"].widget = forms.Select(attrs=attrs)

        # Reordering fields
        profile_field = self.fields.pop("employee_profile")
        fields = list(self.fields.items())
        fields.insert(1, ("employee_profile", profile_field))
        self.fields = dict(fields)

    class Meta:
        """
        Meta
        """

        model = Employee
        fields = "__all__"
        exclude = [
            "employee_user_id",
            "additional_info",
            "is_active",
        ]


class WorkInfo(ModelForm):
    """
    WorkInfo
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_joining"].widget = forms.DateInput(
            attrs={"type": "date", "class": "oh-input w-100"}
        )
        self.fields["contract_end_date"].widget = forms.DateInput(
            attrs={"type": "date", "class": "oh-input w-100"}
        )

    class Meta:
        """
        Meta
        """

        model = EmployeeWorkInformation
        fields = "__all__"
        exclude = [
            "employee_id",
            "experience",
            "additional_info",
        ]


class BankInfo(ModelForm):
    """
    BankInfo
    """

    cols = {
        "address": 12,
        "country": 4,
        "state": 4,
        "city": 4,
        "bank_name": 6,
        "account_number": 12,
        "branch": 6,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Reordering fields
        account_number = self.fields.pop("account_number")
        fields = list(self.fields.items())
        fields.insert(2, ("account_number", account_number))
        self.fields = dict(fields)

        attrs = self.fields["country"].widget.attrs
        attrs["class"] = "oh-select oh-select2 w-100"
        attrs["style"] = "height:45px !important;"
        attrs["id"] = "country"
        self.fields["country"].widget = forms.Select(attrs=attrs)
        attrs["id"] = "state"
        self.fields["state"].widget = forms.Select(attrs=attrs)

    class Meta:
        """
        Meta
        """

        model = EmployeeBankDetails
        fields = "__all__"
        exclude = [
            "employee_id",
            "additional_info",
            "is_active",
        ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class PersonalFormView(HorillaFormView):
    """
    PersonalFormView
    """

    form_class = PersonalForm
    model = Employee
    template_name = "cbv/allocations/employee/form_structure.html"

    def init_form(self, *args, data=..., files=..., instance=None, **kwargs):
        instance = self.instance

        if instance:
            instance = Employee.objects.entire().filter(pk=instance).first()
        return self.form_class(
            data, files, instance=instance, initial=self.get_initial()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["request"] = self.request
        return context

    def post(self, request, *args, pk=None, **kwargs):
        self.instance = request.POST.get("instance_id")
        return super().post(request, *args, pk=pk, **kwargs)

    def get(self, request, *args, pk=None, **kwargs):
        self.instance = request.GET.get("instance_id")
        return super().post(request, *args, pk=pk, **kwargs)

    def form_valid(self, form: PersonalForm):

        if form.is_valid():
            form.save()
            messages.success(self.request, _("Personal Information Updated"))
            return render(
                request=self.request,
                template_name=self.template_name,
                context=self.get_context_data(),
            )

        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class WorkFormView(HorillaFormView):
    """
    WorkFormView
    """

    form_class = WorkInfo
    model = EmployeeWorkInformation
    template_name = "cbv/allocations/employee/form_structure.html"
    restrict_company_field = False

    def init_form(self, *args, data=..., files=..., instance=None, **kwargs):
        instance = self.request.GET.get("instance_id", None)
        if instance:
            instance = (
                EmployeeWorkInformation.objects.entire()
                .filter(employee_id__id=instance)
                .first()
            )

        return super().init_form(
            *args, data=data, files=files, instance=instance, **kwargs
        )

    def form_valid(self, form: WorkInfo):
        if form.is_valid():
            form.save()
            messages.success(self.request, _("Work Info Updated"))
            return render(
                request=self.request,
                template_name=self.template_name,
                context=self.get_context_data(),
            )

        return super().form_valid(form)

    def post(self, request, *args, pk=None, **kwargs):
        self.instance = request.POST.get("instance_id")
        return super().post(request, *args, pk=pk, **kwargs)

    def get(self, request, *args, pk=None, **kwargs):
        self.instance = request.GET.get("instance_id")
        return super().post(request, *args, pk=pk, **kwargs)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
@receiver(post_save, sender=EmployeeWorkInformation)
def work_info_post_save(sender, instance, created, **kwargs):
    """
    Work info post save
    """
    request = getattr(_thread_locals, "request", None)
    if created and request and getattr(request, "employee_candidate", None):
        candidate = getattr(request, "employee_candidate")
        try:
            instance.date_joining = candidate.joining_date
            instance.job_position_id = candidate.job_position_id
            instance.department_id = candidate.job_position_id.department_id
            instance.company_id = candidate.recruitment_id.company_id
        except Exception as e:
            logger.error(e)
        django_models.Model.save(instance)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class BankFormView(HorillaFormView):
    """
    WorkFormView
    """

    form_class = BankInfo
    model = EmployeeBankDetails
    template_name = "cbv/allocations/employee/form_structure.html"

    def init_form(self, *args, data=..., files=..., instance=None, **kwargs):
        instance = self.request.GET.get("instance_id", None)
        if instance:
            instance = EmployeeBankDetails.objects.filter(
                employee_id__id=instance
            ).first()
        return super().init_form(
            *args, data=data, files=files, instance=instance, **kwargs
        )

    def form_valid(self, form: BankInfo):
        if form.is_valid():
            if not form.instance.employee_id:
                form.instance.employee_id = Employee.objects.get(
                    pk=self.request.POST["instance_id"]
                )
            form.save()
            messages.success(self.request, _("Bank Info Updated"))
            return render(
                request=self.request,
                template_name=self.template_name,
                context=self.get_context_data(),
            )
        return super().form_valid(form)

    def post(self, request, *args, pk=None, **kwargs):
        self.instance = request.POST.get("instance_id")
        return super().post(request, *args, pk=pk, **kwargs)

    def get(self, request, *args, pk=None, **kwargs):
        self.instance = request.GET.get("instance_id")
        return super().post(request, *args, pk=pk, **kwargs)


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class EmployeeForms(TemplateView):
    """
    EmployeeForms
    """

    template_name = "cbv/allocations/employee/forms.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


if app_installed("leave"):
    AllocationView.menues.append(
        {
            "menu": _("Leave Policy"),
            # you will get instance_id in url params
            "url": reverse_lazy("allocation-leave-type"),
        }
    )

    @method_decorator(login_required, name="dispatch")
    @method_decorator(hx_request_required, name="dispatch")
    @method_decorator(
        all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
    )
    class LeaveTypeView(TemplateView):
        """
        EmployeeForms
        """

        template_name = "cbv/allocations/leave/types.html"

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            return context

    def leave_type_toggle_allocation(self):
        """
        Leave type assign toggle allocation
        """
        request = getattr(_thread_locals, "request")
        instance_id = request.GET.get("instance_id")

        available_leave = (
            self.employee_available_leave.filter(employee_id__id=instance_id).first()
            if instance_id
            else None
        )
        return render_template(
            "cbv/allocations/leave/toggle_type.html",
            {"instance": self, "available_leave": available_leave},
        )

    LeaveType.leave_type_toggle_allocation = leave_type_toggle_allocation

    @method_decorator(login_required, name="dispatch")
    @method_decorator(
        all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
    )
    class LeaveTypeAllocationList(LeaveTypeListView):
        """
        LeaveTypeAllocationList
        """

        template_name = "cbv/allocations/leave/type_list.html"

        action_method = None
        # actions = [{"action": "Assigned", "icon": "checkmark-done-circle-outline"}]
        header_attrs = {
            "payment": "style='width:80px;'",
            "count": "style='width:105px;'",
            "action": "style='width:70px;'",
        }
        row_status_indications = []
        filter_selected = False
        show_filter_tags = False
        row_attrs = """
            onclick="$(this).find('td:first [type=checkbox]').prop('checked',!$(this).find('td:first [type=checkbox]').is(':checked')).change()"
        """

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.search_url = self.request.path
            self.action_method = "leave_type_toggle_allocation"

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            instance_id = self.request.GET.get("instance_id")
            context["assigned_types"] = (
                AvailableLeave.objects.filter(
                    employee_id__id=instance_id,
                    leave_type_id__in=self.queryset,
                )
                if instance_id
                else AvailableLeave.objects.none()
            )

            return context

        def dispatch(self, request, *args, **kwargs):
            """
            To avoide parent permissions
            """
            # This is a fragment meant to be loaded via htmx inside the
            # "Add types" modal (see leave/types.html), always carrying the
            # employee's instance_id. Visited directly/standalone without
            # it, there's no employee context to show assigned types
            # against, so render nothing rather than the raw, unstyled
            # list+export+column-picker fragment.
            if not request.GET.get("instance_id"):
                return HttpResponse()
            return super(LeaveTypeListView, self).dispatch(request, *args, **kwargs)

        def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
            if not getattr(self.queryset, "queryset", None):
                queryset = (
                    super()
                    .get_queryset(queryset, filtered, *args, **kwargs)
                    .exclude(
                        employee_available_leave__employee_id__id=self.request.GET.get(
                            "instance_id"
                        )
                    )
                )

            return self.queryset

        def post(self, *args, **kwargs):
            """
            post
            """
            AvailableLeave = apps.get_model("leave", "AvailableLeave")
            LeaveType = apps.get_model("leave", "LeaveType")

            ids = ast.literal_eval(self.request.POST["ids"])
            employee_id = self.request.POST["instance_id"]
            types = LeaveType.objects.filter(id__in=ids)
            instance = Employee.objects.get(pk=employee_id)
            for leave_type in types:
                avaiable_instance = AvailableLeave()
                avaiable_instance.employee_id = instance
                avaiable_instance.leave_type_id = leave_type
                avaiable_instance.available_days = leave_type.total_days
                try:
                    avaiable_instance.save()
                    messages.success(
                        self.request, _("Assigned ") + f" {leave_type.name}"
                    )
                except:
                    messages.error(
                        self.request,
                        _("Cannot Assign or Already Assigned")
                        + f" `{leave_type.name}`",
                    )
            if not types:
                messages.info(self.request, _("Select Types to Assign"))
            return HttpResponse(
                """
            <script>$("#reloadMessagesButton").click();$(".reload-record").click();</script>
    """
            )


if app_installed("asset"):
    AllocationView.menues.append(
        {
            "menu": _("Asset"),
            # you will get instance_id in url params
            "url": reverse_lazy("allocation-assets"),
        }
    )

    @method_decorator(login_required, name="dispatch")
    @method_decorator(
        all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
    )
    class Assets(TemplateView):
        """
        Assets
        """

        template_name = "cbv/allocations/asset/assets.html"

    def asset_allocation_metod(self):
        """
        Allocation method
        """
        return render_template("cbv/allocations/asset/actions.html", {"instance": self})

    def asset_allocation_status(self):
        """
        Allocation method
        """
        return render_template(
            "cbv/allocations/asset/allocation_status.html", {"instance": self}
        )

    def allocation_asset_get_avatar(self):
        """
        Method will retun the api to the avatar or path to the question template
        """
        url = f"https://ui-avatars.com/api/?name={self}&background=random"
        return url

    Asset.asset_allocation_metod = asset_allocation_metod
    Asset.allocation_asset_get_avatar = allocation_asset_get_avatar
    Asset.asset_allocation_status = asset_allocation_status

    @method_decorator(login_required, name="dispatch")
    @method_decorator(
        all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
    )
    class AssetAllocationList(HorillaListView):
        """
        AssetAllocationLists
        """

        model = Asset
        filter_class = AssetFilter
        template_name = "cbv/allocations/asset/asset_list.html"

        header_attrs = {
            "asset_tracking_id": "style='width:120px !important;'",
            "asset_name": "style='width:160px !important;'",
            "asset_category_id": "style='width:150px !important;'",
            "asset_status": "style='width:140px !important;'",
            "action": "style='width:70px;'",
        }
        row_status_indications = []
        filter_selected = False
        show_filter_tags = False
        row_attrs = """
            onclick="$(this).find('td:first [type=checkbox]').prop('checked',!$(this).find('td:first [type=checkbox]').is(':checked')).change()"
        """
        columns = [
            (_("Tracking Id"), "asset_tracking_id"),
            (_("Asset"), "asset_name", "allocation_asset_get_avatar"),
            (_("Category"), "asset_category_id"),
            (_("Status"), "asset_allocation_status"),
        ]
        sortby_mapping = [
            (_("Status"), "asset_allocation_status"),
        ]
        bulk_update_fields = []
        records_per_page = 10

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.search_url = self.request.path
            self.action_method = "asset_allocation_metod"

        def get_queryset(self, queryset=None, filtered=True, *args, **kwargs):
            if not getattr(self, "queryset", None):
                self._saved_filters = self.request.GET

                self.queryset = (
                    self.filter_class(
                        data=self.request.GET,
                        queryset=self.queryset,
                        request=self.request,
                    )
                    .qs.filter(
                        Q(
                            assetassignment__return_status__isnull=True,
                            assetassignment__assigned_to_employee_id__id=self.request.GET[
                                "instance_id"
                            ],
                        )
                        | (
                            Q(assetassignment__isnull=True)
                            & Q(asset_status="Available")
                        )
                        | Q(
                            assetassignment__return_status="Healthy",
                            asset_status="Available",
                        )
                    )
                    .filter(
                        Q(
                            asset_category_id__asset_category_name__icontains=self.request.GET.get(
                                "search", ""
                            )
                        )
                        | Q(asset_name__icontains=self.request.GET.get("search", ""))
                        | Q(
                            asset_tracking_id__icontains=self.request.GET.get(
                                "search", ""
                            )
                        )
                    )
                )

                self.queryset = super().get_queryset(
                    self.queryset, filtered, *args, **kwargs
                )
                self.assigned_assets = self.queryset.filter(asset_status="In use")

            return self.queryset

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            context["assigned_assets"] = self.assigned_assets
            return context

        def post(self, *args, **kwargs):
            _response = super().post(*args, **kwargs)
            ids = ast.literal_eval(self.request.POST["ids"])
            employee_id = self.request.POST["instance_id"]
            instance = Employee.objects.get(pk=employee_id)
            assets = Asset.objects.filter(pk__in=ids).filter(asset_status="Available")
            assigned_by = self.request.user.employee_get

            for asset in assets:
                assignment = AssetAssignment()
                assignment.asset_id = asset
                assignment.assigned_to_employee_id = instance
                assignment.assigned_by_employee_id = assigned_by
                assignment.assigned_date = datetime.today().date()
                asset.asset_status = "In use"
                assignment.save()
                asset.save()
            if assets:
                messages.success(self.request, _("Selected Available Assets Allocated"))
            else:
                messages.info(self.request, _("Select Available Assets to Add"))
            return HttpResponse(
                """
            <script>$("#reloadMessagesButton").click();$(".reload-record").click();</script>
    """
            )

    def category_available_count(self):
        """
        Number of units currently available to allocate for this asset category
        """
        return Asset.available_assets().filter(asset_category_id=self).count()

    def category_request_status(self):
        """
        Latest asset request status for this category raised for the employee
        currently being viewed on the allocation page, or "Available" if none.
        """
        request = getattr(_thread_locals, "request", None)
        employee_id = None
        if request:
            employee_id = request.GET.get("instance_id") or request.POST.get(
                "instance_id"
            )
        if employee_id:
            asset_request = (
                AssetRequest.objects.filter(
                    requested_employee_id__id=employee_id,
                    asset_category_id=self,
                    asset_request_status__in=["Requested", "Approved"],
                )
                .order_by("-id")
                .first()
            )
            if asset_request:
                return asset_request.asset_request_status
        return _("Available")

    def category_allocation_metod(self):
        """
        Allocation method
        """
        return render_template(
            "cbv/allocations/asset/category_actions.html", {"instance": self}
        )

    AssetCategory.allocation_asset_get_avatar = allocation_asset_get_avatar
    AssetCategory.category_available_count = category_available_count
    AssetCategory.category_request_status = category_request_status
    AssetCategory.category_allocation_metod = category_allocation_metod

    @method_decorator(login_required, name="dispatch")
    @method_decorator(
        all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
    )
    class AssetCategoryAllocationList(HorillaListView):
        """
        Lists asset categories for the employee and lets managers raise an
        AssetRequest for the selected categories instead of allocating an
        Asset directly. The request then goes through the normal asset
        request approval flow (asset.cbv.request_and_allocation.AssetApproveFormView).
        """

        model = AssetCategory
        template_name = "cbv/allocations/asset/asset_list.html"

        header_attrs = {
            "asset_category_name": "style='width:160px !important;'",
            "action": "style='width:70px;'",
        }
        row_status_indications = []
        filter_selected = False
        show_filter_tags = False
        row_attrs = """
            onclick="$(this).find('td:first [type=checkbox]').prop('checked',!$(this).find('td:first [type=checkbox]').is(':checked')).change()"
        """
        columns = [
            (_("Category"), "asset_category_name", "allocation_asset_get_avatar"),
            (_("Available"), "category_available_count"),
            (_("Status"), "category_request_status"),
        ]
        sortby_mapping = [
            (_("Category"), "asset_category_name"),
        ]
        bulk_update_fields = []
        records_per_page = 10
        selected_instances_key_id = "asset_category_allocation_selected_instances"

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.search_url = self.request.path
            self.action_method = "category_allocation_metod"

        def get_queryset(self, queryset=None, filtered=True, *args, **kwargs):
            if not getattr(self, "queryset", None):
                self._saved_filters = self.request.GET

                self.queryset = AssetCategory.objects.filter(
                    asset_category_name__icontains=self.request.GET.get("search", "")
                )
                self.queryset = super().get_queryset(
                    self.queryset, filtered, *args, **kwargs
                )
                self.assigned_assets = Asset.objects.filter(
                    assetassignment__assigned_to_employee_id__id=self.request.GET.get(
                        "instance_id"
                    ),
                    assetassignment__return_status__isnull=True,
                ).distinct()

            return self.queryset

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            context["assigned_assets"] = self.assigned_assets
            return context

        def post(self, *args, **kwargs):
            _response = super().post(*args, **kwargs)
            ids = ast.literal_eval(self.request.POST["ids"])
            employee_id = self.request.POST["instance_id"]
            instance = Employee.objects.get(pk=employee_id)
            categories = AssetCategory.objects.filter(pk__in=ids)

            requested = []
            for category in categories:
                already_requested = AssetRequest.objects.filter(
                    requested_employee_id=instance,
                    asset_category_id=category,
                    asset_request_status__in=["Requested", "Approved"],
                ).exists()
                if already_requested:
                    continue
                asset_request = AssetRequest()
                asset_request.requested_employee_id = instance
                asset_request.asset_category_id = category
                asset_request.asset_request_status = "Requested"
                asset_request.save()
                requested.append(category)

            if requested:
                messages.success(
                    self.request, _("Asset request raised for selected categories")
                )
            else:
                messages.info(
                    self.request,
                    _("Select categories to request, or requests already exist"),
                )
            return HttpResponse(
                """
            <script>$("#reloadMessagesButton").click();$(".reload-record").click();</script>
    """
            )

    @hx_request_required
    def return_allocation(request, *args, **kwargs):
        """
        Return allocation method
        """
        asset_id = kwargs["asset_id"]
        if request.method == "POST":
            try:
                asset_allocate_return(request, asset_id)
            except:
                messages.error(request, _("An error occured"))
            return HttpResponse(
                """
                <script>$("#reloadMessagesButton").click();$(".reload-record").click();$("#genericModal").removeClass('oh-modal--show');</script>
        """
            )
        asset_return_form = AssetReturnForm()
        asset_allocation = AssetAssignment.objects.filter(
            asset_id=asset_id, return_status__isnull=True
        ).first()
        context = {"asset_return_form": asset_return_form, "asset_id": asset_id}
        context["asset_alocation"] = asset_allocation
        return render(request, "cbv/allocations/asset/return_form.html", context)


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class GroupsView(TemplateView):
    """
    GroupsView
    """

    template_name = "cbv/allocations/auth/group_view.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class Groups(TemplateView):
    """
    Groups
    """

    template_name = "cbv/allocations/auth/groups.html"

    def get(self, request, *args, **kwargs):
        context = {}
        employees = Employee.objects.filter(id=request.GET.get("instance_id"))
        emoloyee = employees.first()
        context["employee"] = emoloyee
        permissions = []
        no_permission_models = settings.NO_PERMISSION_MODALS
        for app_name in settings.APPS:
            app_models = []
            for model in get_models_in_app(app_name):
                if model._meta.model_name not in no_permission_models:
                    app_models.append(
                        {
                            "verbose_name": model._meta.verbose_name.capitalize(),
                            "model_name": model._meta.model_name,
                        }
                    )
            permissions.append(
                {
                    "app": app_name.capitalize().replace("_", " "),
                    "app_models": app_models,
                }
            )
        context["permissions"] = permissions
        context["no_permission_models"] = no_permission_models
        context["employees"] = paginator_qry(employees, request.GET.get("page"))
        return render(
            request,
            self.template_name,
            context,
        )


@method_decorator(login_required, name="dispatch")
@method_decorator(
    recruitment_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class GroupAssignView(TemplateView):
    """
    View to assign multiple groups to a single employee
    """

    template_name = "cbv/allocations/auth/group_form.html"

    def get(self, request, *args, **kwargs):
        """
        Get
        """
        employee_id = request.GET.get("employee")
        employee = Employee.objects.filter(id=employee_id).first()
        if not employee:
            return HorillaRedirect(request, message=_("Employee not found"))
        groups = employee.employee_user_id.groups.all()
        form = AddToUserGroupForm(
            initial={
                "group": groups,
                "employee": request.GET.get("employee"),
            }
        )
        return render(
            request,
            self.template_name,
            {"form": form, "employee_id": request.GET.get("employee")},
        )

    def post(self, request, *args, **kwargs):
        """
        Post
        """
        form = AddToUserGroupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Employee assigned to group"))
            return HttpResponse(
                """<script>
                $('#groupAssignBody').closest('.oh-modal.oh-modal--show').removeClass('oh-modal--show');
                $('.oh-inner-sidebar__link--active').click();
                $("#reloadMessagesButton").click();
                $(".reload-record").click();
                </script>
                """
            )
        return render(
            request,
            self.template_name,
            {"form": form, "employee_id": request.POST.get("employee")},
        )


if app_installed("payroll"):
    AllocationView.menues.append(
        {
            "menu": _("Allowance"),
            # you will get instance_id in url params
            "url": reverse_lazy("allocation-allowance"),
        }
    )
    AllocationView.menues.append(
        {
            "menu": _("Deduction"),
            # you will get instance_id in url params
            "url": reverse_lazy("allocation-deduction"),
        }
    )

    def allowance_allocation_metod(self):
        """
        Allocation method
        """
        request = getattr(_thread_locals, "request", None)
        employee = None
        if request:
            employee_id = request.GET.get("instance_id") or request.POST.get(
                "instance_id"
            )
            if employee_id:
                employee = Employee.objects.filter(pk=employee_id).first()
        return render_template(
            "cbv/allocations/payroll/allowance/actions.html",
            {"instance": self, "employee": employee},
        )

    Allowance.allowance_allocation_metod = allowance_allocation_metod

    @method_decorator(login_required, name="dispatch")
    @method_decorator(hx_request_required, name="dispatch")
    @method_decorator(
        all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
    )
    class AllowanceView(TemplateView):
        """
        AllowanceView
        """

        template_name = "cbv/allocations/payroll/allowance/allowance_view.html"

    @method_decorator(login_required, name="dispatch")
    class AllowanceList(AllowanceListView):
        """
        AllowanceList
        """

        row_attrs = """
            onclick="$(this).find('td:first [type=checkbox]').prop('checked',!$(this).find('td:first [type=checkbox]').is(':checked')).change()"
        """

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.search_url = self.request.path
            self.action_method = "allowance_allocation_metod"

        template_name = "cbv/allocations/payroll/allowance/allowance_list.html"

        show_filter_tags = False
        row_status_indications = False
        bulk_update_fields = []
        filter_selected = False

        columns = [(_("Allowance"), "title", "get_avatar")]

        def post(self, *args, **kwargs):
            employee_id = self.request.POST["instance_id"]
            self.instance = Employee.objects.get(pk=employee_id)
            if self.request.GET.get("exclude"):
                allowance = Allowance.objects.get(pk=self.request.POST["allowance_id"])
                allowance.exclude_employees.add(self.instance)
                allowance.specific_employees.remove(self.instance)

                messages.success(
                    self.request, _("Allowance excluded") + f" {allowance}"
                )
            else:
                ids = ast.literal_eval(self.request.POST["ids"])
                allowances = Allowance.objects.filter(pk__in=ids)
                for allowance in allowances:
                    allowance.exclude_employees.remove(self.instance)
                    if not allowance.include_active_employees:
                        allowance.specific_employees.add(self.instance)
                if allowances:
                    messages.success(self.request, _("Added to Selected Allowances"))
                else:
                    messages.info(self.request, _("Select Allowances to Add"))
            return HttpResponse(
                """
            <script>$("#reloadMessagesButton").click();$(".reload-record").click();</script>
    """
            )

        def get(self, request, *args, **kwargs):
            self.instance = Employee.objects.filter(
                pk=request.GET.get("instance_id")
            ).first()
            if not self.instance:
                return HttpResponse()

            return super().get(request, *args, **kwargs)

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            context["assigned_allowances"] = self.assigned_allowances
            return context

        def get_queryset(self):
            self.queryset = (
                super()
                .get_queryset()
                .filter(
                    Q(include_active_employees=True)
                    | Q(specific_employees=self.instance)
                )
                .filter(title__icontains=self.request.GET.get("search", ""))
                .distinct()
            )
            self.assigned_allowances = self.queryset.exclude(
                exclude_employees=self.instance
            )
            return self.queryset

        def dispatch(self, request, *args, **kwargs):
            """
            To avoide parent permissions
            """
            return super(AllowanceListView, self).dispatch(request, *args, **kwargs)

    def deduction_allocation_metod(self):
        """
        Allocation method
        """
        request = getattr(_thread_locals, "request", None)
        employee = None
        if request:
            employee_id = request.GET.get("instance_id") or request.POST.get(
                "instance_id"
            )
            if employee_id:
                employee = Employee.objects.filter(pk=employee_id).first()
        return render_template(
            "cbv/allocations/payroll/deduction/actions.html",
            {"instance": self, "employee": employee},
        )

    Deduction.deduction_allocation_metod = deduction_allocation_metod

    @method_decorator(login_required, name="dispatch")
    @method_decorator(hx_request_required, name="dispatch")
    @method_decorator(
        all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
    )
    class DeductionView(TemplateView):
        """
        AllowanceView
        """

        template_name = "cbv/allocations/payroll/deduction/deduction_view.html"

    @method_decorator(login_required, name="dispatch")
    @method_decorator(
        all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
    )
    class DeductionList(DeductionListView):
        """
        AllowanceList
        """

        row_attrs = """
            onclick="$(this).find('td:first [type=checkbox]').prop('checked',!$(this).find('td:first [type=checkbox]').is(':checked')).change()"
        """

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.search_url = self.request.path
            self.action_method = "deduction_allocation_metod"

        template_name = "cbv/allocations/payroll/deduction/deduction_list.html"

        show_filter_tags = False
        row_status_indications = False
        bulk_update_fields = []
        filter_selected = False

        columns = [(_("Deduction"), "title", "get_avatar")]

        def post(self, *args, **kwargs):
            employee_id = self.request.POST["instance_id"]
            self.instance = Employee.objects.get(pk=employee_id)
            if self.request.GET.get("exclude"):
                deduction = Deduction.objects.get(pk=self.request.POST["deduction_id"])
                deduction.exclude_employees.add(self.instance)
                deduction.specific_employees.remove(self.instance)

                messages.success(
                    self.request, _("Deduction excluded") + f" {deduction}"
                )
            else:
                ids = ast.literal_eval(self.request.POST["ids"])
                deductions = Deduction.objects.filter(pk__in=ids)
                for deduction in deductions:
                    deduction.exclude_employees.remove(self.instance)
                    if not deduction.include_active_employees:
                        deduction.specific_employees.add(self.instance)
                if deductions:
                    messages.success(self.request, _("Added to Selected Deductions"))
                else:
                    messages.info(self.request, _("Select Deductions to Add"))
            return HttpResponse(
                """
            <script>$("#reloadMessagesButton").click();$(".reload-record").click();</script>
    """
            )

        def get(self, request, *args, **kwargs):
            self.instance = Employee.objects.filter(
                pk=request.GET.get("instance_id")
            ).first()
            if not self.instance:
                return HttpResponse()

            return super().get(request, *args, **kwargs)

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            context["assigned_deductions"] = self.assigned_deductions
            return context

        def get_queryset(self):
            self.queryset = (
                super()
                .get_queryset()
                .filter(
                    Q(include_active_employees=True)
                    | Q(specific_employees=self.instance)
                )
                .filter(title__icontains=self.request.GET.get("search", ""))
                .distinct()
            )
            self.assigned_deductions = self.queryset.exclude(
                exclude_employees=self.instance
            )
            return self.queryset

        def dispatch(self, request, *args, **kwargs):
            """
            To avoide parent permissions
            """
            return super(DeductionListView, self).dispatch(request, *args, **kwargs)


def is_any_recruitment_manager(request, instance, *args, **kwargs):
    """
    check the user is a recruitment manager
    """
    return (
        request.user.has_perm("recruitment.change_recruitment")
        or request.user.has_perm("auth.add_group")
        or request.user.has_perm("auth.add_permission")
        or request.user.employee_get.recruitment_set.exists()
    )


def completion_percentage(self):
    total_fields = len(self._meta.fields) - 1  # Excluding id field
    filled_fields = sum(1 for field in self._meta.fields if getattr(self, field.name))

    return (filled_fields / total_fields) * 100 if total_fields > 0 else 0


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class Summary(TemplateView):
    """
    Summary
    """

    template_name = "cbv/allocations/summary.html"

    def get(self, request, *args, **kwargs):
        instance_id = request.GET.get("instance_id")

        if not instance_id:
            return HorillaRedirect(request, message=_("Employee ID missing."))

        try:
            Employee.objects.get(pk=instance_id)
        except Employee.DoesNotExist:
            return HorillaRedirect(
                request, message=_("No Employee found matching the query.")
            )

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = Employee.objects.get(pk=self.request.GET["instance_id"])
        context["instance"] = instance

        personal_info_fields = [
            "badge_id",
            "employee_first_name",
            "employee_last_name",
            "employee_profile",
            "email",
            "phone",
            "address",
            "country",
            "state",
            "city",
            "zip",
            "dob",
            "gender",
            "qualification",
            "experience",
            "marital_status",
            "emergency_contact",
            "emergency_contact_name",
            "emergency_contact_relation",
        ]
        work_info_fields = [
            "job_position_id",
            "department_id",
            "work_type_id",
            "employee_type_id",
            "job_role_id",
            "reporting_manager_id",
            "company_id",
            "location",
            "email",
            "mobile",
            "shift_id",
            "date_joining",
            "contract_end_date",
            "basic_salary",
            "salary_hour",
        ]
        bank_info_fields = [
            "bank_name",
            "account_number",
            "branch",
            "address",
            "country",
            "state",
            "city",
            "any_other_code1",
            "any_other_code2",
        ]
        personal_filled_fields = sum(
            1 for field in personal_info_fields if getattr(instance, field)
        )
        total_personal_fields = len(personal_info_fields)

        bank_instance = EmployeeBankDetails.objects.filter(employee_id=instance).first()
        work_instance = EmployeeWorkInformation.objects.filter(
            employee_id=instance
        ).first()
        context["work_percentage"] = 0
        context["bank_percentage"] = 0
        if work_instance:
            work_filled_fields = sum(
                1
                for field in work_info_fields
                if getattr(instance.employee_work_info, field)
            )
            total_work_fields = len(work_info_fields)
            context["work_percentage"] = (work_filled_fields / total_work_fields) * 100
        if bank_instance:
            bank_filled_fields = sum(
                1
                for field in bank_info_fields
                if getattr(instance.employee_bank_details, field)
            )
            total_bank_fields = len(bank_info_fields)
            context["bank_percentage"] = (bank_filled_fields / total_bank_fields) * 100

        context["personal_percentage"] = (
            personal_filled_fields / total_personal_fields
        ) * 100
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_recruitment"), name="dispatch"
)
class ToggleDashboardAccess(View):
    """
    ToggleDashboardAccess
    """

    def post(self, request, *args, **kwargs):
        """
        post
        """
        instance = Employee.objects.get(pk=request.GET["instance_id"])
        instance.employee_user_id.is_active = not instance.employee_user_id.is_active
        instance.employee_user_id.save()
        if instance.employee_user_id.is_active:
            messages.success(request, _("Dashboard access provided"))
        else:
            messages.success(request, _("Dashboard access removed"))
        return HttpResponse(
            """
        <script>$("#reloadMessagesButton").click();$(".reload-record").click();</script>
"""
        )


# AllocationView.menues.append(
#     {
#         "menu": _("Groups & Permissions"),
#         # you will get instance_id in url params
#         "url": reverse_lazy("allocation-user-group-view"),
#         "accessibility": "employee.cbv.allocations.is_any_recruitment_manager",
#     }
# )
