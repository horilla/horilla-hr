"""
The allowance and deduction report: what each component paid or took over a period.

Opened from the Report button in the Actions column of the Allowances and Deductions lists. The
figures are worked out from the issued payslips each time the page is opened; nothing is stored.
"""

import datetime
import json

from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from base.methods import has_export_access
from horilla.decorators import login_required, permission_required
from horilla.horilla_middlewares import ExportOptionsMiddleware
from horilla_views.generic.cbv.views import HorillaListView
from horilla_views.views import render_export_file
from payroll.filters import ComponentReportFilter
from payroll.methods import component_report
from payroll.models.models import Payslip
from payroll.views.contribution_views import _period

KINDS = (
    (component_report.ALLOWANCE, _("Allowances")),
    (component_report.DEDUCTION, _("Deductions")),
)

# The quick filters above the table, in order. "latest" is what the page opens on.
RANGES = (
    ("latest", _("Latest Payslips")),
    ("all", _("All Time")),
    ("this_month", _("This Month")),
    ("previous_month", _("Previous Month")),
    ("last_3_months", _("Last 3 Months")),
    ("this_year", _("This Year")),
    ("custom", _("Custom Range")),
)
TITLES = {
    component_report.ALLOWANCE: _("Allowance Report"),
    component_report.DEDUCTION: _("Deduction Report"),
}
# What a link keeps from the page when it changes only the date range.
RANGE_PARAMS = ("range", "from_date", "to_date")


def _kind(request):
    kind = request.GET.get("kind") or component_report.ALLOWANCE
    return kind if kind in dict(KINDS) else component_report.ALLOWANCE


def _today():
    return datetime.date.today()


