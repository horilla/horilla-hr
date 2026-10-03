"""
Tracking what has to be remitted.

Payroll has always computed the employer's share of a contribution component —
``calculate_employer_contribution`` writes it onto every payslip — and has never
shown it. So the figure that gets paid to a provident fund or an insurer existed
only inside a JSON column, and the only way to total a month was to open the
payslips one at a time.
"""

import csv
import datetime

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from horilla.decorators import login_required, permission_required
from payroll.methods import contributions
from payroll.models.models import Deduction, PayPeriodSettings, Payslip

# Anything but a draft is a figure somebody may act on. Draft is included by
# default all the same: the point of watching this is to see a liability before
# it is paid, not after.
STATUSES = [
    ("", "All"),
    ("draft", "Draft"),
    ("review_ongoing", "Review ongoing"),
    ("confirmed", "Confirmed"),
    ("paid", "Paid"),
]


def _period(request):
    """
    The period being reported on, defaulting to the configured pay period.

    Not "the last 30 days": a contribution is remitted per pay period, and a
    total spanning two of them is not a figure anybody can use.
    """
    settings = PayPeriodSettings.for_company(
        getattr(
            getattr(request.user, "employee_get", None),
            "get_company",
            lambda: None,
        )()
    )
    start, end = settings.period_for(datetime.date.today())

    def parse(value, fallback):
        try:
            return datetime.date.fromisoformat(value)
        except (TypeError, ValueError):
            return fallback

    start = parse(request.GET.get("from_date"), start)
    end = parse(request.GET.get("to_date"), end)
    if start > end:
        start, end = end, start
    return start, end


def _payslips(request, start, end):
    """
    The payslips whose period falls inside the one being reported on.

    Contained rather than overlapping: a payslip for a different month that
    happens to touch this one would put part of another period's liability into
    this period's total.
    """
    queryset = Payslip.objects.filter(
        start_date__gte=start, end_date__lte=end
    ).select_related("employee_id")

    status = request.GET.get("status") or ""
    if status:
        queryset = queryset.filter(status=status)
    return queryset


@login_required
@permission_required("payroll.view_payslip")
def contribution_list(request):
    """Every contribution component for the period, and what it comes to."""
    start, end = _period(request)
    payslips = _payslips(request, start, end)
    rows, totals = contributions.summarise(payslips)

    return render(
        request,
        "payroll/contribution/contribution_home.html",
        {
            "rows": rows,
            "totals": totals,
            "period_start": start,
            "period_end": end,
            "statuses": STATUSES,
            "status": request.GET.get("status") or "",
            "payslip_count": payslips.count(),
        },
    )


@login_required
@permission_required("payroll.view_payslip")
def contribution_detail(request, component_id):
    """The working behind one component's figure."""
    start, end = _period(request)
    component = get_object_or_404(Deduction.objects.entire(), pk=component_id)
    lines = contributions.breakdown(_payslips(request, start, end), component_id)

    return render(
        request,
        "payroll/contribution/contribution_detail.html",
        {
            "component": component,
            "lines": lines,
            "period_start": start,
            "period_end": end,
            "statuses": STATUSES,
            "status": request.GET.get("status") or "",
            "totals": {
                "employee_amount": round(
                    sum(line["employee_amount"] for line in lines), 2
                ),
                "employer_amount": round(
                    sum(line["employer_amount"] for line in lines), 2
                ),
                "total": round(sum(line["total"] for line in lines), 2),
            },
        },
    )


@login_required
@permission_required("payroll.view_payslip")
def contribution_export(request):
    """
    The period as a CSV, per employee per component.

    Per employee rather than the summary: a remittance return is filed per
    member, and a total on its own cannot be filed or queried.
    """
    start, end = _period(request)
    payslips = _payslips(request, start, end)
    rows, _totals = contributions.summarise(payslips)

    response = HttpResponse(content_type="text/csv")
    name = f"contributions_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{name}"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Component",
            "Badge ID",
            "Employee",
            "Period start",
            "Period end",
            "Status",
            "Employee share",
            "Employer share",
            "Total",
        ]
    )
    for row in rows:
        for line in contributions.breakdown(payslips, row["id"]):
            writer.writerow(
                [
                    row["title"],
                    line["employee"].badge_id or "",
                    str(line["employee"]),
                    line["start_date"],
                    line["end_date"],
                    line["status"],
                    line["employee_amount"],
                    line["employer_amount"],
                    line["total"],
                ]
            )
    return response
