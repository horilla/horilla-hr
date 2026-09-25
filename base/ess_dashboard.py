"""
Employee Self-Service (ESS) dashboard views.

Accessible at /ess/ — shows personal data only for the logged-in employee.
All data is scoped to request.user.employee_get; no cross-employee access.
"""

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from base.templatetags.horillafilters import is_check_in_enabled

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_employee(request):
    """Return the Employee for the current user, or None."""
    return getattr(request.user, "employee_get", None)


def _parse_period(request):
    """Parse from_date and to_date from GET params. Defaults to current month."""
    today = date.today()
    from_str = request.GET.get("from_date")
    to_str = request.GET.get("to_date")
    try:
        from_date = date.fromisoformat(from_str) if from_str else today.replace(day=1)
    except (ValueError, TypeError):
        from_date = today.replace(day=1)
    try:
        to_date = date.fromisoformat(to_str) if to_str else today
    except (ValueError, TypeError):
        to_date = today
    if to_date < from_date:
        to_date = from_date
    return from_date, to_date


# ─── Entry point ──────────────────────────────────────────────────────────────


@login_required
def ess_dashboard(request):
    """Render the ESS dashboard shell page."""
    employee = _get_employee(request)
    if not employee:
        from django.contrib import messages

        from horilla.http.response import HorillaRedirect

        messages.error(request, _("Your account is not linked to an employee record."))
        return HorillaRedirect(request)

    return render(
        request,
        "base/ess_dashboard.html",
        {
            "employee": employee,
            "today": date.today(),
        },
    )


# ─── KPI summary ──────────────────────────────────────────────────────────────


@login_required
def ess_kpi_data(request):
    """GET /ess/api/kpi/?year=&month= — four personal KPI cards.

    Attendance counts honor the picker month; balances/objectives/payslip
    are current-state and ignore the picker.
    """
    from leave.models import AvailableLeave, LeaveRequest

    employee = _get_employee(request)
    if not employee:
        return JsonResponse({"error": "no employee"}, status=403)

    from_date, to_date = _parse_period(request)
    # Don't count attendance in future days of the selected month
    range_end = min(to_date, date.today())

    # Leave balances (available for balance chart — not a hero KPI)
    total_available = 0.0
    try:
        balances = AvailableLeave.objects.filter(employee_id=employee)
        total_available = sum(
            float(b.available_days) + float(b.carryforward_days) for b in balances
        )
    except Exception:
        pass

    pending_leave_requests = 0
    upcoming_leave_count = 0
    try:
        pending_leave_requests = LeaveRequest.objects.filter(
            employee_id=employee, status="requested"
        ).count()
        upcoming_leave_count = LeaveRequest.objects.filter(
            employee_id=employee,
            status="approved",
            start_date__gte=date.today(),
        ).count()
    except Exception:
        pass

    # Attendance in the selected month
    present_count = 0
    late_count = 0
    try:
        from attendance.models import Attendance, AttendanceLateComeEarlyOut

        if range_end >= from_date:
            present_count = Attendance.objects.filter(
                employee_id=employee,
                attendance_date__gte=from_date,
                attendance_date__lte=range_end,
            ).count()
            late_count = (
                AttendanceLateComeEarlyOut.objects.filter(
                    employee_id=employee,
                    type="late_come",
                    attendance_id__attendance_date__gte=from_date,
                    attendance_id__attendance_date__lte=range_end,
                )
                .values("attendance_id")
                .distinct()
                .count()
            )
    except Exception:
        pass

    # Open objectives
    open_objectives = 0
    try:
        from pms.models import EmployeeObjective

        open_objectives = EmployeeObjective.objects.filter(
            employee_id=employee,
            archive=False,
            status__in=["Not Started", "On Track", "Behind", "At Risk"],
        ).count()
    except Exception:
        pass

    # Latest payslip
    latest_net_pay = None
    latest_payslip_period = ""
    try:
        from payroll.models.models import Payslip

        ps = (
            Payslip.objects.filter(
                employee_id=employee,
                status__in=["confirmed", "paid"],
            )
            .order_by("-end_date")
            .first()
        )
        if ps:
            latest_net_pay = round(float(ps.net_pay or 0), 2)
            latest_payslip_period = ps.start_date.strftime("%b %Y")
    except Exception:
        pass

    return JsonResponse(
        {
            "total_available_leave": round(total_available, 1),
            "pending_leave_requests": pending_leave_requests,
            "upcoming_leave_count": upcoming_leave_count,
            "present_this_month": present_count,
            "late_this_month": late_count,
            "open_objectives": open_objectives,
            "latest_net_pay": latest_net_pay,
            "latest_payslip_period": latest_payslip_period,
        }
    )


