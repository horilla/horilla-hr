"""
employee/context_processors.py

This module is used to write context processor methods
"""

import json
from datetime import date

from django import template
from django.apps import apps
from django.contrib import messages
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from base.backends import ConfiguredEmailBackend
from base.forms import MailTemplateForm
from base.methods import (
    build_safe_template_request,
    export_data,
    generate_pdf,
    sanitize_mail_template_body,
    sanitize_mail_template_placeholders,
)
from base.models import HorillaMailTemplate
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla import settings
from horilla.decorators import hx_request_required, login_required, manager_can_enter
from horilla.http.response import HorillaRedirect


def paginator_qry(qryset, page_number):
    """
    This method is used to paginate query set
    """
    paginator = Paginator(qryset, 20)
    qryset = paginator.get_page(page_number)
    return qryset


@login_required
@manager_can_enter("employee.view_employee")
def not_in_yet(request):
    """
    This context processor wil return the employees, if they not marked the attendance
    for the day
    """
    page_number = request.GET.get("page")
    previous_data = request.GET.urlencode()
    emps = (
        EmployeeFilter({"not_in_yet": date.today()})
        .qs.exclude(employee_work_info__isnull=True)
        .filter(is_active=True)
    )

    return render(
        request,
        "dashboard/not_in_yet.html",
        {
            "employees": paginator_qry(emps, page_number),
            "pd": previous_data,
        },
    )


@login_required
@manager_can_enter("employee.view_employee")
def not_out_yet(request):
    """
    This context processor wil return the employees, if they not marked the attendance
    for the day
    """
    emps = (
        EmployeeFilter({"not_out_yet": date.today()})
        .qs.exclude(employee_work_info__isnull=True)
        .filter(is_active=True)
    )
    return render(request, "dashboard/not_out_yet.html", {"employees": emps})


@login_required
@hx_request_required
@manager_can_enter("employee.change_employee")
def send_mail(request, emp_id=None):
    """
    This method used send mail to the employees
    """
    employee = None
    if emp_id:
        try:
            employee = Employee.objects.get(id=emp_id)
        except Employee.DoesNotExist:
            return HorillaRedirect(
                request, message=_("No Employee found matching the query.")
            )
    employees = Employee.objects.all()
    templates = HorillaMailTemplate.objects.all()
    return render(
        request,
        "employee/send_mail.html",
        {
            "employee": employee,
            "templates": templates,
            "employees": employees,
            "searchWords": MailTemplateForm().get_employee_template_language(),
        },
    )


@login_required
@manager_can_enter("employee.change_employee")
def employee_data_export(request, emp_id=None):
    """
    This method used send mail to the employees
    """

    resolver_match = request.resolver_match
    if (
        resolver_match
        and resolver_match.url_name
        and resolver_match.url_name == "export-data-employee"
    ):
        employee = None
        if emp_id:
            try:
                employee = Employee.objects.get(id=emp_id)
            except Employee.DoesNotExist:
                return HorillaRedirect(
                    request, message=_("No Employee found matching the query.")
                )

        context = {"employee": employee}

        # IF LEAVE IS INSTALLED
        if apps.is_installed("leave"):
            from leave.filters import LeaveRequestFilter
            from leave.forms import LeaveRequestExportForm

            excel_column = LeaveRequestExportForm()
            export_filter = LeaveRequestFilter()
            context.update(
                {
                    "leave_excel_column": excel_column,
                    "leave_export_filter": export_filter.form,
                }
            )

        # IF ATTENDANCE IS INSTALLED
        if apps.is_installed("attendance"):
            from attendance.filters import AttendanceFilters
            from attendance.forms import AttendanceExportForm
            from attendance.models import Attendance

            excel_column = AttendanceExportForm()
            export_filter = AttendanceFilters()
            context.update(
                {
                    "attendance_excel_column": excel_column,
                    "attendance_export_filter": export_filter.form,
                }
            )

        # IF PAYROLL IS INSTALLED
        if apps.is_installed("payroll"):
            from payroll.filters import PayslipFilter
            from payroll.forms.component_forms import PayslipExportColumnForm

            context.update(
                {
                    "payroll_export_column": PayslipExportColumnForm(),
                    "payroll_export_filter": PayslipFilter(request.GET),
                }
            )

        return render(request, "employee/export_data_employee.html", context=context)
    return export_data(
        request=request,
        model=Attendance,
        filter_class=AttendanceFilters,
        form_class=AttendanceExportForm,
        file_name="Attendance_export",
    )


