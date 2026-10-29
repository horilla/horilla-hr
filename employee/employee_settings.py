"""
employee/employee_settings.py

Employee Configuration landing page with tabbed shift, schedule, work type, and tag sections.
"""

from django.shortcuts import render

from horilla.decorators import hx_request_required, login_required


@login_required
def employee_settings_view(request):
    """
    Employee Configuration landing page with tabbed master-data sections.
    """
    return render(request, "employee_settings/employee_settings.html")


@login_required
@hx_request_required
def employee_settings_shift_tab(request):
    """HTMX tab body for employee shifts under configuration."""
    return render(request, "employee_settings/employee_settings_shift_tab.html")


@login_required
@hx_request_required
def employee_settings_shift_schedule_tab(request):
    """HTMX tab body for shift schedules under configuration."""
    return render(
        request, "employee_settings/employee_settings_shift_schedule_tab.html"
    )


@login_required
@hx_request_required
def employee_settings_rotating_shift_tab(request):
    """HTMX tab body for rotating shifts under configuration."""
    return render(
        request, "employee_settings/employee_settings_rotating_shift_tab.html"
    )


@login_required
@hx_request_required
def employee_settings_work_type_tab(request):
    """HTMX tab body for work types under configuration."""
    return render(request, "employee_settings/employee_settings_work_type_tab.html")


@login_required
@hx_request_required
def employee_settings_rotating_work_type_tab(request):
    """HTMX tab body for rotating work types under configuration."""
    return render(
        request, "employee_settings/employee_settings_rotating_work_type_tab.html"
    )


@login_required
@hx_request_required
def employee_settings_employee_type_tab(request):
    """HTMX tab body for employee types under configuration."""
    return render(request, "employee_settings/employee_settings_employee_type_tab.html")


@login_required
@hx_request_required
def employee_settings_employee_tags_tab(request):
    """HTMX tab body for employee tags under configuration."""
    return render(request, "employee_settings/employee_settings_employee_tags_tab.html")