# ─── Leave balance chart ───────────────────────────────────────────────────────


@login_required
def ess_leave_balance(request):
    """GET /ess/api/leave-balance/?year=&month= — leave balance with days taken in the selected month."""
    from leave.models import AvailableLeave, LeaveRequest

    employee = _get_employee(request)
    if not employee:
        return JsonResponse({"error": "no employee"}, status=403)

    from_date, to_date = _parse_period(request)
    balances = []
    try:
        qs = (
            AvailableLeave.objects.filter(employee_id=employee)
            .select_related("leave_type_id")
            .order_by("leave_type_id__name")
        )
        for al in qs:
            taken = 0.0
            try:
                approved = LeaveRequest.objects.filter(
                    employee_id=employee,
                    leave_type_id=al.leave_type_id,
                    status="approved",
                    start_date__lte=to_date,
                    end_date__gte=from_date,
                )
                taken = float(sum(float(lr.requested_days or 0) for lr in approved))
            except Exception:
                pass
            balances.append(
                {
                    "id": al.leave_type_id.id,
                    "type": al.leave_type_id.name,
                    "available": round(float(al.available_days), 1),
                    "carryforward": round(float(al.carryforward_days), 1),
                    "total": round(float(al.total_leave_days), 1),
                    "taken_in_month": round(taken, 1),
                }
            )
    except Exception:
        pass

    return JsonResponse({"balances": balances})


# ─── Leave requests list ───────────────────────────────────────────────────────


@login_required
def ess_leave_requests(request):
    """GET /ess/api/leave-requests/?year=&month= — leave requests overlapping the picker month."""
    from leave.models import LeaveRequest

    employee = _get_employee(request)
    if not employee:
        return JsonResponse({"error": "no employee"}, status=403)

    from_date, to_date = _parse_period(request)
    status_filter = request.GET.get("status")
    results = []
    try:
        qs = (
            LeaveRequest.objects.filter(
                employee_id=employee,
                start_date__lte=to_date,
                end_date__gte=from_date,
            )
            .select_related("leave_type_id")
            .order_by("-start_date")
        )
        if status_filter:
            qs = qs.filter(status=status_filter)
        qs = qs[:10]

        status_labels = {
            "requested": _("Pending"),
            "approved": _("Approved"),
            "rejected": _("Rejected"),
            "cancelled": _("Cancelled"),
        }
        for lr in qs:
            results.append(
                {
                    "id": lr.pk,
                    "leave_type": str(lr.leave_type_id),
                    "start": lr.start_date.strftime("%b %d"),
                    "end": lr.end_date.strftime("%b %d"),
                    "days": float(lr.requested_days or 1),
                    "status": lr.status,
                    "status_label": status_labels.get(lr.status, lr.status),
                }
            )
    except Exception:
        pass

    return JsonResponse({"requests": results})


# ─── Attendance calendar ───────────────────────────────────────────────────────


