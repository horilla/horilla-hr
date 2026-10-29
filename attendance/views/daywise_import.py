"""
Regularising by day: download the Day-Wise grid as a sheet, change statuses from a dropdown, upload.

One row per employee, one column per date, a status code in each cell. Only the cells that were
changed are applied, each as the same regularisation the Day-Wise popover makes, so the last one
wins and the work records follow. This replaces the old summary sheet (totals per employee), which
is deprecated; see ``regularisation_import``.
"""

import datetime
import io

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from attendance.models import AttendanceConflictResolution
from attendance.views.regularisation_import import XLSX, _scope
from attendance.views.summary import DAILY_VIEW_MAX_DAYS, build_daily_rows
from base.methods import filtersubordinatesemployeemodel
from employee.models import Employee
from horilla.decorators import login_required, manager_can_enter

SHEET = "Day-Wise"
GUIDE = "How To Fill This In"
WEEKDAY_ROW = 0  # zero-based: the weekday of each date
HEADER_ROW = 1  # then the headers, with the dates
ID_HEADER = "Employee ID"

# code -> (resolution, label, meaning, fill, text)
STATUSES = {
    "P": (
        "full_present",
        gettext_lazy("Present"),
        gettext_lazy("Worked the full day."),
        "#86efac",
        "#14532d",
    ),
    "HD": (
        "half_present",
        gettext_lazy("Half Day"),
        gettext_lazy("Present for half the day, paid leave for the other half."),
        "#a7e8c4",
        "#1f2937",
    ),
    "HA": (
        "half_absent",
        gettext_lazy("Half Absent"),
        gettext_lazy("Present for half the day, absent for the other half."),
        "#d9d99a",
        "#1f2937",
    ),
    "A": (
        "absent",
        gettext_lazy("Absent"),
        gettext_lazy("Not present, no approved leave."),
        "#fca5a5",
        "#7f1d1d",
    ),
    "PL": (
        "paid_leave",
        gettext_lazy("Paid Leave"),
        gettext_lazy("A paid leave day."),
        "#93c5fd",
        "#1e3a8a",
    ),
    "UL": (
        "unpaid_leave",
        gettext_lazy("Unpaid Leave"),
        gettext_lazy("An unpaid leave day. Affects payroll."),
        "#fdba74",
        "#7c2d12",
    ),
    "WO": (
        "week_off",
        gettext_lazy("Week Off"),
        gettext_lazy("A rest day."),
        "#c4b5fd",
        "#4c1d95",
    ),
    "H": (
        "holiday",
        gettext_lazy("Holiday"),
        gettext_lazy("A holiday."),
        "#5eead4",
        "#134e4a",
    ),
}
# Shown in the grid but not something to type: they come from the clock, or need the calendar.
READ_ONLY_CODES = {
    "SH": gettext_lazy(
        "Short Hours: the day fell short of the shift. Set it to P, HD or A."
    ),
    "PH": gettext_lazy(
        "Partial Hours: set from the calendar, which asks for the hours."
    ),
}


def _dates(from_date, to_date):
    return [
        from_date + datetime.timedelta(days=i)
        for i in range((to_date - from_date).days + 1)
    ]


