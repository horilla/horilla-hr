"""
Modern payroll dashboard views — KPI summary + ApexCharts.

Accessible at /payroll/dashboard/modern/ alongside the existing dashboard.
"""

from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, FloatField, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from horilla.decorators import permission_required


def _current_month_bounds(today=None):
    """Return (first_day, last_day) of the given date's calendar month."""
    today = today or date.today()
    first_day = today.replace(day=1)
    if first_day.month == 12:
        last_day = first_day.replace(year=first_day.year + 1, month=1) - timedelta(
            days=1
        )
    else:
        last_day = first_day.replace(month=first_day.month + 1) - timedelta(days=1)
    return first_day, last_day


def _parse_period(request):
    """Parse from_date and to_date from GET params. Defaults to the full current month."""
    default_from, default_to = _current_month_bounds()
    from_str = request.GET.get("from_date")
    to_str = request.GET.get("to_date")
    try:
        from_date = date.fromisoformat(from_str) if from_str else default_from
    except (ValueError, TypeError):
        from_date = default_from
    try:
        to_date = date.fromisoformat(to_str) if to_str else default_to
    except (ValueError, TypeError):
        to_date = default_to
    return from_date, to_date


@login_required
@permission_required("payroll.view_payslip")
def payroll_dashboard_view(request):
    """Render the modern payroll dashboard page."""
    return render(request, "payroll/dashboard.html")


@login_required
@permission_required("payroll.view_payslip")
def payroll_kpi_data(request):
    """Return payroll KPI summary data as JSON."""
    from payroll.models.models import LoanAccount, Payslip, Reimbursement

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date

    # Current month payslips
    current_qs = Payslip.objects.filter(
        start_date__gte=first_of_month,
        start_date__lte=today,
    )

    total_gross = current_qs.aggregate(
        total=Coalesce(Sum("gross_pay"), 0.0, output_field=FloatField())
    )["total"]
    total_deductions = current_qs.aggregate(
        total=Coalesce(Sum("deduction"), 0.0, output_field=FloatField())
    )["total"]
    total_net = current_qs.aggregate(
        total=Coalesce(Sum("net_pay"), 0.0, output_field=FloatField())
    )["total"]

    # Status counts
    draft = current_qs.filter(status="draft").count()
    review = current_qs.filter(status="review_ongoing").count()
    confirmed = current_qs.filter(status="confirmed").count()
    paid = current_qs.filter(status="paid").count()
    total_payslips = current_qs.count()

    # Previous month for comparison
    prev_month_end = first_of_month - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    prev_net = Payslip.objects.filter(
        start_date__gte=prev_month_start,
        start_date__lte=prev_month_end,
        status__in=["confirmed", "paid"],
    ).aggregate(total=Coalesce(Sum("net_pay"), 0.0, output_field=FloatField()))["total"]

    change_pct = 0
    if prev_net > 0:
        change_pct = round(((total_net - prev_net) / prev_net) * 100, 1)

    # Active loans
    active_loans = 0
    loan_amount = 0
    try:
        loans = LoanAccount.objects.filter(settled=False)
        active_loans = loans.count()
        loan_amount = loans.aggregate(
            total=Coalesce(Sum("loan_amount"), 0.0, output_field=FloatField())
        )["total"]
    except Exception:
        pass

    # Pending reimbursements
    pending_reimbursements = 0
    try:
        pending_reimbursements = Reimbursement.objects.filter(
            status="requested"
        ).count()
    except Exception:
        pass

    return JsonResponse(
        {
            "total_gross": round(float(total_gross), 2),
            "total_deductions": round(float(total_deductions), 2),
            "total_net": round(float(total_net), 2),
            "total_payslips": total_payslips,
            "draft": draft,
            "review": review,
            "confirmed": confirmed,
            "paid": paid,
            "change_pct": change_pct,
            "active_loans": active_loans,
            "loan_amount": round(float(loan_amount), 2),
            "pending_reimbursements": pending_reimbursements,
            "month": today.strftime("%B %Y"),
        }
    )


