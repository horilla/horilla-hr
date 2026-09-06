"""
summary.py

Monthly attendance summary — aggregation helpers and views.
HR-187: data aggregation layer
HR-188: view + URL
"""

import calendar
import datetime
import io
import json
from collections import defaultdict
from itertools import chain

import pandas as pd
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from xlsxwriter.utility import xl_range

from attendance.models import Attendance, AttendanceDailyHours, AttendanceSummaryHours
from base.methods import (
    filtersubordinatesemployeemodel,
    get_company_leave_dates,
    get_holiday_dates,
    get_working_days,
    paginator_qry,
)
from base.models import (
    Company,
    Department,
    EmployeeShift,
    Holidays,
    JobPosition,
    Roster,
    WorkType,
)
from employee.filters import EmployeeFilter
from employee.models import Employee, EmployeeTag
from horilla.decorators import hx_request_required, login_required, manager_can_enter

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iter_dates(start, end):
    """Yield every date from start to end inclusive."""
    current = start
    while current <= end:
        yield current
        current += datetime.timedelta(days=1)


def _secs_to_label(secs):
    """Format a duration in seconds as 'Hh MMm'."""
    secs = int(secs or 0)
    return f"{secs // 3600}h {(secs % 3600) // 60:02d}m"


def _count_leave_days_in_range(leave_qs, from_date, to_date, off_dates):
    """
    Given a queryset of approved LeaveRequest objects (with leave_type_id
    pre-fetched), return two dicts keyed by employee PK:
        paid_map   {emp_pk: int}
        unpaid_map {emp_pk: int}

    Only days that fall within [from_date, to_date] AND are not already
    company/holiday off-days are counted.
    """
    off_set = set(off_dates)
    paid_map = defaultdict(int)
    unpaid_map = defaultdict(int)

    for leave in leave_qs:
        eff_start = max(leave.start_date, from_date)
        eff_end = min(leave.end_date or leave.start_date, to_date)
        if eff_start > eff_end:
            continue

        days = sum(1 for d in _iter_dates(eff_start, eff_end) if d not in off_set)
        emp_pk = leave.employee_id_id
        if leave.leave_type_id.payment == "paid":
            paid_map[emp_pk] += days
        else:
            unpaid_map[emp_pk] += days

    return paid_map, unpaid_map


# ---------------------------------------------------------------------------
# Public aggregation function (HR-187)
# ---------------------------------------------------------------------------