@login_required
@manager_can_enter("attendance.change_attendance")
def daywise_template(request):
    """The Day-Wise grid for the filtered employees and range, as a sheet to fill in."""
    import xlsxwriter

    employees, from_date, to_date = _scope(request)
    days = (to_date - from_date).days + 1
    if days > DAILY_VIEW_MAX_DAYS:
        messages.error(
            request,
            _(
                "The Day-Wise Sheet Covers Up To %(days)s Days. Choose A Shorter Date Range."
            )
            % {"days": DAILY_VIEW_MAX_DAYS},
        )
        return redirect(reverse("attendance-monthly-summary"))
    ordered = list(employees.order_by("employee_first_name", "employee_last_name"))
    rows = build_daily_rows(ordered, from_date, to_date)
    dates = _dates(from_date, to_date)

    buffer = io.BytesIO()
    book = xlsxwriter.Workbook(buffer, {"in_memory": True})
    sheet = book.add_worksheet(SHEET)
    base = {"font_name": "Calibri", "valign": "vcenter"}

    def fmt(**kw):
        return book.add_format({**base, **kw})

    # Horilla's warning yellow (hsl(40, 91%, 60%)) for the headers; weekends a shade deeper.
    yellow, deep = "#f6b83c", "#e8a21f"
    edge = "#c98a1a"
    head = fmt(
        bold=True,
        font_color="#1f2937",
        bg_color=yellow,
        border=1,
        border_color=edge,
        align="center",
    )
    head_left = fmt(
        bold=True,
        font_color="#1f2937",
        bg_color=yellow,
        border=1,
        border_color=edge,
        indent=1,
    )
    weekday = fmt(
        bold=True,
        font_size=9,
        font_color="#1f2937",
        bg_color=yellow,
        border=1,
        border_color=edge,
        align="center",
    )
    weekday_weekend = fmt(
        bold=True,
        font_size=9,
        font_color="#1f2937",
        bg_color=deep,
        border=1,
        border_color=edge,
        align="center",
    )
    head_weekend = fmt(
        bold=True,
        font_color="#1f2937",
        bg_color=deep,
        border=1,
        border_color=edge,
        align="center",
        num_format="dd mmm",
    )
    head_day = fmt(
        bold=True,
        font_color="#1f2937",
        bg_color=yellow,
        border=1,
        border_color=edge,
        align="center",
        num_format="dd mmm",
    )
    name = fmt(bold=True, border=1, border_color="#e5e7eb", indent=1)
    badge = fmt(font_color="#6b7280", border=1, border_color="#e5e7eb", indent=1)
    cell = fmt(
        bold=True, align="center", border=1, border_color="#ffffff", font_size=10
    )

    last_col = 2 + len(dates)
    sheet.set_row(WEEKDAY_ROW, 18)
    sheet.set_row(HEADER_ROW, 24)
    for col in range(3):
        sheet.write(WEEKDAY_ROW, col, "", head)

    sheet.write(HEADER_ROW, 0, ID_HEADER, head)
    sheet.write(HEADER_ROW, 1, _("Badge ID"), head_left)
    sheet.write(HEADER_ROW, 2, _("Employee"), head_left)
    for i, day in enumerate(dates):
        weekend = day.weekday() >= 5
        sheet.write(
            WEEKDAY_ROW, 3 + i, f"{day:%a}", weekday_weekend if weekend else weekday
        )
        sheet.write_datetime(
            HEADER_ROW,
            3 + i,
            datetime.datetime.combine(day, datetime.time()),
            head_weekend if weekend else head_day,
        )

    for r, row in enumerate(rows, start=HEADER_ROW + 1):
        employee = row["employee"]
        sheet.set_row(r, 22)
        sheet.write_number(r, 0, employee.pk)
        sheet.write(r, 1, employee.badge_id or "", badge)
        sheet.write(r, 2, employee.get_full_name(), name)
        for i, c in enumerate(row["cells"]):
            sheet.write(r, 3 + i, c["code"] if c["status"] != "future" else "", cell)

    first_row, last_row = HEADER_ROW + 1, HEADER_ROW + len(rows)
    sheet.set_column(0, 0, 11, None, {"hidden": True})
    sheet.set_column(1, 1, 12)
    sheet.set_column(2, 2, 28)
    sheet.set_column(3, last_col, 8.5)
    sheet.freeze_panes(HEADER_ROW + 1, 3)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.repeat_rows(WEEKDAY_ROW, HEADER_ROW)

    if rows:
        area = (first_row, 3, last_row, last_col)
        sheet.data_validation(
            *area,
            {
                "validate": "list",
                "source": list(STATUSES),
                "ignore_blank": True,
                "input_title": _("Status"),
                "input_message": _(
                    "P Present, HD Half Day, HA Half Absent, A Absent, PL Paid Leave, UL Unpaid Leave, WO Week Off, H Holiday"
                ),
                "error_title": _("Not A Status"),
                "error_message": _("Choose One Of: %(codes)s.")
                % {"codes": ", ".join(STATUSES)},
            },
        )
        for code, (_res, _label, _meaning, fill, text) in STATUSES.items():
            sheet.conditional_format(
                *area,
                {
                    "type": "cell",
                    "criteria": "==",
                    "value": f'"{code}"',
                    "format": book.add_format({"bg_color": fill, "font_color": text}),
                },
            )
        for code, fill, text in (
            ("SH", "#fca5a5", "#7f1d1d"),
            ("PH", "#67e8f9", "#155e75"),
        ):
            sheet.conditional_format(
                *area,
                {
                    "type": "cell",
                    "criteria": "==",
                    "value": f'"{code}"',
                    "format": book.add_format({"bg_color": fill, "font_color": text}),
                },
            )
        sheet.conditional_format(
            *area,
            {
                "type": "text",
                "criteria": "containing",
                "value": "/",
                "format": book.add_format(
                    {"bg_color": "#e5e7eb", "font_color": "#374151"}
                ),
            },
        )
        sheet.autofilter(HEADER_ROW, 1, last_row, last_col)

    _guide(book, fmt)
    book.close()

    response = HttpResponse(buffer.getvalue(), content_type=XLSX)
    response["Content-Disposition"] = (
        f'attachment; filename="day_wise_{from_date:%Y%m%d}_{to_date:%Y%m%d}.xlsx"'
    )
    return response