@login_required
@permission_required("payroll.view_payslip")
def payroll_monthly_trend(request):
    """Payroll cost trend for the last 6 months."""
    from payroll.models.models import Payslip

    _, to_date = _parse_period(request)
    today = to_date
    months = []

    for i in range(5, -1, -1):
        month_date = today.replace(day=1) - timedelta(days=i * 30)
        month_start = month_date.replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(
                year=month_start.year + 1, month=1
            ) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1) - timedelta(
                days=1
            )

        qs = Payslip.objects.filter(
            start_date__gte=month_start,
            start_date__lte=month_end,
            status__in=["confirmed", "paid"],
        )

        agg = qs.aggregate(
            gross=Coalesce(Sum("gross_pay"), 0.0, output_field=FloatField()),
            deductions=Coalesce(Sum("deduction"), 0.0, output_field=FloatField()),
            net=Coalesce(Sum("net_pay"), 0.0, output_field=FloatField()),
        )

        months.append(
            {
                "month": month_start.strftime("%b %Y"),
                "gross": round(float(agg["gross"]), 2),
                "deductions": round(float(agg["deductions"]), 2),
                "net": round(float(agg["net"]), 2),
                "count": qs.count(),
            }
        )

    return JsonResponse({"months": months})


@login_required
@permission_required("payroll.view_payslip")
def payroll_department_cost(request):
    """Payroll cost by department for the current month."""
    from payroll.models.models import Payslip

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date
    departments = []

    try:
        data = (
            Payslip.objects.filter(
                start_date__gte=first_of_month,
                start_date__lte=today,
                status__in=["confirmed", "paid", "review_ongoing"],
            )
            .values(
                "employee_id__employee_work_info__department_id",
                "employee_id__employee_work_info__department_id__department",
            )
            .annotate(
                total_net=Coalesce(Sum("net_pay"), 0.0, output_field=FloatField()),
                total_gross=Coalesce(Sum("gross_pay"), 0.0, output_field=FloatField()),
                count=Count("id"),
            )
            .order_by("-total_net")
        )

        for item in data:
            dept = item["employee_id__employee_work_info__department_id__department"]
            dept_id = item["employee_id__employee_work_info__department_id"]
            if dept:
                departments.append(
                    {
                        "department": dept,
                        "dept_id": dept_id,
                        "net": round(float(item["total_net"]), 2),
                        "gross": round(float(item["total_gross"]), 2),
                        "count": item["count"],
                    }
                )
    except Exception:
        pass

    return JsonResponse({"departments": departments, "month": today.strftime("%B %Y")})


@login_required
@permission_required("payroll.view_payslip")
def payroll_status_pipeline(request):
    """Payslip status distribution for the current month."""
    from payroll.models.models import Payslip

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date

    qs = Payslip.objects.filter(start_date__gte=first_of_month, start_date__lte=today)

    statuses = [
        {
            "status": "draft",
            "label": _("Draft"),
            "count": qs.filter(status="draft").count(),
        },
        {
            "status": "review_ongoing",
            "label": _("Review"),
            "count": qs.filter(status="review_ongoing").count(),
        },
        {
            "status": "confirmed",
            "label": _("Confirmed"),
            "count": qs.filter(status="confirmed").count(),
        },
        {
            "status": "paid",
            "label": _("Paid"),
            "count": qs.filter(status="paid").count(),
        },
    ]

    return JsonResponse({"statuses": statuses, "total": qs.count()})


@login_required
@permission_required("payroll.view_payslip")
def payroll_top_earners(request):
    """Top 10 employees by net pay this month."""
    from employee.models import Employee
    from payroll.models.models import Payslip

    from_date, to_date = _parse_period(request)
    today = to_date
    first_of_month = from_date
    earners = []

    try:
        data = (
            Payslip.objects.filter(
                start_date__gte=first_of_month,
                start_date__lte=to_date,
                status__in=["confirmed", "paid"],
            )
            .values(
                "employee_id",
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
            )
            .annotate(total_net=Sum("net_pay"), total_gross=Sum("gross_pay"))
            .order_by("-total_net")[:10]
        )

        avatar_by_employee_id = {
            emp.id: emp.get_avatar()
            for emp in Employee.objects.filter(
                id__in=[item["employee_id"] for item in data]
            )
        }

        for item in data:
            first = item["employee_id__employee_first_name"] or ""
            last = item["employee_id__employee_last_name"] or ""

            earners.append(
                {
                    "id": item["employee_id"],
                    "name": f"{first} {last}".strip(),
                    "avatar": avatar_by_employee_id.get(item["employee_id"]),
                    "net": round(float(item["total_net"] or 0), 2),
                    "gross": round(float(item["total_gross"] or 0), 2),
                }
            )
    except Exception:
        pass

    return JsonResponse({"earners": earners, "month": today.strftime("%B %Y")})


