"""
views.py

This module is used to define the method for the path in the urls
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import groupby
from urllib.parse import parse_qs

import pandas as pd
import pdfkit
from django.conf import settings as pay_settings
from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from base.methods import (
    closest_numbers,
    eval_validate,
    export_data,
    filter_own_and_subordinate_recordes,
    generate_colors,
    generate_pdf,
    get_key_instances,
    get_session_company,
    sortby,
)
from base.models import Company
from employee.models import Employee, EmployeeWorkInformation
from horilla.decorators import (
    hx_request_required,
    login_required,
    owner_can_enter,
    permission_required,
)
from horilla.group_by import group_by_queryset
from horilla.http.response import HorillaRedirect
from notifications.signals import notify
from payroll.context_processors import get_active_employees
from payroll.filters import ContractFilter, ContractReGroup, PayslipFilter
from payroll.forms.component_forms import (
    ContractExportFieldForm,
    PayrollSettingsForm,
    PayslipAutoGenerateForm,
)
from payroll.methods.methods import paginator_qry, save_payslip
from payroll.models.models import (
    Contract,
    FilingStatus,
    PayrollGeneralSetting,
    Payslip,
    PayslipAutoGenerate,
    Reimbursement,
    ReimbursementFile,
    ReimbursementrequestComment,
)
from payroll.models.tax_models import PayrollSettings

# Create your views here.

status_choices = {
    "draft": _("Draft"),
    "review_ongoing": _("Review Ongoing"),
    "confirmed": _("Confirmed"),
    "paid": _("Paid"),
}


@login_required
@permission_required("payroll.add_contract")
def contract_create(request):
    """
    Contract create view
    """
    from payroll.forms.forms import ContractForm

    form = ContractForm()
    is_htmx = request.headers.get("HX-Request") is not None
    if request.method == "POST":
        form = ContractForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, _("Contract Created"))
            if is_htmx:
                response = HttpResponse("", status=200)
                response["HX-Trigger"] = json.dumps(
                    {"reloadPayrollContracts": {"target": "body"}}
                )
                return response
            return redirect("view-contract")
    template_name = (
        "payroll/common/form_fragment.html" if is_htmx else "payroll/common/form.html"
    )
    return render(
        request,
        template_name,
        {
            "form": form,
            "post_url": request.get_full_path(),
            "back_url": reverse("contract-filter"),
        },
    )


@login_required
@permission_required("payroll.change_contract")
def contract_update(request, contract_id, **kwargs):
    """
    Update an existing contract.

    Args:
        request: The HTTP request object.
        contract_id: The ID of the contract to update.

    Returns:
        If the request method is POST and the form is valid, redirects to the contract view.
        Otherwise, renders the contract update form.

    """
    from payroll.forms.forms import ContractForm

    contract = Contract.objects.filter(id=contract_id).first()
    is_htmx = request.headers.get("HX-Request") is not None
    if not contract:
        messages.info(request, _("The contract could not be found."))
        return redirect("view-contract")
    contract_form = ContractForm(instance=contract)
    if request.method == "POST":
        contract_form = ContractForm(request.POST, request.FILES, instance=contract)
        if contract_form.is_valid():
            contract_form.save()
            messages.success(request, _("Contract updated"))
            if is_htmx:
                response = HttpResponse("", status=200)
                response["HX-Trigger"] = json.dumps(
                    {"reloadPayrollContracts": {"target": "body"}}
                )
                return response
            return redirect(reverse("view-contract"))
    template_name = (
        "payroll/common/form_fragment.html" if is_htmx else "payroll/common/form.html"
    )
    return render(
        request,
        template_name,
        {
            "form": contract_form,
            "post_url": request.get_full_path(),
            "back_url": reverse("contract-filter"),
        },
    )


@login_required
@hx_request_required
@permission_required("payroll.change_contract")
def contract_status_update(request, contract_id):
    from payroll.forms.forms import ContractForm

    previous_data = request.GET.urlencode()
    if request.method == "POST":
        contract = Contract.objects.get(id=contract_id)
        if request.POST.get("view"):
            status = request.POST.get("status")
            if status in dict(contract.CONTRACT_STATUS_CHOICES).keys():
                save = True
                if status in ["active", "draft"]:
                    active_contract = Contract.objects.filter(
                        contract_status="active", employee_id=contract.employee_id
                    ).exists()
                    draft_contract = Contract.objects.filter(
                        contract_status="draft", employee_id=contract.employee_id
                    ).exists()
                    if (status == "active" and active_contract) or (
                        status == "draft" and draft_contract
                    ):
                        save = False
                        messages.info(
                            request,
                            _("An {} contract already exists for {}").format(
                                status, contract.employee_id
                            ),
                        )
                if save:
                    contract.contract_status = status
                    contract.save()
                    messages.success(
                        request, _("The contract status has been updated successfully.")
                    )
            else:
                messages.warning(
                    request, _("You selected the wrong option for contract status.")
                )

            return redirect(f"/payroll/contract-filter?{previous_data}")

        contract_form = ContractForm(request.POST, request.FILES, instance=contract)
        if contract_form.is_valid():
            contract_form.save()
            messages.success(request, _("Contract status updated"))
        else:
            for errors in contract_form.errors.values():
                for error in errors:
                    messages.error(request, error)
        return HttpResponse("<script>$('#reloadMessagesButton').click()</script>")


@login_required
@permission_required("payroll.change_contract")
def bulk_contract_status_update(request):
    status = request.POST.get("status")
    ids = request.POST.get("ids")
    ids = eval_validate(ids) if ids else []
    all_contracts = Contract.objects.all()
    contracts = all_contracts.filter(id__in=ids)

    for contract in contracts:
        save = True
        if status in ["active", "draft"]:
            active_contract = all_contracts.filter(
                contract_status="active", employee_id=contract.employee_id
            ).exists()
            draft_contract = all_contracts.filter(
                contract_status="draft", employee_id=contract.employee_id
            ).exists()
            if (status == "active" and active_contract) or (
                status == "draft" and draft_contract
            ):
                save = False
                messages.info(
                    request,
                    _("An {} contract already exists for {}").format(
                        status, contract.employee_id
                    ),
                )
        if save:
            contract.contract_status = status
            contract.save()
            messages.success(
                request, _("The contract status has been updated successfully.")
            )
    return HttpResponse("success")


@login_required
@permission_required("payroll.change_contract")
@require_http_methods(["POST"])
def update_contract_filing_status(request, contract_id):
    if request.method == "POST":
        contract = get_object_or_404(Contract, id=contract_id)
        filing_status_id = request.POST.get("filing_status")
        try:
            filing_status = (
                FilingStatus.objects.get(id=int(filing_status_id))
                if filing_status_id
                else None
            )
            contract.filing_status = filing_status
            messages.success(
                request, _("The employee filing status has been updated successfully.")
            )
        except (ValueError, OverflowError, FilingStatus.DoesNotExist):
            messages.warning(
                request, _("You selected the wrong option for filing status.")
            )
        contract.save()
        return redirect("contract-filter")


@login_required
@hx_request_required
@permission_required("payroll.delete_contract")
def contract_delete(request, contract_id):
    """
    Delete a contract.

    Args:
        contract_id: The ID of the contract to delete.

    Returns:
        Redirects to the contract view after successfully deleting the contract.

    """
    try:
        Contract.objects.get(id=contract_id).delete()
        messages.success(request, _("Contract deleted"))
        request_path = request.path.split("/")
        if "delete-contract-modal" in request_path:
            if instances_ids := request.GET.get("instances_ids"):
                get_data = request.GET.copy()
                get_data.pop("instances_ids", None)
                previous_data = get_data.urlencode()
                instances_list = json.loads(instances_ids)
                previous_instance, next_instance = closest_numbers(
                    instances_list, contract_id
                )
                if contract_id in instances_list:
                    instances_list.remove(contract_id)
                urls = f"/payroll/single-contract-view/{next_instance}/"
                params = f"?{previous_data}&instances_ids={instances_list}"
                return redirect(urls + params)
            return HorillaRedirect(request)
        else:
            return redirect(f"/payroll/contract-filter?{request.GET.urlencode()}")
    except Contract.DoesNotExist:
        messages.error(request, _("Contract not found."))
    except ProtectedError:
        messages.error(request, _("You cannot delete this contract."))
    return HorillaRedirect(request)


@login_required
@permission_required("payroll.view_contract")
def contract_view(request):
    """
    Contract view method
    """

    contracts = Contract.objects.all()
    if contracts.exists():
        template = "payroll/contract/contract_view.html"
    else:
        template = "payroll/contract/contract_empty.html"

    contracts = paginator_qry(contracts, request.GET.get("page"))
    contract_ids_json = json.dumps([instance.id for instance in contracts.object_list])
    filter_form = ContractFilter(request.GET)
    context = {
        "contracts": contracts,
        "f": filter_form,
        "contract_ids": contract_ids_json,
        "gp_fields": ContractReGroup.fields,
    }

    return render(request, template, context)


@login_required
# @hx_request_required         #this function is also used in payroll dashboard which uses ajax
@owner_can_enter("payroll.view_contract", Contract)
def view_single_contract(request, contract_id):
    """
    Renders a single contract view page.
    """
    get_data = request.GET.copy()
    get_data.pop("instances_ids", None)
    previous_data = get_data.urlencode()
    dashboard = request.GET.get("dashboard", "")

    HTTP_REFERERS = request.META.get("HTTP_REFERER", "").split("/")
    delete_hx_target = (
        "#personal_target"
        if "employee-view" in HTTP_REFERERS or "employee-profile" in HTTP_REFERERS
        else "#objectDetailsModalTarget"
    )

    contract = Contract.find(contract_id)

    context = {
        "contract": contract,
        "dashboard": dashboard,
        "delete_hx_target": delete_hx_target,
        "pd": previous_data,
    }

    contract_ids_json = request.GET.get("instances_ids")
    if contract_ids_json:
        contract_ids = json.loads(contract_ids_json)
        previous_id, next_id = closest_numbers(contract_ids, contract_id)
        context.update(
            {
                "previous": previous_id,
                "next": next_id,
                "contract_ids": contract_ids_json,
            }
        )
    return render(request, "payroll/contract/contract_single_view.html", context)


@login_required
@hx_request_required
@permission_required("payroll.view_contract")
def contract_filter(request):
    """
    Filter contracts based on the provided query parameters.

    Args:
        request: The HTTP request object containing the query parameters.

    Returns:
        Renders the contract list template with the filtered contracts.

    """
    query_string = request.GET.urlencode()
    contracts_filter = ContractFilter(request.GET)
    template = "payroll/contract/contract_list.html"
    contracts = contracts_filter.qs
    field = request.GET.get("field")

    if field != "" and field is not None:
        contracts = group_by_queryset(contracts, field, request.GET.get("page"), "page")
        list_values = [entry["list"] for entry in contracts]
        id_list = []
        for value in list_values:
            for instance in value.object_list:
                id_list.append(instance.id)

        contract_ids_json = json.dumps(list(id_list))
        template = "payroll/contract/group_by.html"

    else:
        contracts = sortby(request, contracts, "orderby")
        contracts = paginator_qry(contracts, request.GET.get("page"))
        contract_ids_json = json.dumps(
            [instance.id for instance in contracts.object_list]
        )

    data_dict = parse_qs(query_string)
    get_key_instances(Contract, data_dict)
    keys_to_remove = [key for key, value in data_dict.items() if value == ["unknown"]]
    for key in keys_to_remove:
        data_dict.pop(key)
    if "contract_status" in data_dict:
        status_list = data_dict["contract_status"]
        if len(status_list) > 1:
            data_dict["contract_status"] = [status_list[-1]]
    return render(
        request,
        template,
        {
            "contracts": contracts,
            "pd": query_string,
            "filter_dict": data_dict,
            "contract_ids": contract_ids_json,
            "field": field,
        },
    )


@login_required
@permission_required("payroll.view_payrollsettings")
def settings(request):
    """
    This method is used to render settings template
    """
    tracking_company = get_session_company(request)
    instance, _created = PayrollSettings.objects.get_or_create(
        company_id=tracking_company
    )
    currency_form = PayrollSettingsForm(instance=instance)

    if request.method == "POST":

        currency_form = PayrollSettingsForm(request.POST, instance=instance)
        if currency_form.is_valid():

            currency_form.save()
            messages.success(request, _("Payroll settings updated."))
            if request.headers.get("HX-Request"):
                return HttpResponse("")
            return HorillaRedirect(request)
        else:
            messages.error(request, _("There was an error updating the currency."))
            if request.headers.get("HX-Request"):
                return HttpResponse("", status=400)
    if request.headers.get("HX-Request"):
        return HttpResponse("", status=400)
    return HorillaRedirect(request)


@login_required
@permission_required("payroll.change_payslip")
def update_payslip_status(request, payslip_id):
    """
    This method is used to update the payslip confirmation status
    """
    status = request.POST.get("status")
    view = request.POST.get("view")
    payslip = Payslip.objects.filter(id=payslip_id).first()
    if not payslip:
        return HorillaRedirect(request, message=_("Payslip not found."))
    if payslip:
        payslip.status = status
        payslip.save()
        messages.success(request, _("Payslip status updated"))
    else:
        messages.error(request, _("Payslip not found"))
    if view:
        from .component_views import filter_payslip

        return redirect(reverse("payslip-list"))
    data = payslip.pay_head_data
    data["employee"] = payslip.employee_id
    data["payslip"] = payslip
    data["json_data"] = data.copy()
    data["json_data"]["employee"] = payslip.employee_id.id
    data["json_data"]["payslip"] = payslip.id
    data["instance"] = payslip
    return render(request, "payroll/payslip/individual_payslip_summery.html", data)


@login_required
@hx_request_required
def update_payslip_status_no_id(request):
    """
    This method is used to update the payslip confirmation status
    """
    message = {"type": "success", "message": "Payslip status updated."}
    if request.method == "POST":
        ids_json = request.POST["ids"]
        ids = json.loads(ids_json)
        status = request.POST["status"]
        slips = Payslip.objects.filter(id__in=ids)
        slips.update(status=status)
        message = {
            "type": "success",
            "message": f"{slips.count()} Payslips status updated.",
        }
    return JsonResponse(message)


@login_required
def view_payslip_pdf(request, payslip_id):

    from .component_views import filter_payslip

    if Payslip.objects.filter(id=payslip_id).exists():
        payslip = Payslip.objects.get(id=payslip_id)
        company = Company.objects.filter(hq=True).first()
        if (
            request.user.has_perm("payroll.view_payslip")
            or payslip.employee_id.employee_user_id == request.user
        ):
            user = request.user
            employee = user.employee_get

            # Taking the company_name of the user
            info = EmployeeWorkInformation.objects.filter(employee_id=employee)
            if info.exists():
                for data in info:
                    employee_company = data.company_id
                company_name = Company.objects.filter(company=employee_company)
                emp_company = company_name.first()

                # Access the date_format attribute directly
                date_format = (
                    emp_company.date_format
                    if emp_company and emp_company.date_format
                    else "MMM. D, YYYY"
                )
            else:
                date_format = "MMM. D, YYYY"

            data = payslip.pay_head_data
            start_date_str = data["start_date"]
            end_date_str = data["end_date"]

            # Convert the string to a datetime.date object
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

            month_start_name = start_date.strftime("%B %d, %Y")
            month_end_name = end_date.strftime("%B %d, %Y")
            # Formatted date for each format
            for format_name, format_string in pay_settings.HORILLA_DATE_FORMATS.items():
                if format_name == date_format:
                    formatted_start_date = start_date.strftime(format_string)

            for format_name, format_string in pay_settings.HORILLA_DATE_FORMATS.items():
                if format_name == date_format:
                    formatted_end_date = end_date.strftime(format_string)
            data["month_start_name"] = month_start_name
            data["month_end_name"] = month_end_name
            data["formatted_start_date"] = formatted_start_date
            data["formatted_end_date"] = formatted_end_date
            data["employee"] = payslip.employee_id
            data["payslip"] = payslip
            data["json_data"] = data.copy()
            data["json_data"]["employee"] = payslip.employee_id.id
            data["json_data"]["payslip"] = payslip.id
            data["instance"] = payslip
            data["currency"] = PayrollSettings.objects.first().currency_symbol
            data["all_deductions"] = []
            for deduction_list in [
                data["basic_pay_deductions"],
                data["gross_pay_deductions"],
                data["pretax_deductions"],
                data["post_tax_deductions"],
                data["tax_deductions"],
                data["net_deductions"],
            ]:
                data["all_deductions"].extend(deduction_list)

            data["all_allowances"] = data["allowances"].copy()
            equalize_lists_length(data["allowances"], data["all_deductions"])
            data["zipped_data"] = zip(data["allowances"], data["all_deductions"])
            data["host"] = request.get_host()
            data["protocol"] = "https" if request.is_secure() else "http"
            data["company"] = company

            return render(request, "payroll/payslip/payslip_pdf.html", context=data)
        return redirect(filter_payslip)
    return render(request, "405.html")


@login_required
# @permission_required("payroll.view_payslip")
def view_created_payslip(request, payslip_id, **kwargs):
    """
    This method is used to view the saved payslips
    """
    payslip = Payslip.objects.filter(id=payslip_id).first()
    if payslip is not None and (
        request.user.has_perm("payroll.view_payslip")
        or payslip.employee_id.employee_user_id == request.user
    ):
        # the data must be dictionary in the payslip model for the json field
        data = payslip.pay_head_data
        data["employee"] = payslip.employee_id
        data["payslip"] = payslip
        data["json_data"] = data.copy()
        data["json_data"]["employee"] = payslip.employee_id.id
        data["json_data"]["payslip"] = payslip.id
        data["instance"] = payslip
        return render(request, "payroll/payslip/individual_payslip.html", data)
    return render(request, "404.html")


@login_required
@permission_required("payroll.delete_payslip")
def delete_payslip(request, payslip_id):
    """
    This method is used to delete payslip instances
    Args:
        payslip_id (int): Payslip model instance id
    """
    from .component_views import filter_payslip

    try:
        Payslip.objects.get(id=payslip_id).delete()
        messages.success(request, _("Payslip deleted"))
    except Payslip.DoesNotExist:
        messages.error(request, _("Payslip not found."))
    except ProtectedError:
        messages.error(request, _("Something went wrong"))
    if request.headers.get("HX-Request"):
        response = HttpResponse("", status=200)
        response["HX-Trigger"] = json.dumps(
            {"reloadPayrollPayslips": {"target": "body"}}
        )
        return response
    if not Payslip.objects.filter():
        return HorillaRedirect(request)
    return redirect(reverse("payslip-list"))


@login_required
@permission_required("payroll.add_contract")
def contract_info_initial(request):
    """
    This is an ajax method to return json response to auto fill the contract
    form fields
    """
    employee_id = request.GET.get("employee_id")
    if not employee_id:
        messages.error(request, _("Missing required parameter"))
        return JsonResponse(
            {"error": "Missing required parameter: employee_id"}, status=400
        )
    work_info = EmployeeWorkInformation.objects.filter(employee_id=employee_id).first()
    response_data = {
        "department": (
            work_info.department_id.id if work_info.department_id is not None else ""
        ),
        "job_position": (
            work_info.job_position_id.id
            if work_info.job_position_id is not None
            else ""
        ),
        "job_role": (
            work_info.job_role_id.id if work_info.job_role_id is not None else ""
        ),
        "shift": work_info.shift_id.id if work_info.shift_id is not None else "",
        "work_type": (
            work_info.work_type_id.id if work_info.work_type_id is not None else ""
        ),
        "wage": work_info.basic_salary,
        "contract_start_date": work_info.date_joining if work_info.date_joining else "",
        "contract_end_date": (
            work_info.contract_end_date if work_info.contract_end_date else ""
        ),
    }
    return JsonResponse(response_data)


@login_required
@permission_required("payroll.view_contract")
def view_payroll_dashboard(request):
    """
    Dashboard rendering views
    """
    from payroll.forms.forms import DashboardExport

    paid = Payslip.objects.filter(status="paid")
    posted = Payslip.objects.filter(status="confirmed")
    review_ongoing = Payslip.objects.filter(status="review_ongoing")
    draft = Payslip.objects.filter(status="draft")
    export_form = DashboardExport()
    context = {
        "paid": paid,
        "posted": posted,
        "review_ongoing": review_ongoing,
        "draft": draft,
        "export_form": export_form,
    }
    return render(request, "payroll/dashboard.html", context=context)


@login_required
def dashboard_employee_chart(request):
    """
    payroll dashboard employee chart data
    """

    date = request.GET.get("period", datetime.now().strftime("%Y-%m"))
    year, month = date.split("-")
    dataset = []
    employee_label = []
    list_of_employees = []

    response = {
        "dataset": dataset,
        "labels": employee_label,
        "employees": list_of_employees,
        "message": _("No payslips generated for this month."),
    }
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax and request.method == "GET":
        employee_list = Payslip.objects.filter(
            Q(start_date__month=month) & Q(start_date__year=year)
        )
        labels = []
        for employee in employee_list:
            labels.append(employee.employee_id)

        colors = [
            "rgba(255, 99, 132, 1)",  # Red
            "rgba(255, 206, 86, 1)",  # Yellow
            "rgba(54, 162, 235, 1)",  # Blue
            "rgba(75, 242, 182, 1)",  # green
        ]

        for choice, color in zip(Payslip.status_choices, colors):
            dataset.append(
                {
                    "label": choice[0],
                    "data": [],
                    "backgroundColor": color,
                }
            )

        employees = [employee.employee_id for employee in employee_list]

        employees = list(set(employees))
        total_pay_with_status = defaultdict(lambda: defaultdict(float))

        for label in employees:
            payslips = employee_list.filter(employee_id=label)
            for payslip in payslips:
                total_pay_with_status[payslip.status][label] += round(
                    payslip.net_pay, 2
                )

        for data in dataset:
            dataset_label = data["label"]
            data["data"] = [
                total_pay_with_status[dataset_label][label] for label in employees
            ]

        for employee in employees:
            employee_label.append(
                f"{employee.employee_first_name} {employee.employee_last_name}"
            )

        for value, choice in zip(dataset, Payslip.status_choices):
            if value["label"] == choice[0]:
                value["label"] = choice[1]

        list_of_employees = list(
            Employee.objects.values_list(
                "id", "employee_first_name", "employee_last_name"
            )
        )
        response = {
            "dataset": dataset,
            "labels": employee_label,
            "employees": list_of_employees,
            "message": _("No payslips generated for this month."),
        }
    return JsonResponse(response)


@login_required
def payslip_details(request):
    """
    payroll dashboard payslip details data
    """

    date = request.GET.get("period", datetime.now().strftime("%Y-%m"))
    year, month = date.split("-")
    employee_list = []
    employee_list = Payslip.objects.filter(
        Q(start_date__month=month) & Q(start_date__year=year)
    )
    total_amount = 0
    for employee in employee_list:
        total_amount += employee.net_pay

    response = {
        "no_of_emp": len(employee_list),
        "total_amount": round(total_amount, 2),
    }
    return JsonResponse(response)


@login_required
def dashboard_department_chart(request):
    """
    payroll dashboard department chart data
    """

    date = request.GET.get("period", datetime.now().strftime("%Y-%m"))
    year, month = date.split("-")
    dataset = [
        {
            "label": "",
            "data": [],
            "backgroundColor": ["#8de5b3", "#f0a8a6", "#8ed1f7", "#f8e08e", "#c2c7cc"],
        }
    ]
    department = []
    department_total = []

    response = {
        "dataset": dataset,
        "labels": department,
        "department_total": department_total,
        "message": _("No payslips generated for this month."),
    }

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax and request.method == "GET":
        payslips = Payslip.objects.filter(
            start_date__month=month, start_date__year=year
        )

        department_totals = defaultdict(float)

        for slip in payslips:
            try:
                dept = slip.employee_id.get_department().department
                department_totals[dept] += round(slip.net_pay, 2)
            except Exception as e:
                print(e)

        departments = list(department_totals.keys())

        department_total = [
            {"department": dept, "amount": amount}
            for dept, amount in department_totals.items()
        ]

        colors = generate_colors(len(departments))
        dataset = [
            {
                "label": "",
                "data": list(department_totals.values()),
                "backgroundColor": colors,
            }
        ]
        response = {
            "dataset": dataset,
            "labels": departments,
            "department_total": department_total,
            "message": _("No payslips generated for this month."),
        }
    return JsonResponse(response)


def contract_ending(request):
    """
    payroll dashboard contract ending details data
    """

    date = request.GET.get("period")
    month = date.split("-")[1]
    year = date.split("-")[0]

    if request.GET.get("initialLoad") == "true":
        if month == "12":
            month = 0
            year = int(year) + 1

        contract_end = Contract.objects.filter(
            contract_end_date__month=int(month) + 1, contract_end_date__year=int(year)
        )
    else:
        contract_end = Contract.objects.filter(
            contract_end_date__month=int(month), contract_end_date__year=int(year)
        )

    ending_contract = []
    for contract in contract_end:
        ending_contract.append(
            {"contract_name": contract.contract_name, "contract_id": contract.id}
        )

    response = {
        "contract_end": ending_contract,
        "message": _("No contracts ending this month"),
    }
    return JsonResponse(response)


@login_required
def payslip_export(request):
    """
    payroll dashboard exporting to excell data

    Args:
    - request (HttpRequest): The HTTP request object.
    - contract_id (int): The ID of the contract to view.

    """

    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")
    employee = request.POST.getlist("employees")
    status = request.POST.get("status")
    contributions = (
        request.POST.getlist("contributions")
        if request.POST.getlist("contributions")
        else get_active_employees(None)["get_active_employees"].values_list(
            "id", flat=True
        )
    )
    department = []
    total_amount = 0

    table1_data = []
    table2_data = []
    table3_data = []
    table4_data = []
    table5_data = []

    employee_payslip_list = Payslip.objects.all()

    if start_date:
        employee_payslip_list = employee_payslip_list.filter(start_date__gte=start_date)

    if end_date:
        employee_payslip_list = employee_payslip_list.filter(end_date__lte=end_date)

    if employee:
        employee_payslip_list = employee_payslip_list.filter(employee_id__in=employee)

    if status:
        employee_payslip_list = employee_payslip_list.filter(status=status)

    for employ in contributions:
        payslips = Payslip.objects.filter(employee_id__id=employ)
        if end_date:
            payslips = Payslip.objects.filter(
                employee_id__id=employ, end_date__lte=end_date
            )
        if start_date:
            payslips = Payslip.objects.filter(
                employee_id__id=employ, start_date__gte=start_date
            )
            if end_date:
                payslips = payslips.filter(end_date__lte=end_date)
        pay_heads = payslips.values_list("pay_head_data", flat=True)
        # contribution_deductions = []
        deductions = []
        for head in pay_heads:
            for deduction in head["gross_pay_deductions"]:
                if deduction.get("deduction_id"):
                    deductions.append(deduction)
            for deduction in head["basic_pay_deductions"]:
                if deduction.get("deduction_id"):
                    deductions.append(deduction)
            for deduction in head["pretax_deductions"]:
                if deduction.get("deduction_id"):
                    deductions.append(deduction)
            for deduction in head["post_tax_deductions"]:
                if deduction.get("deduction_id"):
                    deductions.append(deduction)
            for deduction in head["tax_deductions"]:
                if deduction.get("deduction_id"):
                    deductions.append(deduction)
            for deduction in head["net_deductions"]:
                deductions.append(deduction)

        deductions.sort(key=lambda x: x["deduction_id"])
        grouped_deductions = {
            key: list(group)
            for key, group in groupby(deductions, key=lambda x: x["deduction_id"])
        }

        for deduction_id, group in grouped_deductions.items():
            employee_contribution = sum(item["amount"] for item in group)
            try:
                employer_contribution = sum(
                    item["employer_contribution_amount"] for item in group
                )
            except (KeyError, TypeError):
                employer_contribution = 0
            if employer_contribution > 0:
                table5_data.append(
                    {
                        "Employee": Employee.objects.get(id=employ),
                        "Employer Contribution": employer_contribution,
                        "Employee Contribution": employee_contribution,
                    }
                )

    date_format = request.user.employee_get.get_date_format()
    if employee_payslip_list:
        for payslip in employee_payslip_list:

            start_date_str = str(payslip.start_date)
            end_date_str = str(payslip.end_date)

            # Convert the string to a datetime.date object
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            for format_name, format_string in pay_settings.HORILLA_DATE_FORMATS.items():
                if format_name == date_format:
                    formatted_start_date = start_date.strftime(format_string)

            for format_name, format_string in pay_settings.HORILLA_DATE_FORMATS.items():
                if format_name == date_format:
                    formatted_end_date = end_date.strftime(format_string)

            table1_data.append(
                {
                    "employee": f"{payslip.employee_id.employee_first_name} {payslip.employee_id.employee_last_name}",
                    "start_date": formatted_start_date,
                    "end_date": formatted_end_date,
                    "basic_pay": round(payslip.basic_pay, 2),
                    "deduction": round(payslip.deduction, 2),
                    "allowance": round(payslip.gross_pay - payslip.basic_pay, 2),
                    "gross_pay": round(payslip.gross_pay, 2),
                    "net_pay": round(payslip.net_pay, 2),
                    "status": status_choices.get(payslip.status),
                },
            )
    else:
        table1_data.append(
            {
                "employee": "None",
                "start_date": "None",
                "end_date": "None",
                "basic_pay": "None",
                "deduction": "None",
                "allowance": "None",
                "gross_pay": "None",
                "net_pay": "None",
                "status": "None",
            },
        )

    for employee in employee_payslip_list:
        try:
            department.append(
                employee.employee_id.employee_work_info.department_id.department
            )
        except Exception as e:
            print(e)

    department = list(set(department))

    for depart in department:
        table2_data.append({"Department": depart, "Amount": 0})

    for employee in employee_payslip_list:
        try:
            employee_department = (
                employee.employee_id.employee_work_info.department_id.department
            )
        except Exception as e:
            print(e)

        for depart in table2_data:
            if depart["Department"] == employee_department:
                depart["Amount"] += round(employee.net_pay, 2)

    if not employee_payslip_list:
        table2_data.append({"Department": "None", "Amount": 0})

    contract_end = Contract.objects.all()
    if not start_date and not end_date:
        contract_end = contract_end.filter(
            Q(contract_end_date__month=datetime.now().month)
            & Q(contract_end_date__year=datetime.now().year)
        )
    if end_date:
        contract_end = contract_end.filter(contract_end_date__lte=end_date)

    if start_date:
        if not end_date:
            contract_end = contract_end.filter(
                Q(contract_end_date__gte=start_date)
                & Q(contract_end_date__lte=datetime.now())
            )
        else:
            contract_end = contract_end.filter(contract_end_date__gte=start_date)

    table3_data = {"contract_ending": []}

    for contract in contract_end:
        table3_data["contract_ending"].append(contract.contract_name)

    if not contract_end:
        table3_data["contract_ending"].append("None")

    for employee in employee_payslip_list:
        total_amount += round(employee.net_pay, 2)

    table4_data = {
        "no_of_payslip_generated": len(employee_payslip_list),
        "total_amount": [total_amount],
    }

    df_table1 = pd.DataFrame(table1_data)
    df_table2 = pd.DataFrame(table2_data)
    df_table3 = pd.DataFrame(table3_data)
    df_table4 = pd.DataFrame(table4_data)
    df_table5 = pd.DataFrame(table5_data)

    df_table1 = df_table1.rename(
        columns={
            "employee": "Employee",
            "start_date": "Start Date",
            "end_date": "End Date",
            "deduction": "Deduction",
            "allowance": "Allowance",
            "gross_pay": "Gross Pay",
            "net_pay": "Net Pay",
            "status": "Status",
        }
    )

    df_table3 = df_table3.rename(
        columns={
            "contract_ending": (
                f"Contract Ending {start_date} to {end_date}"
                if start_date and end_date
                else f"Contract Ending"
            ),
        }
    )

    df_table4 = df_table4.rename(
        columns={
            "no_of_payslip_generated": "Number of payslips generated",
            "total_amount": "Total Amount",
        }
    )

    df_table5 = df_table5.rename(
        columns={
            "contract_ending": (
                f"Employee - Employer Contributions {start_date} to {end_date}"
                if start_date and end_date
                else f"Contract Ending"
            ),
        }
    )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=payslip.xlsx"

    writer = pd.ExcelWriter(response, engine="xlsxwriter")
    df_table1.to_excel(
        writer, sheet_name="Payroll Dashboard details", index=False, startrow=3
    )
    df_table2.to_excel(
        writer,
        sheet_name="Payroll Dashboard details",
        index=False,
        startrow=len(df_table1) + 3 + 3,
    )
    df_table3.to_excel(
        writer,
        sheet_name="Payroll Dashboard details",
        index=False,
        startrow=len(df_table1) + 3 + len(df_table2) + 6,
    )
    df_table5.to_excel(
        writer,
        sheet_name="Payroll Dashboard details",
        index=False,
        startrow=len(df_table1) + 3 + len(df_table2) + len(df_table3) + 9,
    )
    df_table4.to_excel(
        writer,
        sheet_name="Payroll Dashboard details",
        index=False,
        startrow=len(df_table1)
        + 3
        + len(df_table2)
        + len(df_table3)
        + len(df_table5)
        + 12,
    )

    workbook = writer.book
    worksheet = writer.sheets["Payroll Dashboard details"]
    max_columns = max(
        len(df_table1.columns),
        len(df_table2.columns),
        len(df_table3.columns),
        len(df_table4.columns),
        len(df_table5.columns),
    )

    heading_format = workbook.add_format(
        {
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#eb7968",
            "font_size": 20,
        }
    )

    worksheet.set_row(0, 30)
    worksheet.merge_range(
        0,
        0,
        0,
        max_columns - 1,
        (
            f"Payroll details {start_date} to {end_date}"
            if start_date and end_date
            else f"Payroll details"
        ),
        heading_format,
    )

    header_format = workbook.add_format(
        {"bg_color": "#eb7968", "bold": True, "text_wrap": True}
    )

    for col_num, value in enumerate(df_table1.columns.values):
        worksheet.write(3, col_num, value, header_format)
        col_letter = chr(65 + col_num)

        header_width = max(len(value) + 2, len(df_table1[value].astype(str).max()) + 2)
        worksheet.set_column(f"{col_letter}:{col_letter}", header_width)

    for col_num, value in enumerate(df_table2.columns.values):
        worksheet.write(len(df_table1) + 3 + 3, col_num, value, header_format)
        col_letter = chr(65 + col_num)

        header_width = max(len(value) + 2, len(df_table2[value].astype(str).max()) + 2)
        worksheet.set_column(f"{col_letter}:{col_letter}", header_width)

    for col_num, value in enumerate(df_table3.columns.values):
        worksheet.write(
            len(df_table1) + 3 + len(df_table2) + 6, col_num, value, header_format
        )
        col_letter = chr(65 + col_num)

        header_width = max(len(value) + 2, len(df_table3[value].astype(str).max()) + 2)
        worksheet.set_column(f"{col_letter}:{col_letter}", header_width)

    for col_num, value in enumerate(df_table5.columns.values):
        worksheet.write(
            len(df_table1) + 3 + len(df_table2) + len(df_table3) + 9,
            col_num,
            value,
            header_format,
        )
        col_letter = chr(65 + col_num)

    for col_num, value in enumerate(df_table4.columns.values):
        worksheet.write(
            len(df_table1) + 3 + len(df_table2) + len(df_table3) + len(df_table5) + 12,
            col_num,
            value,
            header_format,
        )
        col_letter = chr(65 + col_num)

        header_width = max(len(value) + 2, len(df_table4[value].astype(str).max()) + 2)
        worksheet.set_column(f"{col_letter}:{col_letter}", header_width)

    worksheet.set_row(len(df_table1) + len(df_table2) + 9, 30)

    writer.close()

    return response


@login_required
@permission_required("payroll.delete_payslip")
def payslip_bulk_delete(request):
    """
    This method is used to bulk delete for Payslip
    """
    ids = request.POST.get("ids")
    if not ids:
        messages.error(request, _("Missing required parameters."))
        return JsonResponse({"message": "Missing required parameters."}, status=400)

    ids = json.loads(ids)
    for id in ids:
        try:
            payslip = Payslip.objects.get(id=id)
            period = f"{payslip.start_date} to {payslip.end_date}"
            payslip.delete()
            messages.success(
                request,
                _("{employee} {period} payslip deleted.").format(
                    employee=payslip.employee_id, period=period
                ),
            )
        except Payslip.DoesNotExist:
            messages.error(request, _("Payslip not found."))
        except ProtectedError:
            messages.error(
                request,
                _("You cannot delete {payslip}").format(payslip=payslip),
            )
    return JsonResponse({"message": "Success"})


@login_required
@permission_required("payroll.change_payslip")
def slip_group_name_update(request):
    """
    This method is used to update the group of the payslip
    """
    new_name = request.POST.get("newName")
    group_name = request.POST.get("previousName")

    if not new_name or not group_name:
        return JsonResponse(
            {"type": "error", "message": "Missing required parameters."}, status=400
        )

    Payslip.objects.filter(group_name=group_name).update(group_name=new_name)
    return JsonResponse(
        {"type": "success", "message": "Batch name updated.", "new_name": new_name}
    )


@login_required
@permission_required("payroll.add_contract")
def contract_export(request):
    hx_request = request.META.get("HTTP_HX_REQUEST")
    if hx_request:
        export_filter = ContractFilter()
        export_column = ContractExportFieldForm()
        content = {
            "export_filter": export_filter,
            "export_column": export_column,
        }
        return render(
            request,
            "payroll/contract/contract_export_filter.html",
            context=content,
        )
    return export_data(
        request=request,
        model=Contract,
        filter_class=ContractFilter,
        form_class=ContractExportFieldForm,
        file_name="Contract_export",
    )


@login_required
@permission_required("payroll.delete_contract")
def contract_bulk_delete(request):
    """
    This method is used to bulk delete Contract
    """
    ids = request.POST.get("ids")
    if not ids:
        messages.error(request, _("No IDs provided for deletion."))
        return JsonResponse({"message": "error."}, status=400)
    ids = json.loads(ids)
    for id in ids:
        try:
            contract = Contract.objects.get(id=id)
            name = f"{contract.contract_name}"
            contract.delete()
            messages.success(
                request,
                _("{name} deleted.").format(name=name),
            )
        except Payslip.DoesNotExist:
            messages.error(request, _("Contract not found."))
        except ProtectedError:
            messages.error(
                request,
                _("You cannot delete {contract}").format(contract=contract),
            )
    return JsonResponse({"message": "Success"})


def equalize_lists_length(allowances, deductions):
    """
    Equalize the lengths of two lists by appending empty dictionaries to the shorter list.

    Args:
    deductions (list): List of dictionaries representing deductions.
    allowances (list): List of dictionaries representing allowances.

    Returns:
    tuple: Tuple containing two lists with equal lengths.
    """
    num_deductions = len(deductions)
    num_allowances = len(allowances)

    while num_deductions < num_allowances:
        deductions.append({"title": "", "amount": ""})
        num_deductions += 1

    while num_allowances < num_deductions:
        allowances.append({"title": "", "amount": ""})
        num_allowances += 1

    return deductions, allowances


def generate_payslip_pdf(template_path, context, html=False):
    """
    Generate a PDF file from an HTML template and context data.

    Args:
        template_path (str): The path to the HTML template.
        context (dict): The context data to render the template.
        html (bool): If True, return raw HTML instead of a PDF.

    Returns:
        HttpResponse: A response with the generated PDF file or raw HTML.
    """

    from horilla.horilla_middlewares import _thread_locals

    try:
        # Render the HTML content from the template and context
        html_content = render_to_string(template_path, context)
        request = getattr(_thread_locals, "request")
        cookies = None
        if request:
            cookies = request.META.get("HTTP_COOKIE", "")

        # Return raw HTML if requested
        if html:
            return HttpResponse(html_content, content_type="text/html")

        # PDF options for pdfkit
        pdf_options = {
            "page-size": "A4",
            "margin-top": "10mm",
            "margin-bottom": "10mm",
            "margin-left": "10mm",
            "margin-right": "10mm",
            "encoding": "UTF-8",
            "enable-local-file-access": None,  # Required to load local CSS/images
            "dpi": 300,
            "zoom": 1.3,
            "footer-center": "[page]/[topage]",  # Required to load local CSS/images
        }

        if cookies:
            pdf_options.update(
                {
                    "custom-header": [
                        ("Cookie", cookies),
                    ],
                    "custom-header-propagation": None,
                }
            )

        # Generate the PDF as binary content
        pdf = pdfkit.from_string(html_content, False, options=pdf_options)

        # Return an HttpResponse containing the PDF content
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = "inline; filename=payslip.pdf"
        return response
    except Exception as e:
        # Handle errors gracefully
        return HttpResponse(f"Error generating PDF: {str(e)}", status=500)


@login_required
def payslip_pdf(request, id):
    """
    Generate the payslip as a PDF and return it in an HttpResponse.

    Args:
        request (HttpRequest): The request object.
        id (int): The ID of the payslip to generate.

    Returns:
        HttpResponse: A response containing the PDF content.
    """

    from .component_views import filter_payslip

    if Payslip.objects.filter(id=id).exists():
        payslip = Payslip.objects.get(id=id)
        company = Company.objects.filter(hq=True).first()
        if (
            request.user.has_perm("payroll.view_payslip")
            or payslip.employee_id.employee_user_id == request.user
        ):
            user = request.user
            employee = user.employee_get

            # Taking the company_name of the user
            info = EmployeeWorkInformation.objects.filter(employee_id=employee)
            date_format = "MMM. D, YYYY"
            if info.exists():
                for data in info:
                    employee_company = data.company_id
                company_name = Company.objects.filter(company=employee_company)
                emp_company = company_name.first()

                # Access the date_format attribute directly
                date_format = (
                    emp_company.date_format
                    if emp_company and emp_company.date_format
                    else "MMM. D, YYYY"
                )

            data = payslip.pay_head_data
            start_date_str = data["start_date"]
            end_date_str = data["end_date"]

            # Convert the string to a datetime.date object
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

            # Format the start and end dates
            for format_name, format_string in pay_settings.HORILLA_DATE_FORMATS.items():
                if format_name == date_format:
                    formatted_start_date = start_date.strftime(format_string)
                    formatted_end_date = end_date.strftime(format_string)

            # Prepare context for the template
            data.update(
                {
                    "month_start_name": start_date.strftime("%B %d, %Y"),
                    "month_end_name": end_date.strftime("%B %d, %Y"),
                    "formatted_start_date": formatted_start_date,
                    "formatted_end_date": formatted_end_date,
                    "employee": payslip.employee_id,
                    "payslip": payslip,
                    "json_data": data.copy(),
                    "currency": PayrollSettings.objects.first().currency_symbol,
                    "all_deductions": [],
                    "all_allowances": data["allowances"].copy(),
                    "host": request.get_host(),
                    "protocol": "https" if request.is_secure() else "http",
                    "company": company,
                }
            )

            # Merge deductions and allowances for display
            for deduction_list in [
                data["basic_pay_deductions"],
                data["gross_pay_deductions"],
                data["pretax_deductions"],
                data["post_tax_deductions"],
                data["tax_deductions"],
                data["net_deductions"],
            ]:
                data["all_deductions"].extend(deduction_list)

            equalize_lists_length(data["allowances"], data["all_deductions"])
            data["zipped_data"] = zip(data["allowances"], data["all_deductions"])
            data["request"] = request
            template_path = "payroll/payslip/payslip_pdf.html"

            return generate_payslip_pdf(template_path, context=data, html=False)
        return redirect(filter_payslip)
    return render(request, "405.html")


@login_required
@hx_request_required
@permission_required("payroll.view_contract")
def contract_select(request):
    page_number = request.GET.get("page")
    contracts = Contract.objects.none()

    if page_number == "all":
        contracts = Contract.objects.all()

    contract_ids = [str(contract.id) for contract in contracts]
    total_count = contracts.count()

    context = {"contract_ids": contract_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
@hx_request_required
def contract_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        contract_filter = ContractFilter(filters, queryset=Contract.objects.all())

        # Get the filtered queryset
        filtered_contracts = contract_filter.qs

        contract_ids = [str(contract.id) for contract in filtered_contracts]
        total_count = filtered_contracts.count()

        context = {"contract_ids": contract_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
@hx_request_required
def payslip_select(request):
    page_number = request.GET.get("page")
    payslip = Payslip.objects.none()

    if page_number == "all":
        if request.user.has_perm("payroll.view_payslip"):
            payslip = Payslip.objects.all()
        else:
            payslip = Payslip.objects.filter(employee_id__employee_user_id=request.user)

    payslip_ids = [str(emp.id) for emp in payslip]
    total_count = payslip.count()

    context = {"payslip_ids": payslip_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
@hx_request_required
def payslip_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        payslip_filter = PayslipFilter(filters, queryset=Payslip.objects.all())

        # Get the filtered queryset
        filtered_employees = payslip_filter.qs

        payslip_ids = [str(emp.id) for emp in filtered_employees]
        total_count = filtered_employees.count()

        context = {"payslip_ids": payslip_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
@hx_request_required
def create_payrollrequest_comment(request, payroll_id):
    """
    This method renders form and template to create Reimbursement request comments
    """
    from payroll.forms.forms import ReimbursementRequestCommentForm

    payroll = Reimbursement.objects.filter(id=payroll_id).first()
    emp = request.user.employee_get
    form = ReimbursementRequestCommentForm(
        initial={"employee_id": emp.id, "request_id": payroll_id}
    )

    if request.method == "POST":
        form = ReimbursementRequestCommentForm(request.POST)
        if form.is_valid():
            form.instance.employee_id = emp
            form.instance.request_id = payroll
            form.save()
            comments = ReimbursementrequestComment.objects.filter(
                request_id=payroll_id
            ).order_by("-created_at")
            no_comments = False
            if not comments.exists():
                no_comments = True
            form = ReimbursementRequestCommentForm(
                initial={"employee_id": emp.id, "request_id": payroll_id}
            )
            messages.success(request, _("Comment added successfully!"))

            if payroll.employee_id.employee_work_info.reporting_manager_id is not None:

                if request.user.employee_get.id == payroll.employee_id.id:
                    rec = (
                        payroll.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                    )
                    notify.send(
                        request.user.employee_get,
                        recipient=rec,
                        verb=f"{payroll.employee_id}'s reimbursement request has received a comment.",
                        verb_ar=f"تلقى طلب استرداد نفقات {payroll.employee_id} تعليقًا.",
                        verb_de=f"{payroll.employee_id}s Rückerstattungsantrag hat einen Kommentar erhalten.",
                        verb_es=f"La solicitud de reembolso de gastos de {payroll.employee_id} ha recibido un comentario.",
                        verb_fr=f"La demande de remboursement de frais de {payroll.employee_id} a reçu un commentaire.",
                        redirect=reverse("view-reimbursement"),
                        icon="chatbox-ellipses",
                    )
                elif (
                    request.user.employee_get.id
                    == payroll.employee_id.employee_work_info.reporting_manager_id.id
                ):
                    rec = payroll.employee_id.employee_user_id
                    notify.send(
                        request.user.employee_get,
                        recipient=rec,
                        verb="Your reimbursement request has received a comment.",
                        verb_ar="تلقى طلب استرداد نفقاتك تعليقًا.",
                        verb_de="Ihr Rückerstattungsantrag hat einen Kommentar erhalten.",
                        verb_es="Tu solicitud de reembolso ha recibido un comentario.",
                        verb_fr="Votre demande de remboursement a reçu un commentaire.",
                        redirect=reverse("view-reimbursement"),
                        icon="chatbox-ellipses",
                    )
                else:
                    rec = [
                        payroll.employee_id.employee_user_id,
                        payroll.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                    ]
                    notify.send(
                        request.user.employee_get,
                        recipient=rec,
                        verb=f"{payroll.employee_id}'s reimbursement request has received a comment.",
                        verb_ar=f"تلقى طلب استرداد نفقات {payroll.employee_id} تعليقًا.",
                        verb_de=f"{payroll.employee_id}s Rückerstattungsantrag hat einen Kommentar erhalten.",
                        verb_es=f"La solicitud de reembolso de gastos de {payroll.employee_id} ha recibido un comentario.",
                        verb_fr=f"La demande de remboursement de frais de {payroll.employee_id} a reçu un commentaire.",
                        redirect=reverse("view-reimbursement"),
                        icon="chatbox-ellipses",
                    )
            else:
                rec = payroll.employee_id.employee_user_id
                notify.send(
                    request.user.employee_get,
                    recipient=rec,
                    verb="Your reimbursement request has received a comment.",
                    verb_ar="تلقى طلب استرداد نفقاتك تعليقًا.",
                    verb_de="Ihr Rückerstattungsantrag hat einen Kommentar erhalten.",
                    verb_es="Tu solicitud de reembolso ha recibido un comentario.",
                    verb_fr="Votre demande de remboursement a reçu un commentaire.",
                    redirect=reverse("view-reimbursement"),
                    icon="chatbox-ellipses",
                )

            return render(
                request,
                "payroll/reimbursement/reimbursement_comment.html",
                {
                    "comments": comments,
                    "no_comments": no_comments,
                    "request_id": payroll_id,
                },
            )
    return render(
        request,
        "payroll/reimbursement/reimbursement_comment.html",
        {"form": form, "request_id": payroll_id},
    )


@login_required
@hx_request_required
def view_payrollrequest_comment(request, payroll_id):
    """
    This method is used to show Reimbursement request comments
    """
    comments = ReimbursementrequestComment.objects.filter(
        request_id=payroll_id
    ).order_by("-created_at")

    req = Reimbursement.objects.get(id=payroll_id)
    no_comments = False
    if not comments.exists():
        no_comments = True

    if request.FILES:
        files = request.FILES.getlist("files")
        comment_id = request.GET["comment_id"]
        comment = ReimbursementrequestComment.objects.get(id=comment_id)
        attachments = []
        for file in files:
            file_instance = ReimbursementFile()
            file_instance.file = file
            file_instance.save()
            attachments.append(file_instance)
        comment.files.add(*attachments)
    return render(
        request,
        "payroll/reimbursement/reimbursement_comment.html",
        {
            "comments": comments,
            "no_comments": no_comments,
            "request_id": payroll_id,
            "req": req,
        },
    )


@login_required
def delete_payrollrequest_comment(request, comment_id):
    """
    This method is used to delete Reimbursement request comments
    """

    comment = ReimbursementrequestComment.objects.filter(id=comment_id)
    if not comment.exists():
        messages.error(request, _("Comment not found."))
        return HorillaRedirect(request)
    comment_obj = comment.first()

    # Mirrors reimbursement_comment.html's delete-control condition, but
    # scoped to the comment's specific parent Reimbursement instead of the
    # template's coarse is_reportingmanager check (which only asks "does
    # this user manage *someone*", not whether they manage the request's
    # actual employee). filter_own_and_subordinate_recordes() checks: own
    # record, subordinate-of-an-authorized-manager, or the global perm.
    is_author = comment_obj.employee_id == request.user.employee_get
    if not is_author:
        authorized_requests = filter_own_and_subordinate_recordes(
            request,
            Reimbursement.objects.filter(pk=comment_obj.request_id_id),
            "payroll.delete_reimbursementrequestcomment",
        )
        if not authorized_requests.exists():
            messages.error(
                request, _("You don't have permission to delete this comment.")
            )
            return HorillaRedirect(request)

    comment.delete()
    return HorillaRedirect(request, message=_("Comment deleted successfully!"))


@login_required
def delete_reimbursement_comment_file(request):
    """
    Used to delete attachment
    """
    ids = request.GET.getlist("ids")
    if not ids:
        return HorillaRedirect(request, message=_("No file IDs provided for deletion."))
    records = ReimbursementFile.objects.filter(id__in=ids)
    if not request.user.has_perm("payroll.delete_reimbursementfile"):
        records = records.filter(employee_id__employee_user_id=request.user)
    records.delete()
    return HorillaRedirect(request, message=_("File deleted successfully"))


@login_required
@permission_required("payroll.add_payrollgeneralsetting")
def initial_notice_period(request):
    """
    This method is used to set initial value notice period
    """
    if not request.GET.get("notice_period"):
        return HorillaRedirect(request, message=_("required parameter is missing"))

    notice_period = eval_validate(request.GET["notice_period"])
    selected_company = request.session.get("selected_company")
    if selected_company and selected_company != "all":
        settings = PayrollGeneralSetting.objects.filter(
            company_id=selected_company
        ).first()
        settings = settings or PayrollGeneralSetting(company_id_id=selected_company)
    else:
        settings = PayrollGeneralSetting.objects.first()
        settings = settings or PayrollGeneralSetting()
    settings.notice_period = max(notice_period, 0)
    settings.save()
    messages.success(
        request, _("The initial notice period has been successfully updated.")
    )
    if request.META.get("HTTP_HX_REQUEST"):
        return HttpResponse()
    return HorillaRedirect(request)


# ===========================Auto payslip generate================================


@login_required
@permission_required("payroll.view_payslipautogenerate")
def auto_payslip_settings_view(request):
    payslip_auto_generate = PayslipAutoGenerate.objects.all()

    context = {"payslip_auto_generate": payslip_auto_generate}
    return render(request, "payroll/settings/auto_payslip_settings.html", context)


@login_required
@hx_request_required
@permission_required("payroll.change_payslipautogenerate")
def create_or_update_auto_payslip(request, auto_id=None):
    auto_payslip = None
    if auto_id:
        auto_payslip = PayslipAutoGenerate.objects.get(id=auto_id)
    form = PayslipAutoGenerateForm(instance=auto_payslip)
    if request.method == "POST":
        form = PayslipAutoGenerateForm(request.POST, instance=auto_payslip)
        if form.is_valid():
            auto_payslip = form.save()
            company = (
                auto_payslip.company_id if auto_payslip.company_id else "All company"
            )
            action = _("updated") if auto_id else _("created")
            messages.success(
                request,
                _(f"Payslip Auto generate for {company} {action} successfully "),
            )
            return HorillaRedirect(request)
    return render(
        request, "payroll/settings/auto_payslip_create_or_update.html", {"form": form}
    )


@login_required
@hx_request_required
@permission_required("payroll.change_payslipautogenerate")
def activate_auto_payslip_generate(request):
    """
    ajax function to update is active field in PayslipAutoGenerate.
    Args:
    - isChecked: Boolean value representing the state of PayslipAutoGenerate,
    - autoId: Id of PayslipAutoGenerate object
    """
    isChecked = request.POST.get("isChecked")
    autoId = request.POST.get("autoId")
    if not autoId or not isChecked:
        return JsonResponse(
            {
                "type": "error",
                "message": _("Invalid request. Missing required parameters."),
            }
        )
    payslip_auto = PayslipAutoGenerate.objects.filter(id=autoId).first()
    if not payslip_auto:
        return JsonResponse(
            {
                "type": "error",
                "message": _("Payslip auto generate setting not found."),
            }
        )

    if isChecked == "true":
        payslip_auto.auto_generate = True
        response = {
            "type": "success",
            "message": _("Auto paslip generate activated successfully."),
        }
    else:
        payslip_auto.auto_generate = False
        response = {
            "type": "success",
            "message": _("Auto paslip generate deactivated successfully."),
        }
    payslip_auto.save()
    return JsonResponse(response)


@login_required
@hx_request_required
@permission_required("payroll.delete_payslipautogenerate")
def delete_auto_payslip(request, auto_id):
    """
    Delete a PayslipAutoGenerate object.

    Args:
        auto_id: The ID of PayslipAutoGenerate object to delete.

    Returns:
        Redirects to the contract view after successfully deleting the contract.

    """
    try:
        count = PayslipAutoGenerate.objects.count()
        auto_payslip = PayslipAutoGenerate.objects.get(id=auto_id)
        if not auto_payslip.auto_generate:
            delete_error = False
            company = (
                auto_payslip.company_id if auto_payslip.company_id else "All company"
            )
            auto_payslip.delete()
            messages.success(
                request, _(f"Payslip auto generate for {company} deleted successfully.")
            )
        else:
            delete_error = True
            messages.info(request, _(f"Active 'Payslip auto generate' cannot delete."))
    except PayslipAutoGenerate.DoesNotExist:
        delete_error = True
        messages.error(request, _("Payslip auto generate not found."))
    if delete_error or count == 1:
        return HttpResponse("<script>$('.reload-record').click();</script>")
    return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")


@login_required
def payroll_tab(request, pk, **kwargs):
    """
    method for rendering payroll tab
    """

    employee = Employee.objects.get(id=pk)
    return render(
        request,
        "tabs/payroll-tab.html",
        {
            "employee": employee,
        },
    )