def _guide(book, fmt):
    """The second sheet: what each code means, and how the upload treats the cells."""
    sheet = book.add_worksheet(GUIDE)
    sheet.hide_gridlines(2)
    title = fmt(
        bold=True, font_size=15, font_color="#1f2937", bg_color="#f6b83c", indent=1
    )
    head = fmt(
        bold=True,
        font_color="#1f2937",
        bg_color="#f6b83c",
        border=1,
        border_color="#c98a1a",
        indent=1,
    )
    text = fmt(border=1, border_color="#e5e7eb", indent=1, text_wrap=True)
    section = fmt(
        bold=True, font_size=12, font_color="#1f2937", bottom=2, bottom_color="#f6b83c"
    )

    sheet.merge_range(0, 0, 0, 2, _("How To Fill This In"), title)
    sheet.set_row(0, 30)
    sheet.write(2, 0, _("Code"), head)
    sheet.write(2, 1, _("Status"), head)
    sheet.write(2, 2, _("Meaning"), head)
    row = 3
    for code, (_res, label, meaning, fill, color) in STATUSES.items():
        sheet.write(
            row,
            0,
            code,
            fmt(
                bold=True,
                align="center",
                border=1,
                border_color="#ffffff",
                bg_color=fill,
                font_color=color,
            ),
        )
        sheet.write(row, 1, str(label), text)
        sheet.write(row, 2, str(meaning), text)
        row += 1
    for code, meaning in READ_ONLY_CODES.items():
        sheet.write(
            row,
            0,
            code,
            fmt(
                bold=True,
                align="center",
                border=1,
                border_color="#ffffff",
                bg_color="#e5e7eb",
                font_color="#374151",
            ),
        )
        sheet.write(row, 1, _("Shown Only"), text)
        sheet.write(row, 2, str(meaning), text)
        row += 1

    row += 1
    sheet.merge_range(row, 0, row, 2, _("Rules"), section)
    rules = [
        _(
            "Change only the day cells. The Badge ID and Employee columns identify the row; do not edit them."
        ),
        _(
            "Only the cells you change are applied. A cell left as it was, or left blank, changes nothing."
        ),
        _(
            "Each change is saved as a regularisation for that employee and day. The last one for a day wins."
        ),
        _("Upcoming days cannot be regularised and are skipped."),
        _(
            "A split day (for example P/UL) or partial hours is set from the calendar, not from this sheet."
        ),
        _(
            "Upload the file from Actions > Import Day-Wise Sheet on the Monthly Summary."
        ),
    ]
    for rule in rules:
        row += 1
        sheet.merge_range(row, 0, row, 2, f"•  {rule}", text)
        sheet.set_row(row, 30)
    sheet.set_column(0, 0, 10)
    sheet.set_column(1, 1, 20)
    sheet.set_column(2, 2, 70)