def _month_start(day, back=0):
    """The first day of the month ``back`` months before ``day``'s."""
    index = day.year * 12 + day.month - 1 - back
    return datetime.date(index // 12, index % 12 + 1, 1)


def _month_end(first):
    return _month_start(first, back=-1) - datetime.timedelta(days=1)


def _export_context(request, kind, scope, columns, name):
    """What the Export action and its column picker need; the form posts to the page's own filters."""
    query = request.GET.copy()
    query["kind"] = kind
    return {
        "can_export": has_export_access(request, Payslip),
        "export_url": f"{reverse('payroll-component-report-export')}?{query.urlencode()}",
        "export_scope": scope,
        "export_columns": columns,
        "export_formats": HorillaListView.export_formats,
        "export_default_name": name,
    }


def _latest_period():
    """The period of the most recent payslip, or ``None`` when there are no payslips at all."""
    latest = Payslip.objects.order_by("-end_date", "-start_date").first()
    return (latest.start_date, latest.end_date) if latest else None


def _resolve_range(request):
    """
    ``(key, start, end)`` for the quick filter chosen; ``start`` and ``end`` are ``None`` for all time.

    Dates typed into the filter mean a custom range. With nothing asked for, the page opens on the latest
    payslips, so it shows figures rather than an empty period.
    """
    key = request.GET.get("range") or ""
    if not key and ("from_date" in request.GET or "to_date" in request.GET):
        key = "custom"
    if key not in dict(RANGES):
        key = ""

    today = _today()
    if key == "all":
        return key, None, None
    if key == "custom":
        start, end = _period(request)
        return key, start, end
    if key == "latest":
        latest = _latest_period()
        return (key, *latest) if latest else (key, None, None)
    if key == "this_month":
        first = _month_start(today)
        return key, first, _month_end(first)
    if key == "previous_month":
        first = _month_start(today, back=1)
        return key, first, _month_end(first)
    if key == "last_3_months":
        return key, _month_start(today, back=2), _month_end(_month_start(today))
    if key == "this_year":
        return key, datetime.date(today.year, 1, 1), datetime.date(today.year, 12, 31)

    latest = _latest_period()
    return ("latest", *latest) if latest else ("latest", None, None)


def _payslips(start, end):
    """
    The payslips whose period falls inside the one shown.

    Contained rather than overlapping, so a payslip of another month never adds part of itself here.
    """
    queryset = Payslip.objects.select_related("employee_id")
    if start:
        queryset = queryset.filter(start_date__gte=start)
    if end:
        queryset = queryset.filter(end_date__lte=end)
    return queryset


TAG_LABELS = (
    ("name_or_badge", _("Name Or Badge ID")),
    ("status", _("Payslip Status")),
    ("employee_id", _("Employee")),
    ("department", _("Department")),
    ("job_position", _("Job Position")),
    ("company", _("Company")),
)


def _tag_value(form, name):
    """What a filter tag says: the typed text, the status name, or the chosen records' names."""
    value = form.cleaned_data.get(name)
    if name == "status":
        return dict(form.fields["status"].choices).get(value, value)
    if value is not None and not isinstance(value, str) and hasattr(value, "__iter__"):
        names = [str(item).strip() for item in value]
        return (
            ", ".join(names)
            if len(names) <= 3
            else _("%(n)s selected") % {"n": len(names)}
        )
    return value


def _without(request, kind, *names):
    """The page's query with these parameters taken out, for a tag's remove link."""
    query = request.GET.copy()
    for name in names:
        query.pop(name, None)
    query["kind"] = kind
    return query.urlencode()


def _query_without_kind(request):
    query = request.GET.copy()
    query.pop("kind", None)
    return query.urlencode()


def _applied_tags(request, kind, form, key, start, end):
    """One tag per filter in use, each with the query that drops just that filter."""
    tags = []
    search = (request.GET.get("search") or "").strip()
    if search:
        tags.append(
            {
                "label": _("Search"),
                "value": search,
                "remove": _without(request, kind, "search"),
            }
        )
    for name, label in TAG_LABELS:
        if any(request.GET.getlist(name)):
            tags.append(
                {
                    "label": label,
                    "value": _tag_value(form, name),
                    "remove": _without(request, kind, name),
                }
            )
    if key == "custom":
        value = f"{start:%d %b %Y} – {end:%d %b %Y}" if start and end else _("Custom")
        tags.append(
            {
                "label": _("Date Range"),
                "value": value,
                "remove": _without(request, kind, *RANGE_PARAMS),
            }
        )
    return tags


def _context(request, kind):
    """The payslips being reported on and the page context."""
    key, start, end = _resolve_range(request)
    # Who was paid: the filter panel's fields, on top of the dates.
    narrowed = ComponentReportFilter(request.GET, queryset=_payslips(start, end))
    payslips = narrowed.qs
    applied = sum(1 for name in narrowed.form.fields if any(request.GET.getlist(name)))

    # The query a range link keeps: everything but the dates, so a chip never drops the search or status.
    kept = request.GET.copy()
    for name in RANGE_PARAMS:
        kept.pop(name, None)
    kept["kind"] = kind

    export = request.GET.copy()
    export["kind"] = kind

    latest = _latest_period()
    tags = _applied_tags(request, kind, narrowed.form, key, start, end)
    return payslips, {
        "applied_filters": tags,
        # The page's query without the kind, so the Allowances/Deductions switch keeps every other choice.
        "kind_query": _query_without_kind(request),
        # The filter parameters in use, so the panel and search box can drop what a removed tag took out.
        "applied_names": ",".join(
            name
            for name in ("search", *(n for n, _label in TAG_LABELS))
            if any(request.GET.getlist(name))
        ),
        "clear_all_query": f"kind={kind}"
        + ("" if key == "custom" else f"&range={key}"),
        "export_url": f"{reverse('payroll-component-report-export')}?{export.urlencode()}",
        "kind": kind,
        "kinds": KINDS,
        "ranges": [(value, label) for value, label in RANGES if value != "custom"],
        "range": key,
        "period_start": start,
        "period_end": end,
        "form": narrowed.form,
        "search": (request.GET.get("search") or "").strip(),
        "base_query": kept.urlencode(),
        "filter_count": applied + (key == "custom"),
        # Offered when the period shown has nothing, so the way to the figures is one click.
        "latest_period": latest if latest and (start, end) != latest else None,
    }


@login_required
@permission_required("payroll.view_payslip")
def component_report_home(request):
    """Every component of one kind for the period, and what it comes to."""
    kind = _kind(request)
    payslips, context = _context(request, kind)
    rows, totals = component_report.summarise(payslips, kind, context["search"])
    context.update(
        {
            "rows": rows,
            "totals": totals,
            "payslip_count": payslips.count(),
            "show_kinds": True,
            "title": TITLES[kind],
        }
    )
    columns = component_report.summary_columns(kind, totals["split"])
    context.update(
        _export_context(request, kind, "summary", columns, str(TITLES[kind]))
    )
    return render(request, "payroll/component_report/home.html", context)


@login_required
@permission_required("payroll.view_payslip")
def component_report_detail(request, kind, component_id):
    """The working behind one component's total, per employee and payslip."""
    if kind not in dict(KINDS):
        raise Http404
    payslips, context = _context(request, kind)
    model = component_report._model(kind)
    component = get_object_or_404(model.objects.entire(), pk=component_id)
    members = component_report.member_ids(kind, component)
    lines = component_report.breakdown(payslips, kind, members, context["search"])
    amount = round(sum(line["amount"] for line in lines), 2)
    employer = round(sum(line["employer_amount"] for line in lines), 2)
    # When the employer shares in the deduction the lines show both shares and what they come to together.
    split = kind == component_report.DEDUCTION and bool(employer)
    totals = {
        "amount": amount,
        "employer_amount": employer,
        "combined": round(amount + employer, 2),
    }
    context.update(
        {
            "component": component,
            "title": component.title,
            "lines": lines,
            "totals": totals,
            "split": split,
            "component_id": component.pk,
            "entries": len(members),
            # The payslip a row opens marks this component's lines: a for an earning, d for a deduction.
            "highlight": f"{'a' if kind == component_report.ALLOWANCE else 'd'}:{component.pk}",
        }
    )
    columns = component_report.detail_columns(kind, split)
    context.update(_export_context(request, kind, "detail", columns, component.title))
    return render(request, "payroll/component_report/detail.html", context)


def _period_label(start, end):
    return (
        f"{start:%d %b %Y} \u2013 {end:%d %b %Y}"
        if start and end
        else str(_("All Time"))
    )


@login_required
@permission_required("payroll.view_payslip")
@require_POST
def component_report_export(request):
    """
    The export the column picker posts: the table as it is on screen, in the columns and format chosen.

    The filters are in the query string the picker posts to, so the file holds what the page shows.
    """
    if not has_export_access(request, Payslip):
        return HttpResponseForbidden(_("You don't have access to export this data"))

    kind = _kind(request)
    payslips, context = _context(request, kind)
    try:
        chosen = [
            key for _label, key in json.loads(request.POST.get("columns") or "[]")
        ]
    except (TypeError, ValueError):
        chosen = []

    if request.POST.get("scope") == "detail":
        component = get_object_or_404(
            component_report._model(kind).objects.entire(),
            pk=request.POST.get("component_id") or 0,
        )
        records = component_report.breakdown(
            payslips,
            kind,
            component_report.member_ids(kind, component),
            context["search"],
        )
        split = kind == component_report.DEDUCTION and any(
            record["employer_amount"] for record in records
        )
        columns = component_report.detail_columns(kind, split)
        default_name = component.title
    else:
        records, totals = component_report.summarise(payslips, kind, context["search"])
        columns = component_report.summary_columns(kind, totals["split"])
        default_name = str(TITLES[kind])

    headers, rows = component_report.export_table(columns, chosen, records)
    if not headers:
        return HttpResponseBadRequest(_("Select at least one column to export."))

    export_format = (request.POST.get("format") or "xlsx").lower()
    if export_format not in dict(HorillaListView.export_formats):
        export_format = "xlsx"
    file_name = (
        ExportOptionsMiddleware._clean_name(request.POST.get("export_file_name") or "")
        or default_name
    )
    return render_export_file(
        request,
        export_format,
        file_name,
        headers,
        rows,
        _period_label(context["period_start"], context["period_end"]),
    )
