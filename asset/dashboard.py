"""
Modern asset dashboard views — KPI summary + ApexCharts.

Accessible at /asset/dashboard/modern/ alongside the existing dashboard.
"""

from datetime import timedelta

from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from horilla.decorators import login_required, permission_required


def _parse_period(request):
    """Parse from_date and to_date from GET params. Defaults to current month."""
    today = timezone.now().date()
    from_str = request.GET.get("from_date")
    to_str = request.GET.get("to_date")
    try:
        from_date = (
            timezone.datetime.fromisoformat(from_str).date()
            if from_str
            else today.replace(day=1)
        )
    except (ValueError, TypeError):
        from_date = today.replace(day=1)
    try:
        to_date = timezone.datetime.fromisoformat(to_str).date() if to_str else today
    except (ValueError, TypeError):
        to_date = today
    return from_date, to_date


def _assets_in_period(request):
    """Return Asset queryset filtered to assets purchased in the picker range."""
    from asset.models import Asset

    from_date, to_date = _parse_period(request)
    return Asset.objects.filter(
        asset_purchase_date__gte=from_date,
        asset_purchase_date__lte=to_date,
    )


@login_required
@permission_required("asset.view_assetcategory")
def asset_dashboard_view(request):
    """Render the modern asset dashboard page."""
    return render(request, "asset/dashboard.html")


@login_required
def asset_kpi_data(request):
    """Return asset KPI summary data as JSON.

    Assets purchased / total value reflect the picker range. Current-state KPIs
    (in-use / available counts, return requests, expiring soon) ignore the picker.
    """
    from asset.models import Asset, AssetAssignment, AssetRequest

    from_date, to_date = _parse_period(request)
    period_assets = _assets_in_period(request)

    # Total assets reflects the full inventory, not the picker range
    total_assets = Asset.objects.count()
    in_use = Asset.objects.filter(asset_status="In use").count()
    available = Asset.objects.filter(asset_status="Available").count()
    not_available = Asset.objects.filter(asset_status="Not-Available").count()

    # Pending requests is a current-state KPI — count all unresolved requests
    # regardless of when they were raised, not just those in the picker range
    pending_requests = AssetRequest.objects.filter(
        asset_request_status="Requested",
        requested_employee_id__is_active=True,
    ).count()

    total_value = period_assets.aggregate(
        total=Coalesce(Sum("asset_purchase_cost"), 0, output_field=DecimalField())
    )["total"]

    # Expiring soon (next 30 days) — forward-looking, independent of picker
    today = timezone.now().date()
    expiring_soon_from_date = today
    expiring_soon_to_date = today + timedelta(days=30)
    expiring_soon = Asset.objects.filter(
        expiry_date__gte=expiring_soon_from_date,
        expiry_date__lte=expiring_soon_to_date,
    ).count()

    # Return requests pending — current state
    return_requests = AssetAssignment.objects.filter(
        return_request=True,
        return_status__isnull=True,
    ).count()

    return JsonResponse(
        {
            "total_assets": total_assets,
            "in_use": in_use,
            "available": available,
            "not_available": not_available,
            "pending_requests": pending_requests,
            "total_value": float(total_value),
            "expiring_soon": expiring_soon,
            "return_requests": return_requests,
            # Echoed back so the "Total Value" card's click-through can
            # filter to the exact same purchase-date range the sum above
            # was computed from, instead of showing every asset.
            "period_from_date": from_date.isoformat(),
            "period_to_date": to_date.isoformat(),
            # Echoed back so the "Expiring Soon" card's click-through uses
            # the exact same forward-looking window expiring_soon was
            # counted from -- this is independent of the picker range above,
            # so period_from_date/period_to_date would be the wrong bounds.
            "expiring_soon_from_date": expiring_soon_from_date.isoformat(),
            "expiring_soon_to_date": expiring_soon_to_date.isoformat(),
        }
    )


@login_required
def asset_status_distribution(request):
    """Asset count by status."""
    from asset.models import Asset

    statuses = [
        {
            "status": "In use",
            "label": _("In Use"),
            "count": Asset.objects.filter(asset_status="In use").count(),
        },
        {
            "status": "Available",
            "label": _("Available"),
            "count": Asset.objects.filter(asset_status="Available").count(),
        },
        {
            "status": "Not-Available",
            "label": _("Not Available"),
            "count": Asset.objects.filter(asset_status="Not-Available").count(),
        },
    ]

    return JsonResponse({"statuses": statuses})