def build_monthly_summary(from_date, to_date, employee_qs):
    """
    Compute per-employee attendance summary for [from_date, to_date].

    Args:
        from_date   : datetime.date  — range start (inclusive)
        to_date     : datetime.date  — range end   (inclusive)
        employee_qs : Employee queryset filtered to the relevant company/dept

    Returns:
        rows            : list of dicts, one per employee
        total_working   : int — working days in the range (excl. company/public holidays)
        summary_totals  : dict — fleet-wide aggregated counts
    """
    from leave.models import LeaveRequest  # local import to avoid circular

    # -- 1. Working days (respects CompanyLeaves + public Holidays) ----------
    working_data = get_working_days(from_date, to_date)
    total_working = working_data["total_working_days"]
    off_dates = working_data["company_leave_dates"]  # combined, used for leave counting

    # -- 1b. Public holidays (separate column) --------------------------------
    holiday_dates_set = set(
        d for d in get_holiday_dates(from_date, to_date) if from_date <= d <= to_date
    )
    total_holidays = len(holiday_dates_set)

    # -- 1c. Company leave dates (fallback week-off when no roster) -----------
    raw_cl = list(
        set(
            get_company_leave_dates(from_date.year)
            + get_company_leave_dates(to_date.year)
        )
    )
    total_company_leaves = len([d for d in raw_cl if from_date <= d <= to_date])

    # -- 2. Attendance per employee (single DB hit, hour-based) ---------------
    # Fetch worked seconds + minimum per record; classify as full (1.0),
    # half (0.5), or absent (0.0) using the default grace time.
    # Using values() + Python loop instead of annotate(Count()) avoids the
    # GROUP BY join-multiplication caused by HorillaCompanyManager's work-info
    # join.
    from attendance.methods.utils import strtime_seconds as _strtime_secs
    from attendance.models import GraceTime as _GraceTime

    emp_pks = list(employee_qs.values_list("pk", flat=True))

    grace_secs = 0
    _dg = _GraceTime.objects.filter(is_default=True, is_active=True).first()
    if _dg:
        grace_secs = _dg.allowed_time_in_secs or 0

    att_records = Attendance.objects.filter(
        employee_id__in=emp_pks,
        attendance_date__range=(from_date, to_date),
    ).values(
        "employee_id_id",
        "at_work_second",
        "overtime_second",
        "minimum_hour",
        "attendance_date",
    )

    att_dates_map = defaultdict(set)  # {emp_pk: set(dates)} — conflict detection
    att_date_value_map = defaultdict(dict)  # {emp_pk: {date: 0.5|1.0}} — per-date value
    att_date_secs_map = defaultdict(
        dict
    )  # {emp_pk: {date: at_work_second}} — raw seconds
    # {emp_pk: {date: overtime_second}} — already computed per-record as
    # max(0, at_work_second - minimum_hour), with minimum_hour forced to
    # "00:00" on days with no shift schedule (holiday/company leave) — so
    # unscheduled days are entirely overtime.
    att_date_ot_secs_map = defaultdict(dict)
    for _r in att_records:
        _pk = _r["employee_id_id"]
        _date = _r["attendance_date"]
        _worked = _r["at_work_second"] or 0
        _min_secs = _strtime_secs(_r["minimum_hour"]) if _r.get("minimum_hour") else 0
        if _min_secs > 0:
            _eff_min = max(0, _min_secs - grace_secs)
            if _worked >= _eff_min:
                _val = 1.0
            elif _worked >= _min_secs / 2:
                _val = 0.5
            else:
                _val = 0.0  # hours too low — attendance exists but doesn't count
        else:
            _val = 1.0
        att_dates_map[_pk].add(_date)
        att_date_value_map[_pk][_date] = _val
        att_date_secs_map[_pk][_date] = _worked
        att_date_ot_secs_map[_pk][_date] = _r["overtime_second"] or 0

    # -- 2b. Batch-load shift schedules for hours computation -----------------
    from base.models import EmployeeShiftSchedule
    from employee.models import EmployeeWorkInformation as _EWI

    _DAY_NAMES = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]

    emp_shift_map = {}  # {emp_pk: shift_pk or None}
    for _wi in _EWI.objects.filter(employee_id__in=emp_pks).values(
        "employee_id_id", "shift_id_id"
    ):
        emp_shift_map[_wi["employee_id_id"]] = _wi["shift_id_id"]

    shift_pk_set = {v for v in emp_shift_map.values() if v}
    shift_day_secs = defaultdict(dict)  # {shift_pk: {day_name: seconds}}
    if shift_pk_set:
        for _ss in (
            EmployeeShiftSchedule.objects.filter(shift_id__in=shift_pk_set)
            .select_related("day")
            .values("shift_id_id", "day__day", "minimum_working_hour")
        ):
            _spk = _ss["shift_id_id"]
            _day = _ss["day__day"]
            _secs = (
                _strtime_secs(_ss["minimum_working_hour"])
                if _ss["minimum_working_hour"]
                else 0
            )
            shift_day_secs[_spk][_day] = _secs

    # -- 2c. Load existing manually-edited hours (never overwritten by compute) --
    hours_override_map = {}  # {emp_pk: hours_second}
    for _h in AttendanceSummaryHours.objects.filter(
        employee_id__in=emp_pks,
        from_date=from_date,
        to_date=to_date,
        is_manually_edited=True,
    ).values("employee_id_id", "hours_second"):
        hours_override_map[_h["employee_id_id"]] = _h["hours_second"]

    # -- 2d. Per-day manual hours from the calendar editor --------------------
    daily_manual_map = defaultdict(dict)  # {emp_pk: {date: hours_second}}
    for _dh in AttendanceDailyHours.objects.filter(
        employee_id__in=emp_pks,
        date__range=(from_date, to_date),
        is_manually_edited=True,
    ).values("employee_id_id", "date", "hours_second"):
        daily_manual_map[_dh["employee_id_id"]][_dh["date"]] = _dh["hours_second"]

    # -- 3. Approved leave requests overlapping the range (single DB hit) ----
    leave_qs = (
        LeaveRequest.objects.filter(
            employee_id__in=emp_pks,
            status="approved",
            start_date__lte=to_date,
        )
        .filter(
            # end_date null means single-day leave starting at start_date
            end_date__isnull=False,
            end_date__gte=from_date,
        )
        .select_related("leave_type_id")
    )
    # Also include single-day leaves (end_date is null) within range
    single_day_qs = LeaveRequest.objects.filter(
        employee_id__in=emp_pks,
        status="approved",
        start_date__range=(from_date, to_date),
        end_date__isnull=True,
    ).select_related("leave_type_id")
    from itertools import chain

    all_leaves = list(chain(leave_qs, single_day_qs))

    # Per-employee per-date leave tracking (paid / unpaid, for conflict detection)
    leave_dates_per_emp = defaultdict(set)
    paid_day_dates_per_emp = defaultdict(set)  # {emp_pk: set(paid-leave dates)}
    unpaid_day_dates_per_emp = defaultdict(set)  # {emp_pk: set(unpaid-leave dates)}
    for _lr in all_leaves:
        _s = max(_lr.start_date, from_date)
        _e = min(_lr.end_date or _lr.start_date, to_date)
        for _d in _iter_dates(_s, _e):
            leave_dates_per_emp[_lr.employee_id_id].add(_d)
            if _lr.leave_type_id.payment == "paid":
                paid_day_dates_per_emp[_lr.employee_id_id].add(_d)
            else:
                unpaid_day_dates_per_emp[_lr.employee_id_id].add(_d)

    # -- 4. Roster-based week-off per employee (single DB hit) ---------------
    roster_qs = Roster.objects.filter(
        employee_id__in=emp_pks,
        date__range=(from_date, to_date),
    ).values("employee_id", "is_off", "date")
    roster_has = set()
    roster_off_dates = defaultdict(set)  # {emp_pk: set(week_off_dates)}
    for entry in roster_qs:
        pk = entry["employee_id"]
        roster_has.add(pk)
        if entry["is_off"]:
            roster_off_dates[pk].add(entry["date"])

    # -- 5. Batch-fetch conflict resolutions (with type) for all employees ----
    from attendance.models import AttendanceConflictResolution

    resolutions_per_emp = defaultdict(dict)  # {emp_pk: {date: resolution_str}}
    for r in AttendanceConflictResolution.objects.filter(
        date__range=(from_date, to_date),
    ).values("employee_id_id", "date", "resolution"):
        resolutions_per_emp[r["employee_id_id"]][r["date"]] = r["resolution"]
    # Flat date-set form kept for conflict-resolution count logic
    resolutions_by_emp = {pk: set(d.keys()) for pk, d in resolutions_per_emp.items()}

    # -- 6. Build per-employee rows using per-date iteration -----------------
    # This is the only correct way to apply HR overrides to summary counts.
    # O(employees × days_in_range) — for a 30-day window with 200 employees
    # that is ~6 000 iterations; well within acceptable bounds.
    rows = []
    total_present = total_absent = total_paid = total_unpaid = total_week_off = 0.0
    total_holiday = 0
    total_conflicts = 0

    off_set = frozenset(off_dates)  # company leaves + public holidays
    company_off_dates = {d for d in raw_cl if from_date <= d <= to_date}
    all_dates_in_range = list(_iter_dates(from_date, to_date))

    # Resolution → (bucket, value) for direct overrides
    _RES_BUCKET = {
        "full_present": ("present", 1.0),
        "half_present": ("present", 0.5),
        "absent": ("absent", 1.0),
        "paid_leave": ("paid_leave", 1.0),
        "unpaid_leave": ("unpaid_leave", 1.0),
        "holiday": ("holiday", 1.0),
        "week_off": ("week_off", 1.0),
    }

    emp_computed_hours = {}  # {emp_pk: hours_second} — filled per employee below
    hours_upsert = []  # AttendanceSummaryHours instances to bulk-upsert

    for emp in employee_qs.select_related(
        "employee_work_info__department_id",
        "employee_work_info__job_position_id",
    ):
        _att_vals = att_date_value_map.get(emp.pk, {})
        _att_secs = att_date_secs_map.get(emp.pk, {})
        _paid_dates = paid_day_dates_per_emp.get(emp.pk, set())
        _unpaid_dates = unpaid_day_dates_per_emp.get(emp.pk, set())
        _emp_off = (
            roster_off_dates.get(emp.pk, set())
            if emp.pk in roster_has
            else company_off_dates
        )
        _resolutions = resolutions_per_emp.get(emp.pk, {})
        _shift_pk = emp_shift_map.get(emp.pk)
        _shift_sched = shift_day_secs.get(_shift_pk, {}) if _shift_pk else {}
        _daily_hrs = daily_manual_map.get(emp.pk, {})  # per-day manual overrides

        present = paid_leave = unpaid_leave = week_off = holiday_c = absent = 0.0
        hours_second = 0

        for d in all_dates_in_range:
            res = _resolutions.get(d)

            # Direct HR override — use as-is
            bucket_info = _RES_BUCKET.get(res)
            if bucket_info is not None:
                bucket, val = bucket_info
                if bucket == "present":
                    present += val
                elif bucket == "paid_leave":
                    paid_leave += val
                elif bucket == "unpaid_leave":
                    unpaid_leave += val
                elif bucket == "absent":
                    absent += val
                elif bucket == "holiday":
                    holiday_c += val
                elif bucket == "week_off":
                    week_off += val

                # Hours for regularized present days (per-day manual override wins)
                if bucket == "present":
                    _day_name = _DAY_NAMES[d.weekday()]
                    _full_secs = _shift_sched.get(_day_name, 0) or 28800  # 8h default
                    _day_manual = _daily_hrs.get(d)
                    hours_second += (
                        _day_manual
                        if _day_manual is not None
                        else int(_full_secs * val)
                    )
                continue

            if res == "partial_hours":
                # Count as present proportionally: actual_secs / shift_min (capped at 1.0)
                _actual_secs = _att_secs.get(d, 0)
                _day_name = _DAY_NAMES[d.weekday()]
                _full_secs = _shift_sched.get(_day_name, 0) or 28800
                val = (
                    min(1.0, _actual_secs / _full_secs)
                    if _full_secs > 0
                    else (1.0 if _actual_secs > 0 else 0.0)
                )
                present += val
                if val < 1.0:
                    absent += 1.0 - val
                _day_manual = _daily_hrs.get(d)
                hours_second += _day_manual if _day_manual is not None else _actual_secs
                continue

            # Legacy "attendance" / "leave" — fall through to natural
            # No resolution — natural computation
            if d in _att_vals:
                val = _att_vals[d]
                if d in holiday_dates_set:
                    holiday_c += 1.0  # HO — attendance on holiday
                elif d in _emp_off:
                    week_off += 1.0  # WO — attendance on week-off
                else:
                    present += val
                    # Half-day (0.5) or zero-hour: remaining fraction is absent
                    if val < 1.0:
                        absent += 1.0 - val
                # Actual hours (per-day manual override wins)
                _day_manual = _daily_hrs.get(d)
                hours_second += (
                    _day_manual if _day_manual is not None else _att_secs.get(d, 0)
                )
            elif d in _paid_dates:
                paid_leave += 1.0
            elif d in _unpaid_dates:
                unpaid_leave += 1.0
            elif d in holiday_dates_set:
                holiday_c += 1.0
            elif d in _emp_off:
                week_off += 1.0
            elif d not in off_set:
                absent += 1.0  # working day with no activity

        # Conflict detection (uses raw data, not overrides). Attendance on a
        # holiday/week-off is normal overtime work, not a data discrepancy —
        # only attendance overlapping approved leave counts as a conflict.
        att_dates = att_dates_map.get(emp.pk, set())
        emp_leave_dates = leave_dates_per_emp.get(emp.pk, set())
        conflict_date_set = att_dates & emp_leave_dates
        conflict_days = len(conflict_date_set)

        emp_resolved_dates = resolutions_by_emp.get(emp.pk, set())
        resolved_conflicts = len(conflict_date_set & emp_resolved_dates)

        # Resolve final hours (manual override wins)
        emp_computed_hours[emp.pk] = hours_second
        if emp.pk in hours_override_map:
            final_hours = hours_override_map[emp.pk]
            is_hours_edited = True
        else:
            final_hours = hours_second
            is_hours_edited = False
            hours_upsert.append(
                AttendanceSummaryHours(
                    employee_id_id=emp.pk,
                    from_date=from_date,
                    to_date=to_date,
                    hours_second=hours_second,
                    is_manually_edited=False,
                )
            )

        _fh, _fm = final_hours // 3600, (final_hours % 3600) // 60
        hours_label = f"{_fh}h {_fm:02d}m"

        # Worked / Regular / Overtime breakdown for this employee over the
        # period — from raw attendance, independent of the credited
        # hours_second above. Overtime splits into three sources:
        #   - ot_regular:  worked beyond minimum_hour on a normal working day
        #   - ot_week_off: any attendance on a week-off day (entirely OT)
        #   - ot_holiday:  any attendance on a holiday (entirely OT)
        _emp_ot_secs = att_date_ot_secs_map.get(emp.pk, {})
        ot_regular_seconds = ot_week_off_seconds = ot_holiday_seconds = 0
        for _d, _wsec in _att_secs.items():
            # HR has explicitly regularized this day away from its holiday/
            # week-off classification (Full Present / Half Day) — treat the
            # hours like a normal working day (regular + capped OT) instead
            # of counting them entirely as holiday/week-off overtime.
            _regularized = _resolutions.get(_d) in ("full_present", "half_present")
            if _d in holiday_dates_set and not _regularized:
                ot_holiday_seconds += _wsec
            elif _d in _emp_off and not _regularized:
                ot_week_off_seconds += _wsec
            else:
                ot_regular_seconds += _emp_ot_secs.get(_d, 0)

        worked_seconds = sum(_att_secs.values())
        overtime_seconds = ot_regular_seconds + ot_week_off_seconds + ot_holiday_seconds
        regular_seconds = worked_seconds - overtime_seconds

        rows.append(
            {
                "employee": emp,
                "present": present,
                "paid_leave": int(paid_leave),
                "unpaid_leave": int(unpaid_leave),
                "absent": absent,
                "total_working": total_working,
                "week_off": int(week_off),
                "holiday": int(holiday_c),
                "conflict_days": conflict_days,
                "resolved_conflicts": resolved_conflicts,
                "unresolved_conflicts": conflict_days - resolved_conflicts,
                "hours_second": final_hours,
                "hours_label": hours_label,
                "is_hours_edited": is_hours_edited,
                "worked_seconds": worked_seconds,
                "regular_seconds": regular_seconds,
                "overtime_seconds": overtime_seconds,
                "worked_label": _secs_to_label(worked_seconds),
                "regular_label": _secs_to_label(regular_seconds),
                "overtime_label": _secs_to_label(overtime_seconds),
                "ot_regular_seconds": ot_regular_seconds,
                "ot_week_off_seconds": ot_week_off_seconds,
                "ot_holiday_seconds": ot_holiday_seconds,
                "ot_regular_label": _secs_to_label(ot_regular_seconds),
                "ot_week_off_label": _secs_to_label(ot_week_off_seconds),
                "ot_holiday_label": _secs_to_label(ot_holiday_seconds),
            }
        )

        total_present += present
        total_absent += absent
        total_paid += paid_leave
        total_unpaid += unpaid_leave
        total_week_off += week_off
        total_holiday += holiday_c
        total_conflicts += conflict_days

    # Bulk-upsert computed hours (only for non-manually-edited records)
    if hours_upsert:
        AttendanceSummaryHours.objects.bulk_create(
            hours_upsert,
            update_conflicts=True,
            unique_fields=["employee_id", "from_date", "to_date"],
            update_fields=["hours_second"],
        )

    summary_totals = {
        "total_employees": len(rows),
        "total_present": total_present,
        "total_absent": total_absent,
        "total_paid_leave": total_paid,
        "total_unpaid_leave": total_unpaid,
        "week_off": total_week_off,
        "holiday": total_holiday,
        "total_conflicts": total_conflicts,
    }

    return rows, total_working, summary_totals


# ---------------------------------------------------------------------------
# Views (HR-188)
# ---------------------------------------------------------------------------


def _parse_date(value, fallback):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