@login_required
def ess_attendance_calendar(request):
    """GET /ess/api/attendance-calendar/?year=&month= — day-by-day attendance status."""

    employee = _get_employee(request)
    if not employee:
        return JsonResponse({"error": "no employee"}, status=403)

    from_date, to_date = _parse_period(request)
    check_in_enabled = is_check_in_enabled(request)

    attendance_map = {}
    late_dates = set()
    on_leave_dates = set()
    holiday_dates = set()

    try:
        from attendance.models import Attendance, AttendanceLateComeEarlyOut

        for att in Attendance.objects.filter(
            employee_id=employee,
            attendance_date__gte=from_date,
            attendance_date__lte=to_date,
        ).values("attendance_date", "at_work_second", "attendance_worked_hour"):
            d = att["attendance_date"]
            seconds = att["at_work_second"] or 0
            attendance_map[d.isoformat()] = round(seconds / 3600, 2)

        late_dates = set(
            AttendanceLateComeEarlyOut.objects.filter(
                employee_id=employee,
                type="late_come",
                attendance_id__attendance_date__gte=from_date,
                attendance_id__attendance_date__lte=to_date,
            ).values_list("attendance_id__attendance_date", flat=True)
        )
        late_dates = {d.isoformat() for d in late_dates}
    except Exception:
        pass

    try:
        from leave.models import LeaveRequest

        for lr in LeaveRequest.objects.filter(
            employee_id=employee,
            status="approved",
            start_date__lte=to_date,
            end_date__gte=from_date,
        ):
            cur = lr.start_date
            while cur <= lr.end_date:
                if from_date <= cur <= to_date:
                    on_leave_dates.add(cur.isoformat())
                cur += timedelta(days=1)
    except Exception:
        pass

    try:
        from base.models import Holidays

        for h in Holidays.objects.filter(
            Q(is_specific=False) | Q(employees=employee),
            start_date__lte=to_date,
            start_date__gte=from_date,
        ):
            cur = h.start_date
            end = h.end_date or h.start_date
            while cur <= end and cur <= to_date:
                if cur >= from_date:
                    holiday_dates.add(cur.isoformat())
                cur += timedelta(days=1)
    except Exception:
        pass

    days = []
    cur = from_date
    summary = {"present": 0, "absent": 0, "leave": 0, "late": 0, "holiday": 0}

    while cur <= to_date:
        iso = cur.isoformat()
        day_of_week = cur.weekday()  # 0=Mon, 6=Sun
        is_weekend = day_of_week >= 5

        if is_weekend:
            status = "weekend"
        elif iso in holiday_dates:
            status = "holiday"
            summary["holiday"] += 1
        elif iso in on_leave_dates:
            status = "leave"
            summary["leave"] += 1
        elif iso in attendance_map:
            status = "late" if iso in late_dates else "present"
            if status == "late":
                summary["late"] += 1
            summary["present"] += 1
        elif cur <= date.today() and check_in_enabled:
            status = "absent"
            summary["absent"] += 1
        elif cur <= date.today():
            # No check-in/check-out means no evidence either way, so the day is
            # left blank rather than accused of being an absence.
            status = "workday"
        else:
            status = "future"

        days.append(
            {
                "date": iso,
                "day": cur.day,
                "status": status,
                "hours": attendance_map.get(iso, 0),
            }
        )
        cur += timedelta(days=1)

    return JsonResponse(
        {
            "year": from_date.year,
            "month": from_date.month,
            "month_name": from_date.strftime("%B %Y"),
            "start_weekday": from_date.weekday(),  # 0=Mon .. 6=Sun
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "days": days,
            "summary": summary,
        }
    )


# ─── Work hours this month ──────────────────────────────────────────────────────