@login_required
def get_template(request, emp_id):
    """
    This method is used to return the mail template
    """
    body = (
        HorillaMailTemplate.find(emp_id).body
        if HorillaMailTemplate.find(emp_id)
        else ""
    )
    return JsonResponse({"body": body})


@login_required
def get_mail_preview(request):
    """
    Returns the mail template preview as HTML.
    """
    body = request.POST.get("body")
    if not body:
        return HttpResponse("No body provided", status=400)

    # Strip dangerous template constructs first.
    body = sanitize_mail_template_body(body)
    allowed_template_words = set(
        MailTemplateForm().get_employee_template_language().values()
    )
    body = sanitize_mail_template_placeholders(body, allowed_template_words)

    emp_id = request.GET.get("emp_id")
    employee_ids = request.POST.getlist("employees")

    # Fetch one employee for preview if provided
    employee_obj = None
    if emp_id or employee_ids:
        ids = [emp_id] if emp_id else employee_ids
        employee_obj = Employee.objects.filter(id__in=ids).first()
        if not employee_obj:
            return HttpResponse("Employee not found", status=404)

    # Keep `request` in context, but only as a sanitized proxy.
    context = {
        "instance": employee_obj,
        "model_instance": employee_obj,
        "self": getattr(request.user, "employee_get", None),
        "request": build_safe_template_request(request),
    }

    # Render template
    rendered_body = template.Template(body).render(template.Context(context)) or " "

    # Add preview note if multiple employees
    if employee_ids and len(employee_ids) > 1 and employee_obj:
        rendered_body = (
            f"<p style='color:gray; font-size:13px;'>"
            f"Preview shown for {employee_obj.get_full_name()}. "
            f"Mail will be personalized for {len(employee_ids)} employees."
            f"</p>{rendered_body}"
        )

    # Wrap in styled div
    textarea_field = (
        f'<div class="oh-input oh-input--textarea" '
        f'style="border: solid .1px #dbd7d7; padding:5px;">{rendered_body}</div>'
    )

    return HttpResponse(textarea_field, content_type="text/html")


@login_required
@manager_can_enter(perm="employee.change_employee")
def send_mail_to_employee(request):
    """
    This method is used to send acknowledgement mail to the employee
    """
    employee_id = request.POST.get("id")
    subject = request.POST.get("subject")
    bdy = request.POST.get("body")

    employee_ids = request.POST.getlist("employees")
    employees = Employee.objects.filter(id__in=employee_ids)

    other_attachments = request.FILES.getlist("other_attachments")

    if employee_id:
        employee_obj = Employee.objects.filter(id=employee_id)
    else:
        employee_obj = Employee.objects.none()
    employees = (employees | employee_obj).distinct()

    template_attachment_ids = request.POST.getlist("template_attachments")
    for employee in employees:
        bodys = list(
            HorillaMailTemplate.objects.filter(
                id__in=template_attachment_ids
            ).values_list("body", flat=True)
        )
        attachments = [
            (file.name, file.read(), file.content_type) for file in other_attachments
        ]
        for html in bodys:
            # due to not having solid template we first need to pass the context
            template_bdy = template.Template(sanitize_mail_template_body(html))
            context = template.Context(
                {"instance": employee, "self": request.user.employee_get}
            )
            render_bdy = template_bdy.render(context)
            attachments.append(
                (
                    "Document",
                    generate_pdf(render_bdy, {}, path=False, title="Document").content,
                    "application/pdf",
                )
            )

        template_bdy = template.Template(sanitize_mail_template_body(bdy))
        context = template.Context(
            {"instance": employee, "self": request.user.employee_get}
        )
        render_bdy = template_bdy.render(context)
        send_to_mail = (
            employee.employee_work_info.email
            if employee.employee_work_info and employee.employee_work_info.email
            else employee.email
        )

        email = EmailMessage(
            subject=subject,
            body=render_bdy,
            to=[send_to_mail],
        )
        email.content_subtype = "html"

        email.attachments = attachments
        try:
            email.send()
            if employee.employee_work_info.email or employee.email:
                messages.success(
                    request,
                    _("Mail sent to %(employee)s")
                    % {"employee": employee.get_full_name()},
                )
            else:
                messages.info(
                    request,
                    _("Email not set for %(employee)s")
                    % {"employee": employee.get_full_name()},
                )
        except Exception as e:
            messages.error(request, _("Something went wrong"))
    return HorillaRedirect(request)