@login_required
@manager_can_enter("attendance.view_attendance")
def attendance_monthly_summary(request):
    """
    Full-page view for the monthly attendance summary.
    Renders the shell (filter bar + stat cards + empty table).
    The table is populated via HTMX on load.
    """
    today = datetime.date.today()
    from_date_default = today.replace(day=1)
    to_date_default = today.replace(day=calendar.monthrange(today.year, today.month)[1])

    # Employee/Department/Job Position/Shift/Work Type render as AJAX-
    # searched Select2 comboboxes now (see monthly_summary.html) rather
    # than pre-rendering every instance as an <option> tag -- Employee in
    # particular doesn't scale as a full dump. Only the currently-selected
    # instances need a real <option> here (select2's own preload
    # requirement), same pattern as HorillaFilterSet._apply_ajax_fields.
    context = {
        "from_date": request.GET.get("from_date", from_date_default.isoformat()),
        "to_date": request.GET.get("to_date", to_date_default.isoformat()),
        "selected_employees": Employee.objects.filter(
            pk__in=request.GET.getlist("employee_id")
        ),
        "selected_departments": Department.objects.filter(
            pk__in=request.GET.getlist("department_id")
        ),
        "selected_job_positions": JobPosition.objects.filter(
            pk__in=request.GET.getlist("job_position_id")
        ),
        "selected_shifts": EmployeeShift.objects.filter(
            pk__in=request.GET.getlist("shift_id")
        ),
        "selected_work_types": WorkType.objects.filter(
            pk__in=request.GET.getlist("work_type_id")
        ),
        # Advanced section -- less commonly filtered on than Work Info's own
        # fields, but already fully supported server-side for free: the
        # table/export views build EmployeeFilter(request.GET), which
        # already declares company_id/reporting_manager_id/tags/is_active
        # and applies whichever of them are present in the querystring via
        # its own .qs, no new backend filtering logic needed here.
        "selected_companies": Company.objects.filter(
            pk__in=request.GET.getlist("employee_work_info__company_id")
        ),
        "selected_reporting_managers": Employee.objects.filter(
            pk__in=request.GET.getlist("employee_work_info__reporting_manager_id")
        ),
        "selected_tags": EmployeeTag.objects.filter(
            pk__in=request.GET.getlist("employee_work_info__tags")
        ),
        "is_active": request.GET.get("is_active", ""),
        "pd": request.GET.urlencode(),
    }
    return render(request, "attendance/monthly_summary/monthly_summary.html", context)


@login_required
@manager_can_enter("attendance.view_attendance")
@hx_request_required
def attendance_monthly_summary_table(request):
    """
    HTMX partial — returns the summary table rows.
    Triggered by the Filter button and on initial page load.
    """
    today = datetime.date.today()
    from_date = _parse_date(request.GET.get("from_date"), today.replace(day=1))
    to_date = _parse_date(
        request.GET.get("to_date"),
        today.replace(day=calendar.monthrange(today.year, today.month)[1]),
    )

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    employee_filter = EmployeeFilter(request.GET)
    employee_qs = filtersubordinatesemployeemodel(
        request, employee_filter.qs, "attendance.view_attendance"
    )

    # Multi-select filters — handled explicitly here (getlist + __in) rather
    # than through EmployeeFilter's own auto-generated single-value fields,
    # so this stays local to the summary page instead of changing the
    # shared EmployeeFilter's widgets/behavior for every other page that
    # reuses it. Param names deliberately don't match EmployeeFilter's own
    # "employee_work_info__department_id"-style field names, so it ignores
    # them entirely and there's no double-filtering.
    emp_ids = request.GET.getlist("employee_id")
    if emp_ids:
        employee_qs = employee_qs.filter(pk__in=emp_ids)

    dept_ids = request.GET.getlist("department_id")
    if dept_ids:
        employee_qs = employee_qs.filter(employee_work_info__department_id__in=dept_ids)

    job_position_ids = request.GET.getlist("job_position_id")
    if job_position_ids:
        employee_qs = employee_qs.filter(
            employee_work_info__job_position_id__in=job_position_ids
        )

    shift_ids = request.GET.getlist("shift_id")
    if shift_ids:
        employee_qs = employee_qs.filter(employee_work_info__shift_id__in=shift_ids)

    work_type_ids = request.GET.getlist("work_type_id")
    if work_type_ids:
        employee_qs = employee_qs.filter(
            employee_work_info__work_type_id__in=work_type_ids
        )

    employee_qs = employee_qs.distinct()

    rows, total_working, summary_totals = build_monthly_summary(
        from_date, to_date, employee_qs
    )

    # Sorting — mirrors the outcome of HorillaListView's sortby() (query
    # param + toggling asc/desc, arrows reflected in the header) without its
    # session-cached Reverse()-object machinery, since `rows` here is a
    # plain list of dicts built by build_monthly_summary(), not a queryset
    # a .order_by() could apply to. "Working Days" is deliberately excluded
    # (like HorillaListView leaves some columns out of its sortby_mapping)
    # since it's the same fleet-wide value on every row — sorting by it is
    # a no-op.
    def _dept_name(row):
        work_info = getattr(row["employee"], "employee_work_info", None)
        dept = getattr(work_info, "department_id", None) if work_info else None
        return (getattr(dept, "department", "") or "").lower()

    SORT_KEYS = {
        "employee": lambda r: r["employee"].get_full_name().lower(),
        "badge_id": lambda r: (r["employee"].badge_id or "").lower(),
        "department": _dept_name,
        "present": lambda r: r["present"],
        "absent": lambda r: r["absent"],
        "paid_leave": lambda r: r["paid_leave"],
        "unpaid_leave": lambda r: r["unpaid_leave"],
        "week_off": lambda r: r["week_off"],
        "holiday": lambda r: r["holiday"],
        "conflicts": lambda r: r["conflict_days"],
        "worked": lambda r: r["worked_seconds"],
        "regular": lambda r: r["regular_seconds"],
        "overtime": lambda r: r["overtime_seconds"],
    }
    sort_key = request.GET.get("sort")
    sort_dir = request.GET.get("dir", "asc")
    if sort_key in SORT_KEYS:
        rows = sorted(rows, key=SORT_KEYS[sort_key], reverse=(sort_dir == "desc"))

    # Same convention as HorillaListView.select_all(): every pk matching the
    # current filters (not just this page) is baked into the "Select" button
    # at render time, so clicking it needs no extra request. Derived from
    # `rows` (the same list summary_totals/"Employees" is built from) rather
    # than a second, independent employee_qs.count() -- that separate call
    # can land on a different result than what actually built the rows/stats
    # below it (e.g. a queryset re-evaluated under different company-scoping
    # thread-local state), so anchoring both to one already-verified source
    # guarantees they can never disagree.
    select_all_ids = json.dumps([row["employee"].pk for row in rows])
    total_employee_count = len(rows)

    rows = paginator_qry(rows, request.GET.get("page"))

    context = {
        "rows": rows,
        "total_working": total_working,
        "summary_totals": summary_totals,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "pd": request.GET.urlencode(),
        "select_all_ids": select_all_ids,
        "total_employee_count": total_employee_count,
        "sort_key": sort_key,
        "sort_dir": sort_dir,
    }
    return render(request, "attendance/monthly_summary/table_partial.html", context)


@login_required
@manager_can_enter("attendance.view_attendance")
def attendance_monthly_summary_export(request):
    """
    HR-190 — Download the current summary as an XLSX file.
    Accepts the same GET params as the table view (no pagination).
    """
    today = datetime.date.today()
    from_date = _parse_date(request.GET.get("from_date"), today.replace(day=1))
    to_date = _parse_date(
        request.GET.get("to_date"),
        today.replace(day=calendar.monthrange(today.year, today.month)[1]),
    )

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    # Rows checked via the table's own selection checkboxes take priority
    # over the filter bar entirely — picking specific rows is a more
    # deliberate, specific choice than whatever broader filters happen to
    # be set, matching "export only what I selected" rather than "export
    # what I selected, further narrowed by filters I may have forgotten
    # were still applied". filtersubordinatesemployeemodel() still applies
    # so a manager can't export a subordinate outside their scope by
    # crafting the request manually.
    selected_ids = request.GET.getlist("employee_ids")
    if selected_ids:
        employee_qs = filtersubordinatesemployeemodel(
            request,
            Employee.objects.filter(pk__in=selected_ids),
            "attendance.view_attendance",
        )
    else:
        employee_filter = EmployeeFilter(request.GET)
        employee_qs = filtersubordinatesemployeemodel(
            request, employee_filter.qs, "attendance.view_attendance"
        )
        emp_id = request.GET.get("employee_id")
        if emp_id:
            employee_qs = employee_qs.filter(pk=emp_id)

    rows, total_working, _extra = build_monthly_summary(from_date, to_date, employee_qs)

    # Build DataFrame
    data = []
    for row in rows:
        emp = row["employee"]
        work_info = getattr(emp, "employee_work_info", None)
        data.append(
            {
                str(_("Employee")): emp.get_full_name(),
                str(_("Badge ID")): emp.badge_id or "",
                str(_("Department")): getattr(
                    getattr(work_info, "department_id", None), "department", ""
                )
                or "",
                str(_("Designation")): getattr(
                    getattr(work_info, "job_position_id", None), "job_position", ""
                )
                or "",
                str(_("Present Days")): row["present"],
                str(_("Absent Days")): row["absent"],
                str(_("Paid Leave Days")): row["paid_leave"],
                str(_("Unpaid Leave Days")): row["unpaid_leave"],
                str(_("Working Days")): total_working,
                str(_("Week Off")): row["week_off"],
                str(_("Holiday")): row["holiday"],
                str(_("Hours")): row.get("hours_label", "0h 00m"),
            }
        )

    columns = [
        str(_("Employee")),
        str(_("Badge ID")),
        str(_("Department")),
        str(_("Designation")),
        str(_("Present Days")),
        str(_("Absent Days")),
        str(_("Paid Leave Days")),
        str(_("Unpaid Leave Days")),
        str(_("Working Days")),
        str(_("Week Off")),
        str(_("Holiday")),
        str(_("Hours")),
    ]
    df = pd.DataFrame(data, columns=columns) if data else pd.DataFrame(columns=columns)

    company = getattr(request, "selected_company_instance", None)
    company_title = getattr(company, "company", "") if company else ""
    company_logo = getattr(company, "icon", "") if company else ""
    date_range_str = f"{from_date}  TO  {to_date}"
    report_title = str(_("Monthly Attendance Summary"))

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Summary", startrow=6)
        workbook = writer.book
        worksheet = writer.sheets["Summary"]

        # Header formats
        company_fmt = workbook.add_format(
            {"bold": True, "font_size": 16, "align": "center", "valign": "vcenter"}
        )
        title_fmt = workbook.add_format(
            {
                "bold": True,
                "font_size": 14,
                "align": "center",
                "valign": "vcenter",
                "font_color": "#dc3545",
            }
        )
        date_fmt = workbook.add_format(
            {"italic": True, "font_size": 11, "align": "center", "valign": "vcenter"}
        )

        total_cols = len(df.columns)
        worksheet.merge_range(
            xl_range(0, 0, 0, total_cols - 1), company_title, company_fmt
        )
        worksheet.merge_range(
            xl_range(1, 0, 2, total_cols - 1), report_title, title_fmt
        )
        worksheet.merge_range(
            xl_range(3, 0, 3, total_cols - 1), date_range_str, date_fmt
        )

        if company_logo:
            try:
                import os

                worksheet.insert_image(
                    "A1",
                    str(os.path.join(settings.MEDIA_ROOT, str(company_logo))),
                    {"x_scale": 0.25, "y_scale": 0.25},
                )
            except Exception:
                pass

        # Column-level colour formats (applied to Present/Absent/Leave columns)
        present_fmt = workbook.add_format(
            {"bg_color": "#d4edda", "font_color": "#155724"}
        )
        absent_fmt = workbook.add_format(
            {"bg_color": "#f8d7da", "font_color": "#721c24"}
        )
        paid_fmt = workbook.add_format({"bg_color": "#cce5ff", "font_color": "#004085"})
        unpaid_fmt = workbook.add_format(
            {"bg_color": "#fff3cd", "font_color": "#856404"}
        )

        col_fmt_map = {
            str(_("Present Days")): present_fmt,
            str(_("Absent Days")): absent_fmt,
            str(_("Paid Leave Days")): paid_fmt,
            str(_("Unpaid Leave Days")): unpaid_fmt,
        }
        for col_idx, col_name in enumerate(df.columns):
            fmt = col_fmt_map.get(col_name)
            if fmt:
                for row_idx in range(len(df)):
                    worksheet.write(
                        row_idx + 7, col_idx, df.iloc[row_idx][col_name], fmt
                    )

        # Auto column width
        for col_idx, col in enumerate(df.columns):
            if len(df):
                max_len = max(df[col].astype(str).map(len).max(), len(col))
            else:
                max_len = len(col)
            worksheet.set_column(col_idx, col_idx, min(max_len + 2, 40))

    output.seek(0)
    filename = f"Attendance_Summary_{from_date}_{to_date}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@hx_request_required