@login_required
def asset_by_category(request):
    """Asset count by category with in-use breakdown, for assets purchased in the picker range."""
    categories = []
    from_date, to_date = _parse_period(request)

    try:
        data = (
            _assets_in_period(request)
            .values("asset_category_id", "asset_category_id__asset_category_name")
            .annotate(
                total=Count("id"),
                in_use=Count("id", filter=Q(asset_status="In use")),
                available_count=Count("id", filter=Q(asset_status="Available")),
            )
            .order_by("-total")
        )

        for item in data:
            cat = item["asset_category_id__asset_category_name"]
            if cat:
                categories.append(
                    {
                        "category_id": item["asset_category_id"],
                        "category": cat,
                        "total": item["total"],
                        "in_use": item["in_use"],
                        "available": item["available_count"],
                    }
                )
    except Exception:
        pass

    # Echoed back so this chart's click-through can filter to the exact
    # same purchase-date range the counts above were computed from --
    # without it, "category=<id>" alone shows every asset in that
    # category ever purchased, not just the "4" this bar actually counted.
    return JsonResponse(
        {
            "categories": categories,
            "period_from_date": from_date.isoformat(),
            "period_to_date": to_date.isoformat(),
        }
    )


@login_required
def asset_request_status(request):
    """Asset request status breakdown, for the current overall request pool.

    Like asset_department_distribution / asset_age_distribution below, this is
    a snapshot of where every request currently stands, not "requests raised
    this period" activity. Scoping it to created_at within the picker range
    (which defaults to the current month) hid every request from earlier
    months, so e.g. long-pending "Requested" rows disappeared from the chart
    even though the KPI tile's "Pending Requests" count (unscoped) still
    included them -- the two numbers disagreed on-screen.
    """
    from asset.models import AssetRequest

    requests_qs = AssetRequest.objects.all()
    statuses = [
        {
            "status": "Requested",
            "label": _("Requested"),
            "count": requests_qs.filter(asset_request_status="Requested").count(),
        },
        {
            "status": "Approved",
            "label": _("Approved"),
            "count": requests_qs.filter(asset_request_status="Approved").count(),
        },
        {
            "status": "Rejected",
            "label": _("Rejected"),
            "count": requests_qs.filter(asset_request_status="Rejected").count(),
        },
    ]

    return JsonResponse({"statuses": statuses})


@login_required
def asset_value_by_category(request):
    """Total asset value by category, for assets purchased in the picker range."""
    categories = []
    from_date, to_date = _parse_period(request)

    try:
        data = (
            _assets_in_period(request)
            .values("asset_category_id", "asset_category_id__asset_category_name")
            .annotate(
                total_value=Coalesce(
                    Sum("asset_purchase_cost"), 0, output_field=DecimalField()
                ),
                count=Count("id"),
            )
            .order_by("-total_value")
        )

        for item in data:
            cat = item["asset_category_id__asset_category_name"]
            if cat:
                categories.append(
                    {
                        "category_id": item["asset_category_id"],
                        "category": cat,
                        "value": float(item["total_value"]),
                        "count": item["count"],
                    }
                )
    except Exception:
        pass

    return JsonResponse(
        {
            "categories": categories,
            "period_from_date": from_date.isoformat(),
            "period_to_date": to_date.isoformat(),
        }
    )


@login_required
def asset_expiring_soon(request):
    """Assets expiring in the next 30 days -- forward-looking, independent of picker.

    Same reasoning as the KPI tile's expiring_soon count above: expiry dates
    are inherently ahead of today, so the picker's [month-start, today]
    default (built for backward-looking "purchased this period" widgets)
    could show already-expired assets as "expiring soon" or hide genuinely
    upcoming expiries, depending on what range happened to be selected.
    """
    from asset.models import Asset

    today = timezone.now().date()
    from_date, to_date = today, today + timedelta(days=30)
    assets = []

    try:
        qs = (
            Asset.objects.filter(
                expiry_date__gte=from_date,
                expiry_date__lte=to_date,
            )
            .select_related("asset_category_id")
            .order_by("expiry_date")[:15]
        )

        for a in qs:
            days_left = (a.expiry_date - today).days
            assets.append(
                {
                    "id": a.id,
                    "name": a.asset_name,
                    "tracking_id": a.asset_tracking_id,
                    "category": (
                        a.asset_category_id.asset_category_name
                        if a.asset_category_id
                        else "—"
                    ),
                    "expiry_date": a.expiry_date.strftime("%b %d, %Y"),
                    "days_left": days_left,
                    "status": a.asset_status,
                }
            )
    except Exception:
        pass

    return JsonResponse({"assets": assets})