@login_required
@permission_required("payroll.view_payslip")
def payroll_contract_status(request):
    """Contracts ending or expired within the selected period."""
    from payroll.models.models import Contract

    from_date, to_date = _parse_period(request)
    today = date.today()
    ending_soon = []
    expired = []

    # The panel advertises a 60-day outlook, so always cover at least that far in
    # each direction. The selected period only ever widens the window, never
    # narrows it — otherwise the default period (which ends today) would leave
    # nothing to show.
    horizon = timedelta(days=60)

    try:
        # Still active and ending on or after today.
        ending_qs = (
            Contract.objects.filter(
                contract_end_date__gte=today,
                contract_end_date__lte=max(to_date, today + horizon),
                contract_status="active",
            )
            .select_related("employee_id")
            .order_by("contract_end_date")[:10]
        )

        for c in ending_qs:
            emp = c.employee_id
            ending_soon.append(
                {
                    "id": emp.id if emp else None,
                    "name": emp.get_full_name() if emp else "—",
                    "avatar": emp.get_avatar() if emp else None,
                    "end_date": c.contract_end_date.strftime("%b %d, %Y"),
                    "days_left": (c.contract_end_date - today).days,
                    "contract": c.contract_name or str(c),
                }
            )

        # Already ended, within the same 60-day outlook looking backwards.
        expired_qs = (
            Contract.objects.filter(
                contract_end_date__gte=min(from_date, today - horizon),
                contract_end_date__lte=today - timedelta(days=1),
            )
            .select_related("employee_id")
            .order_by("-contract_end_date")[:10]
        )

        for c in expired_qs:
            emp = c.employee_id
            expired.append(
                {
                    "id": emp.id if emp else None,
                    "name": emp.get_full_name() if emp else "—",
                    "end_date": c.contract_end_date.strftime("%b %d, %Y"),
                    "days_ago": (today - c.contract_end_date).days,
                    "contract": c.contract_name or str(c),
                }
            )
    except Exception:
        pass

    return JsonResponse(
        {
            "ending_soon": ending_soon,
            "expired": expired,
        }
    )


@login_required
@permission_required("payroll.view_payslip")
def payroll_loan_summary(request):
    """Loans provided within the selected period (still unsettled)."""
    from payroll.models.models import LoanAccount

    from_date, to_date = _parse_period(request)
    loans = []

    try:
        qs = (
            LoanAccount.objects.filter(
                settled=False,
                provided_date__gte=from_date,
                provided_date__lte=to_date,
            )
            .select_related("employee_id")
            .order_by("-provided_date")
        )

        for loan in qs[:15]:
            emp = loan.employee_id
            # Calculate remaining amount from installments
            total_installments = loan.installments or 1
            installment_amount = loan.installment_amount or 0
            total_payable = installment_amount * total_installments

            # Count paid installments from deduction_ids
            paid_installments = loan.deduction_ids.count()
            paid_amount = paid_installments * installment_amount
            remaining = max(0, loan.loan_amount - paid_amount)

            loans.append(
                {
                    "id": loan.id,
                    "employee_id": emp.id if emp else None,
                    "employee": emp.get_full_name() if emp else "—",
                    "title": loan.title,
                    "type": (
                        loan.get_type_display()
                        if hasattr(loan, "get_type_display")
                        else loan.type
                    ),
                    "amount": round(float(loan.loan_amount), 2),
                    "remaining": round(float(remaining), 2),
                    "installment": round(float(installment_amount), 2),
                    "progress": (
                        round(
                            ((loan.loan_amount - remaining) / loan.loan_amount * 100), 1
                        )
                        if loan.loan_amount > 0
                        else 0
                    ),
                }
            )
    except Exception:
        pass

    return JsonResponse({"loans": loans})