def attendance_monthly_summary_detail(request):
    """
    HTMX popover detail for a single metric cell in the monthly summary table.
    Returns an HTML snippet with the underlying records for the given metric.
    """
    from leave.models import LeaveRequest

    emp_id = request.GET.get("employee_id")
    from_date = _parse_date(request.GET.get("from_date"), datetime.date.today())
    to_date = _parse_date(request.GET.get("to_date"), datetime.date.today())
    metric = request.GET.get("metric", "present")

    try:
        emp = Employee.objects.get(pk=emp_id)
    except Employee.DoesNotExist:
        return HttpResponse(
            "<p style='padding:12px;color:#6c757d;font-size:.8rem;'>Employee not found.</p>"
        )

    context = {"metric": metric}

    # Fetch all manual overrides for this employee/period so each metric branch
    # can mark which dates were regularized via AttendanceConflictResolution.
    from attendance.models import AttendanceConflictResolution as _ACR

    _res_qs = _ACR.objects.filter(
        employee_id=emp,
        date__range=(from_date, to_date),
    ).values("date", "resolution")
    resolution_map = {r["date"]: r["resolution"] for r in _res_qs}

    if metric == "present":
        from attendance.methods.utils import strtime_seconds as _ss
        from attendance.models import GraceTime as _GT

        _grace = 0
        _dg = _GT.objects.filter(is_default=True, is_active=True).first()
        if _dg:
            _grace = _dg.allowed_time_in_secs or 0

        raw = list(
            Attendance.objects.filter(
                employee_id=emp,
                attendance_date__range=(from_date, to_date),
            )
            .order_by("attendance_date")
            .values(
                "attendance_date",
                "attendance_clock_in",
                "attendance_clock_out",
                "at_work_second",
                "minimum_hour",
                "overtime_second",
                "attendance_overtime_approve",
            )
        )
        for _r in raw:
            _worked = _r["at_work_second"] or 0
            _min_secs = _ss(_r["minimum_hour"]) if _r.get("minimum_hour") else 0
            if _min_secs > 0:
                _eff = max(0, _min_secs - _grace)
                if _worked >= _eff:
                    _r["day_type"] = "full"
                elif _worked >= _min_secs / 2:
                    _r["day_type"] = "half"
                else:
                    # Distinguish: no clock-out → genuinely missing out
                    #              has clock-out → worked short hours
                    if _r["attendance_clock_out"]:
                        _r["day_type"] = "short"
                    else:
                        _r["day_type"] = "mo"
            else:
                _r["day_type"] = "full"
            # human-readable worked / required / OT labels
            _wh, _wm = _worked // 3600, (_worked % 3600) // 60
            _r["at_work_label"] = f"{_wh}h {_wm:02d}m" if _worked > 0 else ""
            if _min_secs > 0:
                _mh, _mm = _min_secs // 3600, (_min_secs % 3600) // 60
                _r["worked_label"] = f"{_wh}h{_wm:02d}m / {_mh}h{_mm:02d}m"
            else:
                _r["worked_label"] = ""
            _ot_secs = _r.get("overtime_second") or 0
            if _ot_secs > 0:
                _oh, _om = _ot_secs // 3600, (_ot_secs % 3600) // 60
                _r["ot_label"] = f"{_oh}h {_om:02d}m"
                _r["ot_approved"] = bool(_r.get("attendance_overtime_approve"))
            else:
                _r["ot_label"] = ""
                _r["ot_approved"] = False
            _r["is_regularized"] = _r["attendance_date"] in resolution_map

        # Include resolution-only "present" days that have no attendance record
        # (build_monthly_summary counts these via AttendanceConflictResolution).
        _att_dates = {_r["attendance_date"] for _r in raw}
        for _d, _res in sorted(resolution_map.items()):
            if _res in ("full_present", "half_present") and _d not in _att_dates:
                raw.append(
                    {
                        "attendance_date": _d,
                        "attendance_clock_in": None,
                        "attendance_clock_out": None,
                        "at_work_second": 0,
                        "minimum_hour": None,
                        "day_type": "full" if _res == "full_present" else "half",
                        "worked_label": "",
                        "at_work_label": "",
                        "ot_label": "",
                        "ot_approved": False,
                        "is_regularized": True,
                    }
                )
        raw.sort(key=lambda _r: _r["attendance_date"])
        context["records"] = raw

    elif metric in ("paid_leave", "unpaid_leave"):
        payment = "paid" if metric == "paid_leave" else "unpaid"
        records = list(
            LeaveRequest.objects.filter(
                employee_id=emp,
                status__in=["approved", "requested"],
                leave_type_id__payment=payment,
                start_date__lte=to_date,
                end_date__isnull=False,
                end_date__gte=from_date,
            ).select_related("leave_type_id")
        ) + list(
            LeaveRequest.objects.filter(
                employee_id=emp,
                status__in=["approved", "requested"],
                leave_type_id__payment=payment,
                start_date__range=(from_date, to_date),
                end_date__isnull=True,
            ).select_related("leave_type_id")
        )
        # Sort: approved first, then requested; within each group by start_date
        records.sort(key=lambda r: (0 if r.status == "approved" else 1, r.start_date))
        # Add resolution-only entries (days overridden to this leave type without a leave request)
        _res_target = "paid_leave" if metric == "paid_leave" else "unpaid_leave"
        _leave_dates = set()
        for _r in records:
            _s = _r.start_date
            _e = _r.end_date or _r.start_date
            for _d in _iter_dates(max(_s, from_date), min(_e, to_date)):
                _leave_dates.add(_d)
        _res_only_dates = sorted(
            _d
            for _d, _res in resolution_map.items()
            if _res == _res_target and _d not in _leave_dates
        )
        # Represent each as a minimal object the template can render
        context["records"] = records
        context["resolution_only_leave"] = [{"date": _d} for _d in _res_only_dates]

    elif metric == "absent":
        working_data = get_working_days(from_date, to_date)
        off_set = set(working_data["company_leave_dates"])
        working_dates = {d for d in _iter_dates(from_date, to_date) if d not in off_set}

        present_dates = set(
            Attendance.objects.filter(
                employee_id=emp,
                attendance_date__range=(from_date, to_date),
            ).values_list("attendance_date", flat=True)
        )
        leave_dates = set()
        for lr in LeaveRequest.objects.filter(
            employee_id=emp,
            status="approved",
            start_date__lte=to_date,
            end_date__isnull=False,
            end_date__gte=from_date,
        ):
            for d in _iter_dates(
                max(lr.start_date, from_date), min(lr.end_date, to_date)
            ):
                if d not in off_set:
                    leave_dates.add(d)
        for lr in LeaveRequest.objects.filter(
            employee_id=emp,
            status="approved",
            start_date__range=(from_date, to_date),
            end_date__isnull=True,
        ):
            if lr.start_date not in off_set:
                leave_dates.add(lr.start_date)

        # Base absent set: working days with no attendance and no approved leave
        _absent_set = working_dates - present_dates - leave_dates
        # Also include days where resolution="absent" (attendance present but overridden)
        for _d, _res in resolution_map.items():
            if _res == "absent" and _d in present_dates:
                _absent_set.add(_d)
        # Exclude days that resolution moved OUT of absent bucket
        _res_non_absent = {
            "full_present",
            "half_present",
            "partial_hours",
            "paid_leave",
            "unpaid_leave",
            "holiday",
            "week_off",
        }
        _absent_set -= {
            _d for _d, _res in resolution_map.items() if _res in _res_non_absent
        }
        context["records"] = [
            {"date": d, "is_regularized": d in resolution_map}
            for d in sorted(_absent_set)
        ]

    elif metric == "conflict":
        from attendance.methods.utils import strtime_seconds as _ss
        from attendance.models import GraceTime as _GT
        from leave.models import LeaveRequest as _LR

        _grace = 0
        _dg = _GT.objects.filter(is_default=True, is_active=True).first()
        if _dg:
            _grace = _dg.allowed_time_in_secs or 0

        att_rows = list(
            Attendance.objects.filter(
                employee_id=emp,
                attendance_date__range=(from_date, to_date),
            )
            .order_by("attendance_date")
            .values(
                "attendance_date",
                "at_work_second",
                "minimum_hour",
                "attendance_clock_in",
                "attendance_clock_out",
            )
        )
        att_by_date = {r["attendance_date"]: r for r in att_rows}

        # Approved leave date → (leave_type_name, payment)
        leave_date_info = {}
        for _lr in _LR.objects.filter(
            employee_id=emp,
            status="approved",
            start_date__lte=to_date,
            end_date__isnull=False,
            end_date__gte=from_date,
        ).select_related("leave_type_id"):
            for _d in _iter_dates(
                max(_lr.start_date, from_date), min(_lr.end_date, to_date)
            ):
                leave_date_info[_d] = (
                    _lr.leave_type_id.name,
                    _lr.leave_type_id.payment,
                )
        for _lr in _LR.objects.filter(
            employee_id=emp,
            status="approved",
            start_date__range=(from_date, to_date),
            end_date__isnull=True,
        ).select_related("leave_type_id"):
            leave_date_info[_lr.start_date] = (
                _lr.leave_type_id.name,
                _lr.leave_type_id.payment,
            )

        # Holiday date → name
        holiday_info = {}
        for _h in Holidays.objects.filter(
            start_date__lte=to_date, end_date__gte=from_date
        ):
            for _d in _iter_dates(
                max(_h.start_date, from_date), min(_h.end_date, to_date)
            ):
                holiday_info[_d] = _h.name

        # Week-off dates
        _roster = list(
            Roster.objects.filter(
                employee_id=emp, date__range=(from_date, to_date)
            ).values("date", "is_off")
        )
        if _roster:
            week_off_set = {e["date"] for e in _roster if e["is_off"]}
        else:
            _raw_cl = list(
                set(
                    get_company_leave_dates(from_date.year)
                    + get_company_leave_dates(to_date.year)
                )
            )
            week_off_set = {d for d in _raw_cl if from_date <= d <= to_date}

        # Build conflict records
        conflict_records = []
        for att_date in sorted(att_by_date):
            r = att_by_date[att_date]
            _worked = r["at_work_second"] or 0
            _min_secs = _ss(r["minimum_hour"]) if r.get("minimum_hour") else 0
            if _min_secs > 0:
                _eff = max(0, _min_secs - _grace)
                if _worked >= _eff:
                    day_type = "full"
                elif _worked >= _min_secs / 2:
                    day_type = "half"
                else:
                    day_type = "short" if r["attendance_clock_out"] else "mo"
            else:
                day_type = "full"

            if att_date in leave_date_info:
                lt_name, lt_payment = leave_date_info[att_date]
                conflict_type = "paid_leave" if lt_payment == "paid" else "unpaid_leave"
                conflict_label = lt_name
            elif att_date in holiday_info:
                conflict_type = "holiday"
                conflict_label = holiday_info[att_date]
            elif att_date in week_off_set:
                conflict_type = "week_off"
                conflict_label = ""
            else:
                continue

            _wh = _worked // 3600
            _wm = (_worked % 3600) // 60
            conflict_records.append(
                {
                    "date": att_date,
                    "day_type": day_type,
                    "clock_in": r["attendance_clock_in"],
                    "clock_out": r["attendance_clock_out"],
                    "worked_h": _wh,
                    "worked_m": _wm,
                    "conflict_type": conflict_type,
                    "conflict_label": conflict_label,
                }
            )

        context["records"] = conflict_records

        # Pre-compute summary counts for the template (no Counter in templates)
        _ct = {"paid_leave": 0, "unpaid_leave": 0, "holiday": 0, "week_off": 0}
        _at = {"full": 0, "half": 0, "short": 0, "mo": 0}
        for _cr in conflict_records:
            _ct[_cr["conflict_type"]] = _ct.get(_cr["conflict_type"], 0) + 1
            _at[_cr["day_type"]] = _at.get(_cr["day_type"], 0) + 1
        context["conflict_summary"] = {
            "total": len(conflict_records),
            "paid_leave": _ct["paid_leave"],
            "unpaid_leave": _ct["unpaid_leave"],
            "holiday": _ct["holiday"],
            "week_off": _ct["week_off"],
            "full": _at["full"],
            "half": _at["half"],
            "short": _at["short"],
            "mo": _at["mo"],
        }

    elif metric == "week_off":
        roster_entries = list(
            Roster.objects.filter(
                employee_id=emp,
                date__range=(from_date, to_date),
            )
            .order_by("date")
            .values("date", "is_off")
        )
        if roster_entries:
            _wo_dates = {e["date"] for e in roster_entries if e["is_off"]}
            context["source"] = "roster"
        else:
            _raw_cl = list(
                set(
                    get_company_leave_dates(from_date.year)
                    + get_company_leave_dates(to_date.year)
                )
            )
            _wo_dates = {d for d in _raw_cl if from_date <= d <= to_date}
            context["source"] = "company"

        # Include resolution="week_off" dates not already in the list
        for _d, _res in resolution_map.items():
            if _res == "week_off":
                _wo_dates.add(_d)
        context["records"] = [
            {"date": d, "is_regularized": d in resolution_map}
            for d in sorted(_wo_dates)
        ]

    elif metric == "holiday":
        holiday_objs = list(
            Holidays.objects.filter(
                start_date__lte=to_date,
                end_date__gte=from_date,
            ).order_by("start_date")
        )
        # Annotate each holiday with is_regularized if any date in its range was overridden.
        for h in holiday_objs:
            h_start = max(h.start_date, from_date)
            h_end = min(h.end_date, to_date)
            h.is_regularized = any(
                d in resolution_map for d in _iter_dates(h_start, h_end)
            )
        context["records"] = holiday_objs

    return render(request, "attendance/monthly_summary/detail_popover.html", context)


