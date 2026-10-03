"""
Regularising a month by stating its totals.

Resolving conflicts day by day is the right tool for a handful. It is the wrong
one at month end, where what HR actually knows is "this person worked nineteen
days, not three" — a statement about the month, not about any particular date.
Reconstructing that into per-day decisions is work nobody wants to do, and the
per-day record it would produce is invented.

So the sheet is one row per employee, carrying the counted figures. Correct the
numbers, upload, and those are the month's totals. See
``AttendanceSummaryOverride`` for what a stated month does to the conflicts it
was written to answer.
"""

import calendar
import datetime

import pandas as pd
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _

from attendance.models import AttendanceSummaryOverride
from attendance.views.summary import _parse_date, build_monthly_summary
from base.methods import filtersubordinatesemployeemodel
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla.decorators import login_required, manager_can_enter

# Sheet column -> model field. Only these four are editable: week off and
# holiday come from the roster and the company calendar, not from anybody's
# judgement, and letting them be typed over would put the summary at odds with
# the calendar every other screen reads.
COUNT_COLUMNS = {
    "Present": "present",
    "Paid Leave": "paid_leave",
    "Unpaid Leave": "unpaid_leave",
    "Absent": "absent",
}

# Total sits immediately after the six columns it sums, not at the end: a
# total three columns away from its own addends is one nobody checks.
DAY_COLUMNS = [*COUNT_COLUMNS, "Week Off", "Holiday"]

COLUMNS = [
    "Badge ID",
    "Employee",
    *DAY_COLUMNS,
    "Total",
    "Working Days",
    "Conflicts",
    "Reason",
]

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _scope(request, source=None):
    """
    The employees and period a download covers.

    Same rules as the export beside it: explicitly ticked rows win over the
    filter bar, and filtersubordinatesemployeemodel still applies, so a manager
    cannot reach outside their own people by crafting the request.
    """
    source = request.GET if source is None else source
    today = datetime.date.today()
    from_date = _parse_date(source.get("from_date"), today.replace(day=1))
    to_date = _parse_date(
        source.get("to_date"),
        today.replace(day=calendar.monthrange(today.year, today.month)[1]),
    )
    if from_date > to_date:
        from_date, to_date = to_date, from_date

    selected = source.getlist("employee_ids")
    employees = (
        Employee.objects.filter(pk__in=selected)
        if selected
        else EmployeeFilter(request.GET).qs
    )
    employees = filtersubordinatesemployeemodel(
        request, employees, "attendance.view_attendance"
    )
    return employees, from_date, to_date


@login_required
@manager_can_enter("attendance.change_attendance")
def regularisation_template(request):
    """
    The month's summary as a sheet, pre-filled with what was counted.

    Pre-filled rather than empty because the counted figures are the starting
    point: most of them are right, and the ones that are not are far easier to
    spot beside the rest than to reconstruct from nothing.
    """
    employees, from_date, to_date = _scope(request)
    period_days = (to_date - from_date).days + 1
    rows, _total_working, _totals = build_monthly_summary(from_date, to_date, employees)

    sheet = pd.DataFrame(
        [
            {
                "Badge ID": row["employee"].badge_id or "",
                "Employee": str(row["employee"]),
                "Present": row["present"],
                "Paid Leave": row["paid_leave"],
                "Unpaid Leave": row["unpaid_leave"],
                "Absent": row["absent"],
                "Week Off": row["week_off"],
                "Holiday": row["holiday"],
                # Written as a live formula below, not as a number: a total
                # that does not move when the counts are edited is worse than
                # no total, because it looks right.
                "Total": None,
                "Working Days": row["working_days"],
                "Conflicts": row["unresolved_conflicts"],
                "Reason": "",
            }
            for row in rows
        ],
        columns=COLUMNS,
    )

    notes = pd.DataFrame(
        {
            "Column": [*COUNT_COLUMNS, "Week Off", "Holiday", "Total", "Conflicts"],
            "Editable": ["yes"] * len(COUNT_COLUMNS) + ["no", "no", "no", "no"],
            "Notes": [
                str(_("Days present. Half days count as 0.5.")),
                str(_("Days of approved paid leave.")),
                str(_("Days of approved unpaid leave.")),
                str(_("Working days with nothing recorded.")),
                str(_("From the roster. Change the roster, not this.")),
                str(_("From the company calendar.")),
                str(
                    _(
                        "Adds up the day columns as you type. Every day of "
                        "the period belongs in one of those columns, so this "
                        "should equal the days in the period. Anything else "
                        "turns red -- the upload refuses it too."
                    )
                ),
                str(
                    _(
                        "Days with both attendance and leave. Stating the "
                        "totals settles them."
                    )
                ),
            ],
        }
    )

    response = HttpResponse(content_type=XLSX)
    name = f"attendance_summary_{from_date:%Y%m%d}_{to_date:%Y%m%d}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{name}"'

    with pd.ExcelWriter(response, engine="xlsxwriter") as writer:
        sheet.to_excel(writer, sheet_name="Summary", index=False)
        # What each column means and whether it is read back, carried in the
        # file rather than in documentation nobody opens beside a spreadsheet.
        notes.to_excel(writer, sheet_name="How to fill this in", index=False)
        _decorate(writer, len(sheet), period_days)
    return response


