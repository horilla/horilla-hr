"""
employee/work_schedules.py

Work Schedules landing page with tabbed rotating shift, work type, and roster sections.
"""

from django.shortcuts import render

from horilla.decorators import hx_request_required, login_required


@login_required
def work_schedules_view(request):
    """
    Work Schedules landing page with tabbed schedule management sections.
    """
    return render(request, "work_schedules/work_schedules.html")


@login_required
@hx_request_required
def work_schedules_rotating_shift_tab(request):
    """
    HTMX tab body for rotating shift assign under work schedules.
    """
    return render(request, "work_schedules/work_schedules_rotating_shift_tab.html")


@login_required
@hx_request_required
def work_schedules_rotating_work_type_tab(request):
    """
    HTMX tab body for rotating work type assign under work schedules.
    """
    return render(request, "work_schedules/work_schedules_rotating_work_type_tab.html")


@login_required
@hx_request_required
def work_schedules_shift_roster_tab(request):
    """
    HTMX tab body for shift roster under work schedules.
    """
    return render(request, "work_schedules/work_schedules_shift_roster_tab.html")