@login_required
def ess_work_hours_month(request):
    """GET /ess/api/work-hours-month/?from_date=&to_date= — daily hours across the selected month."""
    employee = _get_employee(request)
    if not employee:
        return JsonResponse({"error": "no employee"}, status=403)

    from_date, to_date = _parse_period(request)

    hours_map = {}
    try:
        from attendance.models import Attendance

        for att in Attendance.objects.filter(
            employee_id=employee,
            attendance_date__gte=from_date,
            attendance_date__lte=to_date,
        ).values("attendance_date", "at_work_second"):
            seconds = att["at_work_second"] or 0
            hours_map[att["attendance_date"].isoformat()] = round(seconds / 3600, 2)
    except Exception:
        pass

    days = []
    total_hours = 0.0
    cur = from_date
    while cur <= to_date:
        h = hours_map.get(cur.isoformat(), 0.0)
        total_hours += h
        days.append(
            {
                "day": cur.day,
                "date": cur.strftime("%b %d"),
                "iso_date": cur.isoformat(),
                "hours": h,
            }
        )
        cur += timedelta(days=1)

    return JsonResponse(
        {
            "days": days,
            "total_hours": round(total_hours, 2),
            "month_label": from_date.strftime("%B %Y"),
        }
    )


# ─── Payslips ─────────────────────────────────────────────────────────────────


@login_required
def ess_payslips(request):
    """GET /ess/api/payslips/?year=&month= — last 6 confirmed/paid payslips ending on or before the selected month."""
    employee = _get_employee(request)
    if not employee:
        return JsonResponse({"error": "no employee"}, status=403)

    _, to_date = _parse_period(request)
    results = []
    latest_net = None
    try:
        from payroll.models.models import Payslip

        qs = Payslip.objects.filter(
            employee_id=employee,
            status__in=["confirmed", "paid"],
            end_date__lte=to_date,
        ).order_by("-end_date")[:6]
        for ps in qs:
            net = round(float(ps.net_pay or 0), 2)
            results.append(
                {
                    "id": ps.pk,
                    "period": ps.start_date.strftime("%b %Y"),
                    "net_pay": net,
                    "gross_pay": round(float(ps.gross_pay or 0), 2),
                    "deduction": round(float(ps.deduction or 0), 2),
                    "status": ps.status,
                }
            )
        if results:
            latest_net = results[0]["net_pay"]
    except Exception:
        pass

    return JsonResponse({"payslips": results, "latest_net": latest_net})


# ─── Objectives ───────────────────────────────────────────────────────────────


@login_required
def ess_objectives(request):
    """GET /ess/api/objectives/?year=&month= — PMS objectives overlapping the selected month."""

    employee = _get_employee(request)
    if not employee:
        return JsonResponse({"error": "no employee"}, status=403)

    from_date, to_date = _parse_period(request)
    results = []
    try:
        from pms.models import EmployeeObjective

        # Employee-specific progress records overlapping the selected month
        month_overlap = Q(start_date__lte=to_date) & (
            Q(end_date__gte=from_date) | Q(end_date__isnull=True)
        )
        qs = (
            EmployeeObjective.objects.filter(
                employee_id=employee,
                archive=False,
            )
            .filter(month_overlap)
            .select_related("objective_id")
            .order_by("-progress_percentage")[:8]
        )

        for emp_obj in qs:
            title = ""
            if emp_obj.objective_id:
                title = emp_obj.objective_id.title or ""
            elif emp_obj.objective:
                title = emp_obj.objective
            try:
                kr_count = emp_obj.key_result_id.count()
            except Exception:
                kr_count = 0
            results.append(
                {
                    "id": emp_obj.pk,
                    "title": title,
                    "status": emp_obj.status,
                    "progress": emp_obj.progress_percentage or 0,
                    "key_results_count": kr_count,
                }
            )

        # Fallbacks removed: the chart honours the date filter and shows empty
        # when no EmployeeObjective overlaps the selected month.
    except Exception:
        pass

    return JsonResponse({"objectives": results})


# ─── Announcements ────────────────────────────────────────────────────────────