def _read(upload):
    """``(employee_ids, dates, {(employee_id, date): code})`` from an uploaded sheet, or None when it is not one."""
    from openpyxl import load_workbook

    try:
        book = load_workbook(upload, data_only=True, read_only=True)
        sheet = book[SHEET] if SHEET in book.sheetnames else book.worksheets[0]
        grid = list(sheet.iter_rows(values_only=True))
    except Exception:  # noqa: BLE001 - reported to whoever uploaded it
        return None
    header = None
    for index, values in enumerate(grid[:8]):
        if values and str(values[0] or "").strip() == ID_HEADER:
            header = index
            break
    if header is None:
        return None
    dates = {}
    for col, value in enumerate(grid[header][3:], start=3):
        if isinstance(value, datetime.datetime):
            dates[col] = value.date()
        elif isinstance(value, datetime.date):
            dates[col] = value
    cells = {}
    for values in grid[header + 1 :]:
        try:
            pk = int(values[0])
        except (TypeError, ValueError, IndexError):
            continue
        for col, day in dates.items():
            value = values[col] if col < len(values) else None
            code = str(value).strip().upper() if value is not None else ""
            if code:
                cells[(pk, day)] = code
    return dates, cells


@login_required
@manager_can_enter("attendance.change_attendance")
def daywise_import(request):
    """Apply the cells that were changed in an uploaded Day-Wise sheet."""
    target = reverse("attendance-monthly-summary")
    if request.method != "POST":
        return redirect(target)
    upload = request.FILES.get("regularisation_file")
    if upload is None:
        messages.error(request, _("Choose A File To Upload."))
        return redirect(target)
    parsed = _read(upload)
    if parsed is None or not parsed[0]:
        messages.error(
            request,
            _(
                "This Is Not A Day-Wise Sheet. Download The Template From This Dialog And Fill That In."
            ),
        )
        return redirect(target)
    dates, cells = parsed
    days = sorted(dates.values())
    if len(days) > DAILY_VIEW_MAX_DAYS:
        messages.error(
            request,
            _("The Day-Wise Sheet Covers Up To %(days)s Days.")
            % {"days": DAILY_VIEW_MAX_DAYS},
        )
        return redirect(target)

    allowed = filtersubordinatesemployeemodel(
        request,
        Employee.objects.filter(pk__in={pk for pk, _day in cells}),
        "attendance.change_attendance",
    )
    people = {e.pk: e for e in allowed}
    current = {}
    for row in build_daily_rows(list(people.values()), days[0], days[-1]):
        for day, c in zip(_dates(days[0], days[-1]), row["cells"]):
            current[(row["employee"].pk, day)] = c

    today = datetime.date.today()
    applied = unchanged = 0
    skipped = []
    with transaction.atomic():
        for (pk, day), code in sorted(
            cells.items(), key=lambda item: (item[0][0], item[0][1])
        ):
            employee = people.get(pk)
            if employee is None:
                skipped.append(
                    _("%(day)s: Employee Not Found Or Not Yours To Change")
                    % {"day": f"{day:%d %b}"}
                )
                continue
            now = current.get((pk, day))
            if now is not None and now["code"] == code:
                unchanged += 1
                continue
            if code not in STATUSES:
                if code not in READ_ONLY_CODES and "/" not in code:
                    skipped.append(f"{employee} {day:%d %b}: {code}")
                continue
            if day > today:
                skipped.append(
                    _("%(who)s %(day)s: Upcoming Day")
                    % {"who": employee, "day": f"{day:%d %b}"}
                )
                continue
            AttendanceConflictResolution._base_manager.update_or_create(
                employee_id=employee,
                date=day,
                defaults={
                    "resolution": STATUSES[code][0],
                    "conflict_type": "daywise_import",
                },
            )
            applied += 1

    if applied:
        messages.success(
            request,
            _("%(n)s Days Regularised From The Day-Wise Sheet.") % {"n": applied},
        )
    else:
        messages.info(request, _("No Changes Found In The Sheet."))
    if skipped:
        shown = "; ".join(skipped[:5]) + (
            f" (+{len(skipped) - 5})" if len(skipped) > 5 else ""
        )
        messages.warning(
            request,
            _("%(n)s Cells Skipped: %(list)s") % {"n": len(skipped), "list": shown},
        )
    return redirect(
        f"{target}?view=daily&from_date={days[0].isoformat()}&to_date={days[-1].isoformat()}"
    )