def _build_calendar_context(emp, from_date, to_date):
    """
    Build the full context dict for the calendar modal template.
    Shared by the calendar view and the conflict-resolve POST handler.
    Loads existing AttendanceConflictResolution records and applies them
    so that resolved days are counted in the correct bucket.
    """
    from attendance.methods.utils import strtime_seconds
    from attendance.models import AttendanceConflictResolution, GraceTime
    from leave.models import LeaveRequest

    # -- Grace time -----------------------------------------------------------
    grace_secs = 0
    default_grace = GraceTime.objects.filter(is_default=True, is_active=True).first()
    if default_grace:
        grace_secs = default_grace.allowed_time_in_secs or 0

    # -- Attendance records {date: {...}} ------------------------------------
    att_map = {
        r["attendance_date"]: r
        for r in Attendance.objects.filter(
            employee_id=emp,
            attendance_date__range=(from_date, to_date),
        ).values(
            "attendance_date",
            "attendance_clock_in",
            "attendance_clock_out",
            "at_work_second",
            "minimum_hour",
            "overtime_second",
            "attendance_overtime_approve",
        )
    }

    # -- Leave date maps ------------------------------------------------------
    paid_map = {}
    unpaid_map = {}
    qs_range = LeaveRequest.objects.filter(
        employee_id=emp,
        status="approved",
        start_date__lte=to_date,
        end_date__isnull=False,
        end_date__gte=from_date,
    ).select_related("leave_type_id")
    qs_single = LeaveRequest.objects.filter(
        employee_id=emp,
        status="approved",
        start_date__range=(from_date, to_date),
        end_date__isnull=True,
    ).select_related("leave_type_id")
    for lr in chain(qs_range, qs_single):
        s = max(lr.start_date, from_date)
        e = min(lr.end_date or lr.start_date, to_date)
        name = lr.leave_type_id.name
        for d in _iter_dates(s, e):
            if lr.leave_type_id.payment == "paid":
                paid_map[d] = name
            else:
                unpaid_map[d] = name

    # -- Holiday dates --------------------------------------------------------
    holiday_map = {}
    for h in Holidays.objects.filter(start_date__lte=to_date, end_date__gte=from_date):
        for d in _iter_dates(max(h.start_date, from_date), min(h.end_date, to_date)):
            holiday_map[d] = h.name

    # -- Week-off dates -------------------------------------------------------
    roster_entries = list(
        Roster.objects.filter(employee_id=emp, date__range=(from_date, to_date)).values(
            "date", "is_off"
        )
    )
    if roster_entries:
        week_off_dates = {e["date"] for e in roster_entries if e["is_off"]}
    else:
        raw_cl = list(
            set(
                get_company_leave_dates(from_date.year)
                + get_company_leave_dates(to_date.year)
            )
        )
        week_off_dates = {d for d in raw_cl if from_date <= d <= to_date}

    # -- Existing resolutions {date: "attendance"|"leave"} -------------------
    resolutions_map = {
        r.date: r.resolution
        for r in AttendanceConflictResolution.objects.filter(
            employee_id=emp,
            date__range=(from_date, to_date),
        )
    }

    # -- Worked / Regular / Overtime totals for this employee over the range -
    # Overtime splits into three sources: worked beyond minimum_hour on a
    # normal working day (ot_regular), any attendance on a week-off day
    # (entirely OT), and any attendance on a holiday (entirely OT). A day
    # HR has regularized away from holiday/week-off (Full Present/Half Day)
    # is treated as a normal working day instead.
    cal_worked_seconds = 0
    cal_ot_regular_seconds = cal_ot_week_off_seconds = cal_ot_holiday_seconds = 0
    for _d, _r in att_map.items():
        _wsec = _r["at_work_second"] or 0
        cal_worked_seconds += _wsec
        _regularized = resolutions_map.get(_d) in ("full_present", "half_present")
        if _d in holiday_map and not _regularized:
            cal_ot_holiday_seconds += _wsec
        elif _d in week_off_dates and not _regularized:
            cal_ot_week_off_seconds += _wsec
        else:
            cal_ot_regular_seconds += _r["overtime_second"] or 0
    cal_overtime_seconds = (
        cal_ot_regular_seconds + cal_ot_week_off_seconds + cal_ot_holiday_seconds
    )
    cal_regular_seconds = cal_worked_seconds - cal_overtime_seconds

    # -- Shift schedule for this employee (for regularized-day hours) ---------
    from base.models import EmployeeShiftSchedule as _ESS
    from employee.models import EmployeeWorkInformation as _EWI

    _CAL_DAY_NAMES = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    _wi_row = _EWI.objects.filter(employee_id=emp).values("shift_id_id").first()
    _cal_shift_pk = _wi_row["shift_id_id"] if _wi_row else None
    cal_shift_secs = {}  # {day_name: seconds}
    if _cal_shift_pk:
        for _ss in _ESS.objects.filter(shift_id=_cal_shift_pk).values(
            "day__day", "minimum_working_hour"
        ):
            if _ss["minimum_working_hour"]:
                cal_shift_secs[_ss["day__day"]] = strtime_seconds(
                    _ss["minimum_working_hour"]
                )

    # -- Per-day manual hours from calendar editor ----------------------------
    cal_daily_hours_map = {}  # {date: (hours_second, is_manually_edited)}
    for _dh in AttendanceDailyHours.objects.filter(
        employee_id=emp,
        date__range=(from_date, to_date),
    ).values("date", "hours_second", "is_manually_edited"):
        cal_daily_hours_map[_dh["date"]] = (
            _dh["hours_second"],
            _dh["is_manually_edited"],
        )

    # -- Per-day status -------------------------------------------------------
    # Each branch returns (status, detail, conflict_with, resolution_badge, is_conflict).
    # `conflict_with` drives which badge/dot is shown; `is_conflict` drives the
    # persistent amber ring — kept separate so an approved holiday/week-off
    # overtime day can still show its HO/WO badge without being rung as a
    # conflict needing attention (mirrors the table's conflict-count rule).
    def day_info(d):
        resolution = resolutions_map.get(d)

        # Direct manual override — bypasses all computed logic
        _direct = {
            "full_present": ("present", "", None, "resolved_attendance", False),
            "half_present": ("half_present", "", None, "resolved_attendance", False),
            "partial_hours": ("partial_hours", "", None, "resolved_attendance", False),
            "absent": ("absent", "", None, "resolved_attendance", False),
            "paid_leave": ("paid_leave", "", None, "resolved_leave", False),
            "unpaid_leave": ("unpaid_leave", "", None, "resolved_leave", False),
            "holiday": ("holiday", "", None, "resolved_leave", False),
            "week_off": ("week_off", "", None, "resolved_leave", False),
        }
        if resolution in _direct:
            return _direct[resolution]

        if d in att_map:
            r = att_map[d]
            worked = r["at_work_second"] or 0
            min_secs = (
                strtime_seconds(r["minimum_hour"]) if r.get("minimum_hour") else 0
            )
            clock_in = r["attendance_clock_in"]
            clock_out = r["attendance_clock_out"]

            if min_secs > 0:
                effective_min = max(0, min_secs - grace_secs)
                if worked >= effective_min:
                    att_status = "present"
                elif worked >= min_secs / 2:
                    att_status = "half_present"
                else:
                    att_status = "short" if clock_out else "absent"
            else:
                att_status = "present"

            detail = ""
            if clock_in:
                detail = str(clock_in)
                if clock_out:
                    detail += f" – {clock_out}"
            if att_status in ("half_present", "short", "absent") and min_secs > 0:
                worked_h = worked // 3600
                worked_m = (worked % 3600) // 60
                min_h = min_secs // 3600
                min_m = (min_secs % 3600) // 60
                detail += f" ({worked_h}h{worked_m:02d}m / {min_h}h{min_m:02d}m)"

            # Determine conflict type
            raw_conflict = None
            if d in paid_map:
                raw_conflict = "paid_leave"
            elif d in unpaid_map:
                raw_conflict = "unpaid_leave"
            elif d in holiday_map:
                raw_conflict = "holiday_ot"  # attendance on holiday → HO OT
            elif d in week_off_dates:
                raw_conflict = "week_off_ot"  # attendance on week-off → WO OT

            if raw_conflict in ("holiday_ot", "week_off_ot"):
                # Attendance on a holiday/week-off is normal overtime work,
                # not a data discrepancy — counts in the holiday/week_off
                # bucket, shows its HO/WO badge, but never rings as a
                # conflict (mirrors build_monthly_summary's conflict-count
                # rule, which only flags attendance overlapping leave).
                base_status = "holiday" if raw_conflict == "holiday_ot" else "week_off"
                return base_status, detail, raw_conflict, None, False

            if raw_conflict:  # paid_leave or unpaid_leave
                if resolution == "leave":
                    if d in paid_map:
                        return "paid_leave", paid_map[d], None, "resolved_leave", False
                    if d in unpaid_map:
                        return (
                            "unpaid_leave",
                            unpaid_map[d],
                            None,
                            "resolved_leave",
                            False,
                        )
                elif resolution == "attendance":
                    return att_status, detail, None, "resolved_attendance", False
                else:
                    return att_status, detail, raw_conflict, None, True

            # Overtime worked on a normal scheduled working day (not a
            # holiday/week-off — those get the HO/WO badge above instead).
            if r.get("overtime_second"):
                return att_status, detail, "regular_ot", None, False

            return att_status, detail, None, None, False

        if d in paid_map:
            return "paid_leave", paid_map[d], None, None, False
        if d in unpaid_map:
            return "unpaid_leave", unpaid_map[d], None, None, False
        if d in holiday_map:
            return "holiday", holiday_map[d], None, None, False
        if d in week_off_dates:
            return "week_off", "", None, None, False
        return "absent", "", None, None, False

    # -- Build month grid structures ------------------------------------------
    months = []
    cur = from_date.replace(day=1)
    last = to_date.replace(day=1)
    while cur <= last:
        yr, mo = cur.year, cur.month
        weeks = []
        for week in calendar.monthcalendar(yr, mo):
            cells = []
            for n in week:
                if n == 0:
                    cells.append(None)
                else:
                    d = datetime.date(yr, mo, n)
                    if d < from_date or d > to_date:
                        cells.append(
                            {
                                "day": n,
                                "date": d,
                                "status": "out_of_range",
                                "detail": "",
                                "conflict_with": None,
                                "resolution": None,
                                "is_conflict": False,
                            }
                        )
                    else:
                        status, detail, conflict_with, resolution_badge, is_conflict = (
                            day_info(d)
                        )

                        # Per-day hours computation
                        _show_hours = status in (
                            "present",
                            "half_present",
                            "short",
                            "partial_hours",
                        )
                        _cell_sec = 0
                        _cell_edited = False
                        if _show_hours:
                            _manual = cal_daily_hours_map.get(d)
                            if _manual:
                                _cell_sec, _cell_edited = _manual
                            else:
                                _res = resolutions_map.get(d)
                                if _res in ("full_present", "half_present"):
                                    _dn = _CAL_DAY_NAMES[d.weekday()]
                                    _full = cal_shift_secs.get(_dn, 0) or 28800
                                    _cell_sec = int(
                                        _full * (1.0 if _res == "full_present" else 0.5)
                                    )
                                elif d in att_map:
                                    _cell_sec = att_map[d].get("at_work_second") or 0
                        _ch, _cm = _cell_sec // 3600, (_cell_sec % 3600) // 60
                        _hlabel = f"{_ch}h {_cm:02d}m" if _cell_sec > 0 else ""

                        cells.append(
                            {
                                "day": n,
                                "date": d,
                                "status": status,
                                "detail": detail,
                                "conflict_with": conflict_with,
                                "resolution": resolution_badge,
                                "is_conflict": is_conflict,
                                "hours_second": _cell_sec,
                                "hours_label": _hlabel,
                                "show_hours": _show_hours,
                                "is_hours_edited": _cell_edited,
                            }
                        )
            weeks.append(cells)
        months.append({"label": cur.strftime("%B %Y"), "weeks": weeks})
        mo += 1
        if mo > 12:
            mo, yr = 1, yr + 1
        cur = datetime.date(yr, mo, 1)

    # -- Summary counts -------------------------------------------------------
    cal_summary = {
        "full_present": 0,
        "half_present": 0,
        "short": 0,
        "absent": 0,
        "paid_leave": 0,
        "unpaid_leave": 0,
        "week_off": 0,
        "holiday": 0,
        "conflict": 0,
        "worked_label": _secs_to_label(cal_worked_seconds),
        "regular_label": _secs_to_label(cal_regular_seconds),
        "overtime_label": _secs_to_label(cal_overtime_seconds),
        "ot_regular_seconds": cal_ot_regular_seconds,
        "ot_week_off_seconds": cal_ot_week_off_seconds,
        "ot_holiday_seconds": cal_ot_holiday_seconds,
        "ot_regular_label": _secs_to_label(cal_ot_regular_seconds),
        "ot_week_off_label": _secs_to_label(cal_ot_week_off_seconds),
        "ot_holiday_label": _secs_to_label(cal_ot_holiday_seconds),
    }
    for _m in months:
        for _w in _m["weeks"]:
            for _c in _w:
                if _c is None or _c["status"] == "out_of_range":
                    continue
                _s = _c["status"]
                if _s == "present":
                    cal_summary["full_present"] += 1
                elif _s == "half_present":
                    cal_summary["half_present"] += 1
                elif _s in cal_summary:
                    cal_summary[_s] += 1
                if _c.get("conflict_with") in ("paid_leave", "unpaid_leave"):
                    cal_summary["conflict"] += 1

    total_days = (to_date - from_date).days + 1

    return {
        "employee": emp,
        "from_date": from_date,
        "to_date": to_date,
        "months": months,
        "cal_summary": cal_summary,
        "total_days": total_days,
    }