@login_required
def ess_announcements(request):
    """GET /ess/api/announcements/?year=&month= — announcements active during the selected month."""

    from base.models import Announcement

    employee = _get_employee(request)
    if not employee:
        return JsonResponse({"error": "no employee"}, status=403)

    from_date, to_date = _parse_period(request)
    emp_department = None
    emp_job_position = None
    try:
        wi = employee.employee_work_info
        emp_department = wi.department_id
        emp_job_position = wi.job_position_id
    except Exception:
        pass

    results = []
    try:
        # Active during the selected month: created on/before month end AND not yet expired by month start.
        active_in_month = Q(created_at__date__lte=to_date) & (
            Q(expire_date__gte=from_date) | Q(expire_date__isnull=True)
        )
        not_expired = active_in_month

        # Use filtered_employees (pre-computed denormalised M2M) if available
        if Announcement.objects.filter(filtered_employees=employee).exists():
            qs = Announcement.objects.filter(not_expired, filtered_employees=employee)
        else:
            targeted = (
                Q(employees=employee)
                | (Q(department=emp_department) if emp_department else Q())
                | (Q(job_position=emp_job_position) if emp_job_position else Q())
            )
            broadcast = (
                Q(employees__isnull=True)
                & Q(department__isnull=True)
                & Q(job_position__isnull=True)
            )
            qs = Announcement.objects.filter(not_expired).filter(targeted | broadcast)

        qs = qs.distinct().order_by("-created_at")[:5]

        for ann in qs:
            results.append(
                {
                    "id": ann.pk,
                    "title": ann.title,
                    "description": (ann.description or "")[:160],
                    "date": (
                        ann.created_at.strftime("%b %d, %Y") if ann.created_at else ""
                    ),
                    "expire_date": (
                        ann.expire_date.strftime("%b %d") if ann.expire_date else None
                    ),
                }
            )
    except Exception:
        pass

    return JsonResponse({"announcements": results})


# ─── Upcoming events ──────────────────────────────────────────────────────────


@login_required
def ess_upcoming(request):
    """GET /ess/api/upcoming/?year=&month= — holidays, birthday, anniversary within 30 days from the start of the selected month."""
    from base.models import Holidays

    employee = _get_employee(request)
    if not employee:
        return JsonResponse({"error": "no employee"}, status=403)

    from_date, to_date = _parse_period(request)
    real_today = date.today()
    # When the picker covers today, anchor on today; otherwise anchor on the
    # period start so the panel reflects what was/will be upcoming in that window.
    today = real_today if from_date <= real_today <= to_date else from_date
    horizon = today + timedelta(days=30)

    # Holidays in the next 30 days
    holiday_list = []
    try:
        for h in Holidays.objects.filter(
            Q(is_specific=False) | Q(employees=employee),
            start_date__gte=today,
            start_date__lte=horizon,
        ).order_by("start_date")[:5]:
            holiday_list.append(
                {
                    "name": h.name,
                    "start": h.start_date.strftime("%b %d"),
                    "end": (
                        h.end_date.strftime("%b %d")
                        if h.end_date
                        else h.start_date.strftime("%b %d")
                    ),
                    "days_away": (h.start_date - today).days,
                }
            )
    except Exception:
        pass

    # Birthday
    birthday = None
    try:
        dob = employee.dob
        if dob:
            bday = dob.replace(year=today.year)
            if bday < today:
                bday = dob.replace(year=today.year + 1)
            days_away = (bday - today).days
            if days_away <= 30:
                birthday = {"date": bday.strftime("%b %d"), "days_away": days_away}
    except Exception:
        pass

    # Work anniversary
    anniversary = None
    try:
        date_joining = employee.employee_work_info.date_joining
        if date_joining:
            ann = date_joining.replace(year=today.year)
            if ann < today:
                ann = date_joining.replace(year=today.year + 1)
            days_away = (ann - today).days
            years = ann.year - date_joining.year
            if days_away <= 30 and years > 0:
                anniversary = {
                    "date": ann.strftime("%b %d"),
                    "days_away": days_away,
                    "years": years,
                }
    except Exception:
        pass

    return JsonResponse(
        {"holidays": holiday_list, "birthday": birthday, "anniversary": anniversary}
    )