def _decorate(writer, row_count, period_days):
    """
    Make the sheet check itself: a live Total, and red where it cannot be right.

    The arithmetic has to happen in the spreadsheet rather than on the server,
    because the numbers are edited in the spreadsheet. A total computed at
    download time is stale the moment anybody types, and a stale total is worse
    than none: it looks authoritative.
    """
    book = writer.book
    worksheet = writer.sheets["Summary"]

    first = COLUMNS.index(DAY_COLUMNS[0])
    last = COLUMNS.index(DAY_COLUMNS[-1])
    total = COLUMNS.index("Total")

    def letter(index):
        return chr(ord("A") + index)

    for row in range(1, row_count + 1):
        excel_row = row + 1  # 1-indexed, and row 1 is the header
        worksheet.write_formula(
            row,
            total,
            f"=SUM({letter(first)}{excel_row}:{letter(last)}{excel_row})",
        )

    if not row_count:
        return

    # Not "greater than": the six day columns between them classify every day
    # of the period, so a complete month totals exactly the period length.
    # Over it is impossible; under it means days nobody has accounted for, and
    # payroll would compute from a month with holes in it. Both are wrong, and
    # only flagging the first left the second looking fine.
    span = f"{letter(total)}2:{letter(total)}{row_count + 1}"
    wrong = book.add_format(
        {"bg_color": "#FEE2E2", "font_color": "#991B1B", "bold": True}
    )
    worksheet.conditional_format(
        span,
        {
            "type": "cell",
            "criteria": "not equal to",
            "value": period_days,
            "format": wrong,
        },
    )

    # The limit, attached to the header rather than written into a spare cell
    # off to the right -- that one spilled past the visible area and was the
    # one piece of text explaining why a cell had turned red.
    worksheet.write_comment(
        0,
        total,
        "Adds up the day columns as you type. "
        f"This period has {period_days} days, and every day of it belongs in "
        f"one of those columns -- so the total should be exactly {period_days}. "
        "Anything else turns red. The upload refuses it too.",
        {"width": 260, "height": 110},
    )

    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, row_count, len(COLUMNS) - 1)
    worksheet.set_column(0, 0, 12)
    worksheet.set_column(1, 1, 28)
    worksheet.set_column(2, len(COLUMNS) - 2, 12)
    worksheet.set_column(len(COLUMNS) - 1, len(COLUMNS) - 1, 30)


def _safe_next(request):
    """Where to return to, validated. An unchecked ``next`` is an open redirect."""
    target = request.POST.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse("attendance-monthly-summary")


def _read(upload):
    """The uploaded sheet, or None if it could not be parsed."""
    try:
        if upload.name.lower().endswith(".csv"):
            return pd.read_csv(upload)
        return pd.read_excel(upload)
    except Exception:  # noqa: BLE001 - reported to whoever uploaded it
        return None