@login_required
@hx_request_required
def attendance_monthly_summary_calendar(request):
    """
    HTMX calendar modal — full month-by-month view of every day's status
    for a single employee over the selected date range.
    """
    emp_id = request.GET.get("employee_id")
    from_date = _parse_date(
        request.GET.get("from_date"), datetime.date.today().replace(day=1)
    )
    to_date = _parse_date(request.GET.get("to_date"), datetime.date.today())

    try:
        emp = Employee.objects.get(pk=emp_id)
    except Employee.DoesNotExist:
        return HttpResponse("<p style='padding:20px;'>Employee not found.</p>")

    context = _build_calendar_context(emp, from_date, to_date)
    return render(request, "attendance/monthly_summary/calendar_modal.html", context)


@login_required
@manager_can_enter("attendance.change_attendance")
@hx_request_required
def attendance_monthly_summary_conflict_resolve(request):
    """
    HTMX view for resolving attendance/leave conflicts in the calendar modal.
    GET  → renders the conflict resolution panel for a specific day.
    POST → saves the HR resolution and re-renders the full calendar.
    """
    from attendance.methods.utils import strtime_seconds as _ss
    from attendance.models import (
        AttendanceConflictResolution,
        AttendanceValidationCondition,
    )
    from attendance.models import GraceTime as _GT
    from leave.models import LeaveRequest

    emp_id = request.POST.get("employee_id") or request.GET.get("employee_id")
    date_str = request.POST.get("date") or request.GET.get("date")
    from_date = _parse_date(
        request.POST.get("from_date") or request.GET.get("from_date"),
        datetime.date.today().replace(day=1),
    )
    to_date = _parse_date(
        request.POST.get("to_date") or request.GET.get("to_date"), datetime.date.today()
    )
    date = _parse_date(date_str, None)

    try:
        emp = Employee.objects.get(pk=emp_id)
    except Employee.DoesNotExist:
        return HttpResponse(
            "<p style='padding:12px;color:#6c757d;'>Employee not found.</p>"
        )

    if date is None:
        return HttpResponse("<p style='padding:12px;color:#6c757d;'>Invalid date.</p>")

    if request.method == "POST":
        resolution = request.POST.get("resolution")
        conflict_type = request.POST.get("conflict_type", "")
        _valid = {
            "full_present",
            "half_present",
            "partial_hours",
            "absent",
            "paid_leave",
            "unpaid_leave",
            "holiday",
            "week_off",
            "approve_ot",
            "attendance",
            "leave",  # legacy kept for existing records
        }
        if resolution in _valid:
            AttendanceConflictResolution.objects.update_or_create(
                employee_id=emp,
                date=date,
                defaults={"resolution": resolution, "conflict_type": conflict_type},
            )
            if resolution == "approve_ot":
                # Holiday/week-off work isn't counted as a conflict (it's
                # normal overtime, not a data discrepancy), but HR may still
                # want to formally approve the hours for downstream use
                # (payroll, Hour Account) — set the real flag directly
                # rather than just recording an override local to this page.
                Attendance.objects.filter(employee_id=emp, attendance_date=date).update(
                    attendance_overtime_approve=True
                )
        elif resolution == "clear":
            _obj = AttendanceConflictResolution.objects.filter(
                employee_id=emp, date=date
            ).first()
            if _obj:
                if _obj.resolution == "approve_ot":
                    Attendance.objects.filter(
                        employee_id=emp, attendance_date=date
                    ).update(attendance_overtime_approve=False)
                _obj.delete()

        # Re-render the full calendar so counts and dots update immediately
        context = _build_calendar_context(emp, from_date, to_date)
        return render(
            request, "attendance/monthly_summary/calendar_modal.html", context
        )

    # ── GET: build resolve panel context (handles all day types) ────────────
    att_row = (
        Attendance.objects.filter(employee_id=emp, attendance_date=date)
        .values(
            "attendance_clock_in",
            "attendance_clock_out",
            "at_work_second",
            "minimum_hour",
            "overtime_second",
            "attendance_overtime_approve",
        )
        .first()
    )
    att_ot_approved = bool(att_row and att_row.get("attendance_overtime_approve"))

    _grace = 0
    _dg = _GT.objects.filter(is_default=True, is_active=True).first()
    if _dg:
        _grace = _dg.allowed_time_in_secs or 0

    day_type = None
    worked_h = 0
    worked_m = 0
    regular_h = 0
    regular_m = 0
    overtime_h = 0
    overtime_m = 0
    clock_in = None
    clock_out = None
    _shift_min_secs = 0
    _att_ot_sec = 0

    if att_row:
        _worked = att_row["at_work_second"] or 0
        _min_secs = _ss(att_row["minimum_hour"]) if att_row.get("minimum_hour") else 0
        _shift_min_secs = _min_secs
        _att_ot_sec = att_row.get("overtime_second") or 0
        if _min_secs > 0:
            _eff = max(0, _min_secs - _grace)
            if _worked >= _eff:
                day_type = "full"
            elif _worked >= _min_secs / 2:
                day_type = "half"
            else:
                day_type = "short" if att_row["attendance_clock_out"] else "mo"
        else:
            day_type = "full"
        worked_h = _worked // 3600
        worked_m = (_worked % 3600) // 60
        _reg_sec = min(_worked, _min_secs) if _min_secs > 0 else _worked
        _ot_sec = max(0, _worked - _min_secs) if _min_secs > 0 else 0
        regular_h = _reg_sec // 3600
        regular_m = (_reg_sec % 3600) // 60
        overtime_h = _ot_sec // 3600
        overtime_m = (_ot_sec % 3600) // 60
        clock_in = att_row["attendance_clock_in"]
        clock_out = att_row["attendance_clock_out"]

    # Determine what else is on this day (leave, holiday, week-off)
    conflict_type = ""
    conflict_label = ""
    for _lr in LeaveRequest.objects.filter(
        employee_id=emp,
        status="approved",
        start_date__lte=date,
        end_date__isnull=False,
        end_date__gte=date,
    ).select_related("leave_type_id"):
        conflict_type = (
            "paid_leave" if _lr.leave_type_id.payment == "paid" else "unpaid_leave"
        )
        conflict_label = _lr.leave_type_id.name
        break
    if not conflict_type:
        for _lr in LeaveRequest.objects.filter(
            employee_id=emp,
            status="approved",
            start_date=date,
            end_date__isnull=True,
        ).select_related("leave_type_id"):
            conflict_type = (
                "paid_leave" if _lr.leave_type_id.payment == "paid" else "unpaid_leave"
            )
            conflict_label = _lr.leave_type_id.name
            break
    if not conflict_type:
        _h = Holidays.objects.filter(start_date__lte=date, end_date__gte=date).first()
        if _h:
            # attendance on holiday = OT; no attendance = just a holiday
            conflict_type = "holiday_ot" if att_row else "holiday"
            conflict_label = _h.name
    if not conflict_type:
        _roster = Roster.objects.filter(employee_id=emp, date=date, is_off=True).first()
        if _roster:
            conflict_type = "week_off_ot" if att_row else "week_off"
        else:
            _raw_cl = list(set(get_company_leave_dates(date.year)))
            if date in _raw_cl:
                conflict_type = "week_off_ot" if att_row else "week_off"

    # Overall day status for display purposes — computed independently of
    # any AttendanceConflictResolution, so it always reflects the "natural"
    # (pre-override) status. Used as the "from" side of the from → to
    # transition shown when a day has been regularized.
    if att_row:
        day_status = day_type
    elif conflict_type in ("paid_leave", "unpaid_leave"):
        day_status = conflict_type
    elif conflict_type == "holiday":
        day_status = "holiday"
    elif conflict_type == "week_off":
        day_status = "week_off"
    elif date.weekday() >= 5:
        day_status = "weekend"
    else:
        day_status = "absent"

    _STATUS_LABELS = {
        "full": _("Full Present"),
        "full_present": _("Full Present"),
        "half": _("Half Day"),
        "half_present": _("Half Day"),
        "short": _("Short Hours"),
        "mo": _("Missing Clock-out"),
        "paid_leave": _("Paid Leave"),
        "unpaid_leave": _("Unpaid Leave"),
        "holiday": _("Holiday"),
        "week_off": _("Week Off"),
        "weekend": _("Weekend"),
        "absent": _("Absent"),
        "partial_hours": _("Partial Hours"),
        "approve_ot": _("Overtime Approved"),
        "attendance": _("Attendance"),
        "leave": _("Leave / Holiday"),
    }
    # (background, text) pill colors — shared between the "from" (natural)
    # and "to" (override) sides of the "Changed: X → Y" banner.
    _STATUS_PILL_COLORS = {
        "full": ("#d1fae5", "#065f46"),
        "full_present": ("#d1fae5", "#065f46"),
        "half": ("#fef9c3", "#854d0e"),
        "half_present": ("#fef9c3", "#854d0e"),
        "short": ("#ede9fe", "#3730a3"),
        "mo": ("#fee2e2", "#991b1b"),
        "absent": ("#fee2e2", "#991b1b"),
        "paid_leave": ("#dbeafe", "#1e40af"),
        "unpaid_leave": ("#ffedd5", "#9a3412"),
        "holiday": ("#ccfbf1", "#134e4a"),
        "week_off": ("#ede9fe", "#4c1d95"),
        "weekend": ("#f1f5f9", "#64748b"),
        "partial_hours": ("#ecfeff", "#0e7490"),
        "approve_ot": ("#ffedd5", "#92400e"),
        "attendance": ("#f1f5f9", "#475569"),
        "leave": ("#f1f5f9", "#475569"),
    }

    natural_status_label = _STATUS_LABELS.get(day_status, day_status)
    natural_status_bg, natural_status_fg = _STATUS_PILL_COLORS.get(
        day_status, ("#f1f5f9", "#475569")
    )

    existing = (
        AttendanceConflictResolution.objects.filter(employee_id=emp, date=date)
        .select_related("modified_by", "created_by")
        .first()
    )

    # -- Per-day hours for the panel ------------------------------------------
    _daily_obj = (
        AttendanceDailyHours.objects.filter(employee_id=emp, date=date)
        .select_related("modified_by")
        .first()
    )
    if _daily_obj and _daily_obj.is_manually_edited:
        panel_hours_sec = _daily_obj.hours_second
        panel_is_edited = True
    else:
        if att_row:
            panel_hours_sec = att_row.get("at_work_second") or 0
        elif existing and existing.resolution in ("full_present", "half_present"):
            from attendance.methods.utils import strtime_seconds as _ss2
            from base.models import EmployeeShiftSchedule as _ESS
            from employee.models import EmployeeWorkInformation as _EWI2

            _DAY_NAMES_P = [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ]
            _wi2 = _EWI2.objects.filter(employee_id=emp).values("shift_id_id").first()
            _shift2 = _wi2["shift_id_id"] if _wi2 else None
            _full2 = 28800
            if _shift2:
                _day_n = _DAY_NAMES_P[date.weekday()]
                _ss2r = (
                    _ESS.objects.filter(shift_id=_shift2, day__day=_day_n)
                    .values("minimum_working_hour")
                    .first()
                )
                if _ss2r and _ss2r["minimum_working_hour"]:
                    _full2 = _ss2(_ss2r["minimum_working_hour"])
            _val2 = 1.0 if existing.resolution == "full_present" else 0.5
            panel_hours_sec = int(_full2 * _val2)
        else:
            panel_hours_sec = 0
        panel_is_edited = False

    _ph, _pm = panel_hours_sec // 3600, (panel_hours_sec % 3600) // 60
    panel_hours_label = f"{_ph}h {_pm:02d}m"
    panel_hours_input = f"{_ph}:{_pm:02d}"

    resolution_value = existing.resolution if existing else None
    if resolution_value == "partial_hours":
        override_status_label = f"{_('Partial Hours')} ({panel_hours_label})"
    else:
        override_status_label = _STATUS_LABELS.get(resolution_value, resolution_value)
    override_status_bg, override_status_fg = _STATUS_PILL_COLORS.get(
        resolution_value, ("#f1f5f9", "#475569")
    )

    # OT display formula:
    #   effective_min = shift minimum, or 8h (28800s) when no shift configured
    #   Normal day  : OT = min(max(0, total − eff_min), cutoff)
    #   Holiday/WO  : all worked = OT (reg = 0), capped at eff_min + cutoff
    _cond = AttendanceValidationCondition.objects.first()
    _ot_cutoff_sec = (
        _ss(_cond.overtime_cutoff) if _cond and _cond.overtime_cutoff else 0
    )
    _effective_min = _shift_min_secs if _shift_min_secs > 0 else 28800  # 8h default
    # A holiday/week-off day that HR has regularized (Full Present/Half Day)
    # is no longer treated as 100% overtime — it gets the normal
    # regular/OT split, same as build_monthly_summary and the calendar totals.
    _regularized_day = existing is not None and existing.resolution in (
        "full_present",
        "half_present",
    )
    _is_ot_day = (
        conflict_type in ("holiday_ot", "week_off_ot", "holiday", "week_off")
        and not _regularized_day
    )
    worked_h = panel_hours_sec // 3600
    worked_m = (panel_hours_sec % 3600) // 60
    if _is_ot_day:
        # Week-off / holiday: 100% OT, cap = regular_threshold + cutoff
        _max_ot = (
            (_effective_min + _ot_cutoff_sec) if _ot_cutoff_sec > 0 else panel_hours_sec
        )
        _ot_sec = min(panel_hours_sec, _max_ot)
        _reg_sec = 0
    else:
        # Reg is anchored to shift min (not derived from OT) so excess renders correctly
        # when total > min + cutoff (e.g. 14h worked, 7h min, 5h cap → Reg 7 + OT 5 + ▿ 2)
        _reg_sec = min(panel_hours_sec, _effective_min)
        _potential_ot = max(0, panel_hours_sec - _effective_min)
        _ot_sec = (
            min(_potential_ot, _ot_cutoff_sec) if _ot_cutoff_sec > 0 else _potential_ot
        )
    _excess_sec = max(0, panel_hours_sec - _reg_sec - _ot_sec)
    regular_h = _reg_sec // 3600
    regular_m = (_reg_sec % 3600) // 60
    overtime_h = _ot_sec // 3600
    overtime_m = (_ot_sec % 3600) // 60
    excess_h = _excess_sec // 3600
    excess_m = (_excess_sec % 3600) // 60

    context = {
        "employee": emp,
        "date": date,
        "from_date": from_date,
        "to_date": to_date,
        "att_row": att_row,
        "day_type": day_type,
        "day_status": day_status,
        "natural_status_label": natural_status_label,
        "natural_status_bg": natural_status_bg,
        "natural_status_fg": natural_status_fg,
        "override_status_label": override_status_label,
        "override_status_bg": override_status_bg,
        "override_status_fg": override_status_fg,
        "worked_h": worked_h,
        "worked_m": worked_m,
        "regular_h": regular_h,
        "regular_m": regular_m,
        "overtime_h": overtime_h,
        "overtime_m": overtime_m,
        "clock_in": clock_in,
        "clock_out": clock_out,
        "conflict_type": conflict_type,
        "conflict_label": conflict_label,
        "existing_resolution": existing.resolution if existing else None,
        "existing_obj": existing,
        "panel_hours_sec": panel_hours_sec,
        "panel_hours_label": panel_hours_label,
        "panel_hours_input": panel_hours_input,
        "panel_is_edited": panel_is_edited,
        "panel_daily_obj": _daily_obj,
        "shift_min_secs": _shift_min_secs,
        "shift_min_h": _shift_min_secs // 3600,
        "shift_min_m": (_shift_min_secs % 3600) // 60,
        "att_ot_sec": _att_ot_sec,
        "att_ot_approved": att_ot_approved,
        "effective_min_secs": _effective_min,
        "ot_cutoff_sec": _ot_cutoff_sec,
        "is_ot_day": _is_ot_day,
        "excess_h": excess_h,
        "excess_m": excess_m,
        # OT rules info
        "ot_rule_reg_h": _effective_min // 3600,
        "ot_rule_reg_m": (_effective_min % 3600) // 60,
        "ot_rule_cap_h": _ot_cutoff_sec // 3600 if _ot_cutoff_sec else None,
        "ot_rule_cap_m": (_ot_cutoff_sec % 3600) // 60 if _ot_cutoff_sec else None,
        "ot_rule_min_approve_h": (
            (_ss(_cond.minimum_overtime_to_approve) // 3600)
            if _cond and _cond.minimum_overtime_to_approve
            else None
        ),
        "ot_rule_min_approve_m": (
            ((_ss(_cond.minimum_overtime_to_approve) % 3600) // 60)
            if _cond and _cond.minimum_overtime_to_approve
            else None
        ),
        "ot_rule_auto_approve": bool(_cond and _cond.auto_approve_ot),
        "ot_rule_is_ot_day": _is_ot_day,
        "ot_rule_holiday_cap_h": (
            ((_effective_min + _ot_cutoff_sec) // 3600) if _ot_cutoff_sec else None
        ),
        "ot_rule_holiday_cap_m": (
            (((_effective_min + _ot_cutoff_sec) % 3600) // 60)
            if _ot_cutoff_sec
            else None
        ),
    }
    return render(
        request, "attendance/monthly_summary/conflict_resolve_panel.html", context
    )


@login_required
@manager_can_enter("attendance.change_attendance")
def attendance_monthly_summary_bulk_override(request):
    """
    Bulk-apply an attendance override for multiple employees over a date range.
    POST only.  Accepts:
        employee_ids  — repeated POST values, one per selected employee pk
        from_date     — start of range (YYYY-MM-DD)
        to_date       — end of range   (YYYY-MM-DD)
        resolution    — one of the 7 direct-override choices
    Returns JSON {success, count, changed_pks} or {error}.
    Dates that already carry the same resolution are silently skipped.
    """
    from attendance.models import AttendanceConflictResolution

    if request.method != "POST":
        return HttpResponse(status=405)

    emp_ids = request.POST.getlist("employee_ids")
    from_date = _parse_date(request.POST.get("from_date"), None)
    to_date = _parse_date(request.POST.get("to_date"), None)
    resolution = request.POST.get("resolution", "")

    _valid = {
        "full_present",
        "half_present",
        "partial_hours",
        "absent",
        "paid_leave",
        "unpaid_leave",
        "holiday",
        "week_off",
    }

    if not emp_ids or not from_date or not to_date or resolution not in _valid:
        return JsonResponse({"error": "Invalid parameters"}, status=400)

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    employees = list(Employee.objects.filter(pk__in=emp_ids))
    dates = list(_iter_dates(from_date, to_date))

    # Batch-fetch existing resolutions to skip same-value records (avoids N+1)
    existing_map = {}  # {(emp_pk, date): (pk, resolution)}
    for r in AttendanceConflictResolution.objects.filter(
        employee_id__in=employees,
        date__range=(from_date, to_date),
    ).values("pk", "employee_id_id", "date", "resolution"):
        existing_map[(r["employee_id_id"], r["date"])] = (r["pk"], r["resolution"])

    changed_pks = []
    for emp in employees:
        for d in dates:
            ex = existing_map.get((emp.pk, d))
            if ex and ex[1] == resolution:
                continue  # already the same value — skip
            obj, _ = AttendanceConflictResolution.objects.update_or_create(
                employee_id=emp,
                date=d,
                defaults={"resolution": resolution, "conflict_type": "bulk"},
            )
            changed_pks.append(obj.pk)

    return JsonResponse(
        {"success": True, "count": len(changed_pks), "changed_pks": changed_pks}
    )


@login_required
@manager_can_enter("attendance.change_attendance")
def attendance_monthly_summary_undo_bulk(request):
    """
    Undo a previous bulk override by deleting the specified ACR records,
    but ONLY those that were last modified (or created) by the current user.
    POST only.  Accepts:
        pks — repeated POST values, the PKs returned by bulk_override
    Returns JSON {success, count}.
    """
    from django.db.models import Q

    from attendance.models import AttendanceConflictResolution

    if request.method != "POST":
        return HttpResponse(status=405)

    pks = request.POST.getlist("pks")
    if not pks:
        return JsonResponse({"error": "No records specified"}, status=400)

    # Security: only touch records that the current user created or last modified
    deleted_count, _ = (
        AttendanceConflictResolution.objects.filter(
            pk__in=pks,
        )
        .filter(Q(modified_by=request.user) | Q(created_by=request.user))
        .delete()
    )

    return JsonResponse({"success": True, "count": deleted_count})


@login_required
@manager_can_enter("attendance.change_attendance")
def attendance_monthly_summary_daily_hours_edit(request):
    """
    Per-date hours editing — used both from calendar cells and the conflict panel.
    GET  — returns the edit input.
    POST — saves and returns the display cell.

    Pass `panel=1` (GET or POST) to use the larger conflict-panel template
    (crp_hours.html) instead of the compact calendar-cell template (cal_day_hours.html).
    """
    emp_id = request.POST.get("employee_id") or request.GET.get("employee_id")
    date_str = request.POST.get("date") or request.GET.get("date")
    from_date = _parse_date(
        request.POST.get("from_date") or request.GET.get("from_date"),
        datetime.date.today(),
    )
    to_date = _parse_date(
        request.POST.get("to_date") or request.GET.get("to_date"), datetime.date.today()
    )
    date = _parse_date(date_str, None)

    try:
        emp = Employee.objects.get(pk=emp_id)
    except Employee.DoesNotExist:
        return HttpResponse("—")

    if date is None:
        return HttpResponse("—")

    is_panel = bool(request.POST.get("panel") or request.GET.get("panel"))
    _tmpl = (
        "attendance/monthly_summary/crp_hours.html"
        if is_panel
        else "attendance/monthly_summary/cal_day_hours.html"
    )
    existing = (
        AttendanceDailyHours.objects.filter(employee_id=emp, date=date)
        .select_related("modified_by")
        .first()
    )

    if request.method == "POST":
        raw = request.POST.get("hours", "").strip()
        try:
            if ":" in raw:
                parts = raw.split(":")
                total_sec = int(parts[0]) * 3600 + int(parts[1]) * 60
            else:
                total_sec = int(float(raw) * 3600)
            total_sec = max(0, total_sec)
        except (ValueError, IndexError):
            total_sec = existing.hours_second if existing else 0

        if existing:
            existing.hours_second = total_sec
            existing.is_manually_edited = True
            # include modified_at so auto_now triggers even with update_fields
            existing.save(
                update_fields=["hours_second", "is_manually_edited", "modified_at"]
            )
            saved_obj = existing
        else:
            saved_obj = AttendanceDailyHours.objects.create(
                employee_id=emp,
                date=date,
                hours_second=total_sec,
                is_manually_edited=True,
            )
        # re-fetch with modifier for display
        saved_obj = (
            AttendanceDailyHours.objects.filter(pk=saved_obj.pk)
            .select_related("modified_by")
            .first()
        )

        # Sync the underlying Attendance record so My Attendances stays consistent
        from attendance.methods.utils import format_time as _fmt

        _att = Attendance.objects.filter(employee_id=emp, attendance_date=date).first()
        if _att:
            _att.attendance_worked_hour = _fmt(total_sec)
            _att.at_work_second = total_sec
            _att.update_attendance_overtime()
            _att.handle_overtime_conditions()
            _att.save(
                update_fields=[
                    "attendance_worked_hour",
                    "at_work_second",
                    "attendance_overtime",
                    "overtime_second",
                    "attendance_overtime_approve",
                ]
            )

        h, m = total_sec // 3600, (total_sec % 3600) // 60
        context = {
            "employee": emp,
            "date": date,
            "from_date": from_date,
            "to_date": to_date,
            "hours_label": f"{h}h {m:02d}m",
            "hours_second": total_sec,
            "computed_sec": total_sec,
            "panel": is_panel,
            "is_hours_edited": True,
            "edit_mode": False,
            "daily_obj": saved_obj,
        }
        return render(request, _tmpl, context)

    # GET with cancel=1 → return display mode
    computed_sec = int(request.GET.get("computed_sec") or 0)
    if request.GET.get("cancel"):
        if existing:
            display_sec = existing.hours_second
            is_edited = existing.is_manually_edited
        else:
            display_sec = computed_sec
            is_edited = False
        h, m = display_sec // 3600, (display_sec % 3600) // 60
        context = {
            "employee": emp,
            "date": date,
            "from_date": from_date,
            "to_date": to_date,
            "hours_label": f"{h}h {m:02d}m",
            "hours_second": display_sec,
            "computed_sec": computed_sec,
            "panel": is_panel,
            "is_hours_edited": is_edited,
            "edit_mode": False,
            "daily_obj": existing,
        }
        return render(request, _tmpl, context)

    # GET — show edit input, pre-filling with manual value or computed fallback
    if existing and existing.is_manually_edited:
        display_sec = existing.hours_second
    else:
        display_sec = computed_sec
    h, m = display_sec // 3600, (display_sec % 3600) // 60
    context = {
        "employee": emp,
        "date": date,
        "from_date": from_date,
        "to_date": to_date,
        "hours_input": f"{h}:{m:02d}",
        "hours_label": f"{h}h {m:02d}m",
        "hours_second": display_sec,
        "computed_sec": computed_sec,
        "panel": is_panel,
        "is_hours_edited": existing.is_manually_edited if existing else False,
        "edit_mode": True,
        "daily_obj": existing,
    }
    return render(request, _tmpl, context)