@login_required
def asset_recent_allocations(request):
    """Recently allocated assets within the picker range."""
    from asset.models import AssetAssignment

    from_date, to_date = _parse_period(request)
    allocations = []

    try:
        qs = (
            AssetAssignment.objects.filter(
                return_status__isnull=True,
                assigned_date__gte=from_date,
                assigned_date__lte=to_date,
            )
            .select_related(
                "asset_id", "assigned_to_employee_id", "asset_id__asset_category_id"
            )
            .order_by("-assigned_date")[:15]
        )

        for aa in qs:
            emp = aa.assigned_to_employee_id
            allocations.append(
                {
                    "id": emp.id if emp else None,
                    "employee": emp.get_full_name() if emp else "—",
                    "avatar": emp.get_avatar() if emp else None,
                    "asset": aa.asset_id.asset_name if aa.asset_id else "—",
                    "category": (
                        aa.asset_id.asset_category_id.asset_category_name
                        if aa.asset_id and aa.asset_id.asset_category_id
                        else "—"
                    ),
                    "date": (
                        aa.assigned_date.strftime("%b %d") if aa.assigned_date else "—"
                    ),
                }
            )
    except Exception:
        pass

    return JsonResponse({"allocations": allocations})


@login_required
def asset_department_distribution(request):
    """Assets currently held, distributed by department (via assigned employees).

    This is a snapshot of who holds what right now, not "assigned this
    period" activity -- unlike the Total Value/By Category charts (which
    intentionally track purchases in the picker range), filtering this by
    assigned_date hid every currently-held asset whose assignment just
    happened to be recorded outside the current month, understating each
    department's real current holdings.
    """
    from asset.models import AssetAssignment

    departments = []

    try:
        data = (
            AssetAssignment.objects.filter(
                return_status__isnull=True,
            )
            .values(
                "assigned_to_employee_id__employee_work_info__department_id",
                "assigned_to_employee_id__employee_work_info__department_id__department",
            )
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        for item in data:
            dept = item[
                "assigned_to_employee_id__employee_work_info__department_id__department"
            ]
            dept_id = item["assigned_to_employee_id__employee_work_info__department_id"]
            if dept:
                departments.append(
                    {
                        "department_id": dept_id,
                        "department": dept,
                        "count": item["count"],
                    }
                )
    except Exception:
        pass

    return JsonResponse({"departments": departments})


@login_required
def asset_age_distribution(request):
    """Age distribution of the entire current asset fleet.

    Same fix as asset_department_distribution: this is a snapshot of how
    old the assets we currently own are, not "assets purchased this
    period" activity. Scoping it to _assets_in_period made it collapse to
    a single "< 1 year" bucket every month by construction -- anything
    bought in the current period is by definition under a month old, so
    the fleet's real age spread (most assets purchased years ago) never
    showed up at all.
    """
    from asset.models import Asset

    today = timezone.now().date()
    brackets = []
    try:
        bracket_map = {
            "< 1 year": 0,
            "1–2 years": 0,
            "2–3 years": 0,
            "3–5 years": 0,
            "5+ years": 0,
        }
        for a in Asset.objects.filter(asset_purchase_date__isnull=False):
            age_years = (today - a.asset_purchase_date).days / 365.25
            if age_years < 1:
                bracket_map["< 1 year"] += 1
            elif age_years < 2:
                bracket_map["1–2 years"] += 1
            elif age_years < 3:
                bracket_map["2–3 years"] += 1
            elif age_years < 5:
                bracket_map["3–5 years"] += 1
            else:
                bracket_map["5+ years"] += 1
        brackets = [{"bracket": k, "count": v} for k, v in bracket_map.items() if v > 0]
    except Exception:
        pass
    return JsonResponse({"brackets": brackets})