def _text(value):
    """
    A cell as a stripped string, with pandas' blanks treated as blank.

    ``float("nan") or ""`` evaluates to nan, not "" — NaN is truthy — so an
    empty Badge ID cell arrives as the literal string "nan" and is then looked
    up as if somebody's badge were spelled that way.
    """
    if value is None or (isinstance(value, float) and value != value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _count(value):
    """
    A count cell as a number, ``None`` for "leave this one as counted", or
    ``False`` for something that is neither — so a deliberate blank can be told
    apart from a typo.
    """
    if not _text(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number if number >= 0 else False


def _check(record, by_badge, period_days, computed):
    """
    One row: the totals it states, or why it cannot be applied.

    Returns ``(employee, counts, note, None)`` or ``(None, None, None, reason)``.
    A row with every count left blank is neither — nothing was stated about that
    employee, which is the normal content of a partly-filled sheet.

    ``period_days`` bounds the arithmetic and ``computed`` carries what the
    engine counted, keyed by employee pk. The red in the spreadsheet is a hint,
    and a hint does not stop anybody uploading the file anyway — so the same
    rule is enforced here, where it actually holds.
    """
    badge = _text(record.get("Badge ID"))
    employee = by_badge.get(badge)

    counts, unreadable = {}, []
    for column, field in COUNT_COLUMNS.items():
        value = _count(record.get(column))
        if value is False:
            unreadable.append(column)
        elif value is not None:
            counts[field] = value

    if not counts and not unreadable:
        return None, None, None, None

    if employee is None:
        return (
            None,
            None,
            None,
            _("No employee with badge ID %(badge)s") % {"badge": badge or "—"},
        )
    if unreadable:
        return (
            None,
            None,
            None,
            _("%(cols)s must be a number of days, or left blank")
            % {"cols": ", ".join(unreadable)},
        )

    # Every day of the period belongs in one of the six day columns, so a
    # complete month totals exactly the period length. Over it is impossible;
    # under it means days nobody accounted for, and payroll would compute from
    # a month with holes in it.
    #
    # Checked against the counted row rather than against the sheet: week off
    # and holiday are not read back, and a blank count means "leave that one as
    # counted" -- so both have to come from the engine or the arithmetic is
    # being done on a different month from the one being stated.
    counted = computed.get(employee.pk)
    if counted is not None:
        total = (
            sum(
                counts.get(field, counted.get(field, 0))
                for field in COUNT_COLUMNS.values()
            )
            + counted.get("week_off", 0)
            + counted.get("holiday", 0)
        )
        if round(total, 2) != period_days:
            return (
                None,
                None,
                None,
                _(
                    "The days come to %(total)s, but the period is %(days)s days "
                    "long. Every day has to be accounted for."
                )
                % {"total": _plain(total), "days": period_days},
            )

    return employee, counts, _text(record.get("Reason")), None


def by_badge_pks(by_badge):
    """The employee pks behind a badge lookup."""
    return [employee.pk for employee in by_badge.values()]


def _plain(number):
    """A count without a pointless trailing .0 -- these are days."""
    return int(number) if float(number).is_integer() else number


@login_required
@manager_can_enter("attendance.change_attendance")
def regularisation_import(request):
    """
    Apply a filled-in summary sheet.

    Every row is checked before anything is written, and the apply runs in one
    transaction: a sheet that is half wrong should be corrected and uploaded
    again, not applied in part and then reconciled by hand.

    Rejected rows come back as a workbook with a Problem column — the same shape
    the attendance import already uses. Correct them in place and upload again.
    """
    back = redirect(_safe_next(request))

    if request.method != "POST" or "regularisation_file" not in request.FILES:
        return back

    frame = _read(request.FILES["regularisation_file"])
    if frame is None:
        messages.error(request, _("That file could not be read."))
        return back

    # The period is not in the sheet: a stated total belongs to the month it
    # was stated for, and reading that from a column somebody could edit would
    # let a corrected March sheet overwrite April.
    period_from = _parse_date(request.POST.get("from_date"), None)
    period_to = _parse_date(request.POST.get("to_date"), None)
    if not period_from or not period_to:
        messages.error(request, _("The period this sheet covers was not given."))
        return back

    period_days = (period_to - period_from).days + 1

    # Badge ID, and at least one count to state. Demanding all four would
    # refuse a sheet carrying only the column somebody cared about, and a
    # column that is simply absent states nothing -- which is already what a
    # blank cell means.
    if "Badge ID" not in frame.columns:
        messages.error(request, _("The file has no Badge ID column."))
        return back

    if not any(column in frame.columns for column in COUNT_COLUMNS):
        messages.error(
            request,
            _("The file has none of these columns: %(cols)s")
            % {"cols": ", ".join(COUNT_COLUMNS)},
        )
        return back

    # One query for every badge on the sheet, scoped to whoever the user is
    # allowed to see. A badge outside their scope reads as "not found" rather
    # than being a way to reach someone else's attendance.
    badges = [b for b in (_text(v) for v in frame["Badge ID"]) if b]
    visible = filtersubordinatesemployeemodel(
        request,
        Employee.objects.filter(badge_id__in=badges),
        "attendance.view_attendance",
    )
    by_badge = {employee.badge_id: employee for employee in visible}

    # What the engine counted for these people, so a partly-filled row can be
    # checked as the month it will actually become: stated counts where given,
    # counted ones where left blank.
    counted_rows, _working, _totals = build_monthly_summary(
        period_from, period_to, Employee.objects.filter(pk__in=by_badge_pks(by_badge))
    )
    computed = {row["employee"].pk: row for row in counted_rows}

    applied, failures = [], []
    for position, record in enumerate(frame.to_dict("records"), start=2):
        employee, counts, note, reason = _check(record, by_badge, period_days, computed)
        if reason:
            failures.append({**record, "Row": position, "Problem": str(reason)})
        elif employee is not None:
            applied.append((employee, counts, note))

    if failures:
        response = HttpResponse(content_type=XLSX)
        response["Content-Disposition"] = 'attachment; filename="summary_errors.xlsx"'
        pd.DataFrame(failures).to_excel(response, index=False)
        return response

    # Stating a month settles its conflicts -- that is the point of it, and it
    # is also a quiet thing to do to somebody's attendance record. So when the
    # upload would settle any, it stops and shows which, rather than doing it
    # on the way past.
    pending_conflicts = [
        {
            "employee": employee,
            "row": computed[employee.pk],
        }
        for employee, _counts, _note in applied
        if computed.get(employee.pk, {}).get("unresolved_conflicts", 0)
    ]

    if pending_conflicts:
        _stash(request, period_from, period_to, applied)
        return redirect(f"{_safe_next(request)}?regularise=1")

    _apply(applied, period_from, period_to)
    messages.success(
        request,
        _("Stated the month's totals for %(count)s employee(s).")
        % {"count": len(applied)},
    )
    return back


SESSION_KEY = "attendance_summary_pending"


def _stash(request, period_from, period_to, applied):
    """
    Hold a validated upload until it is confirmed.

    The file itself cannot be carried across the redirect, and asking for it
    again would mean re-picking it in the file dialog. What is kept is the
    result of parsing it, which is small and already checked.
    """
    request.session[SESSION_KEY] = {
        "from_date": period_from.isoformat(),
        "to_date": period_to.isoformat(),
        "rows": [
            {"pk": employee.pk, "counts": counts, "note": note}
            for employee, counts, note in applied
        ],
    }


def _apply(applied, period_from, period_to):
    """Write the overrides. One transaction, as the upload itself is."""
    with transaction.atomic():
        for employee, counts, note in applied:
            AttendanceSummaryOverride.objects.update_or_create(
                employee_id=employee,
                from_date=period_from,
                to_date=period_to,
                defaults={**counts, "note": note},
            )


@login_required
@manager_can_enter("attendance.change_attendance")
def regularisation_confirm(request):
    """
    What the stated months are about to settle, and whether to go ahead.

    GET renders the list; POST applies it; POST with ``cancel`` throws the
    upload away. Nothing was written when the file was uploaded, so cancelling
    leaves the attendance record exactly as it was.
    """
    pending = request.session.get(SESSION_KEY)
    if not pending:
        return HttpResponse("")

    period_from = datetime.date.fromisoformat(pending["from_date"])
    period_to = datetime.date.fromisoformat(pending["to_date"])
    by_pk = {row["pk"]: row for row in pending["rows"]}

    # Re-read rather than trusting the session: between the upload and the
    # confirmation somebody may have resolved these in the calendar, and
    # showing a conflict that is already settled would be asking about work
    # already done.
    employees = filtersubordinatesemployeemodel(
        request,
        Employee.objects.filter(pk__in=by_pk),
        "attendance.view_attendance",
    )
    rows, _working, _totals = build_monthly_summary(period_from, period_to, employees)
    applied = [
        (
            row["employee"],
            by_pk[row["employee"].pk]["counts"],
            by_pk[row["employee"].pk]["note"],
        )
        for row in rows
        if row["employee"].pk in by_pk
    ]

    if request.method == "POST":
        request.session.pop(SESSION_KEY, None)
        if request.POST.get("cancel"):
            messages.info(request, _("Nothing was changed."))
        else:
            _apply(applied, period_from, period_to)
            messages.success(
                request,
                _("Stated the month's totals for %(count)s employee(s).")
                % {"count": len(applied)},
            )
        return HttpResponse(status=204, headers={"HX-Refresh": "true"})

    return render(
        request,
        "attendance/monthly_summary/regularise_confirm.html",
        {
            "rows": [r for r in rows if r["unresolved_conflicts"]],
            "total": len(applied),
            "period_from": period_from,
            "period_to": period_to,
        },
    )