@login_required
@permission_required("payroll.view_payslip")
def payroll_reimbursement_summary(request):
    """Reimbursement requests summary for the selected period."""
    from payroll.models.models import Reimbursement

    from_date, to_date = _parse_period(request)
    summary = {"requested": 0, "approved": 0, "rejected": 0, "total_amount": 0}
    by_type = []

    try:
        qs = Reimbursement.objects.filter(
            allowance_on__gte=from_date,
            allowance_on__lte=to_date,
        )
        summary["requested"] = qs.filter(status="requested").count()
        summary["approved"] = qs.filter(status="approved").count()
        summary["rejected"] = qs.filter(status="rejected").count()

        approved_amount = qs.filter(status="approved").aggregate(
            total=Coalesce(Sum("amount"), 0.0, output_field=FloatField())
        )["total"]
        summary["total_amount"] = round(float(approved_amount), 2)

        # Group by type
        type_data = (
            qs.filter(status__in=["requested", "approved"])
            .values("type")
            .annotate(
                count=Count("id"),
                total=Coalesce(Sum("amount"), 0.0, output_field=FloatField()),
            )
            .order_by("-count")
        )

        type_labels = {
            "reimbursement": _("Reimbursement"),
            "bonus_encashment": _("Bonus Encashment"),
            "leave_encashment": _("Leave Encashment"),
        }

        for item in type_data:
            by_type.append(
                {
                    "type": type_labels.get(item["type"], item["type"]),
                    "type_key": item["type"],
                    "count": item["count"],
                    "amount": round(float(item["total"]), 2),
                }
            )
    except Exception:
        pass

    return JsonResponse({"summary": summary, "by_type": by_type})


@login_required
@permission_required("payroll.view_payslip")
def payroll_salary_distribution(request):
    """Salary band distribution across employees who were active during the selected period."""
    from employee.models import EmployeeWorkInformation

    _from, to_date = _parse_period(request)
    bands = []
    try:
        salaries = [
            row["basic_salary"]
            for row in EmployeeWorkInformation.objects.filter(
                employee_id__is_active=True,
                basic_salary__gt=0,
                date_joining__lte=to_date,
            ).values("pk", "basic_salary")
        ]
        if salaries:
            max_sal = max(salaries)
            step = max(1, round(max_sal / 6, -3)) or 10000
            band_map = {}
            for s in salaries:
                band_start = int(s // step * step)
                label = f"{band_start:,}–{band_start + step:,}"
                band_map[band_start] = band_map.get(
                    band_start,
                    {
                        "label": label,
                        "count": 0,
                        "min": band_start,
                        "max": band_start + int(step),
                    },
                )
                band_map[band_start]["count"] += 1
            bands = [
                {
                    "label": v["label"],
                    "count": v["count"],
                    "min": v["min"],
                    "max": v["max"],
                }
                for k, v in sorted(band_map.items())
            ]
    except Exception:
        pass
    return JsonResponse({"bands": bands})


@login_required
@permission_required("payroll.view_payslip")
def payroll_component_breakdown(request):
    """Top allowance and deduction components from pay_head_data."""
    from payroll.models.models import Payslip

    from_date, to_date = _parse_period(request)
    components = []
    try:
        payslips = Payslip.objects.filter(
            start_date__gte=from_date,
            start_date__lte=to_date,
            status__in=["confirmed", "paid"],
        )
        comp_map = {}
        for ps in payslips:
            if not ps.pay_head_data:
                continue
            for key in [
                "gross_pay_deductions",
                "basic_pay_deductions",
                "pretax_deductions",
                "post_tax_deductions",
                "tax_deductions",
                "net_deductions",
            ]:
                for item in ps.pay_head_data.get(key, []):
                    title = item.get("title", _("Unknown"))
                    amount = float(item.get("amount", 0))
                    if title not in comp_map:
                        comp_map[title] = {
                            "title": title,
                            "amount": 0,
                            "type": "deduction",
                        }
                    comp_map[title]["amount"] += amount
        components = sorted(comp_map.values(), key=lambda x: x["amount"], reverse=True)[
            :10
        ]
    except Exception:
        pass
    return JsonResponse({"components": components})
