"""Views for standard enterprise reports catalog and detail."""

from __future__ import annotations

import json

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from horilla.decorators import login_required
from report.access import (
    company_id_from_request,
    user_can_export_report,
    user_can_subscribe_report,
    user_can_view_report,
)
from report.company_context import company_letterhead
from report.engine import filters_from_request
from report.export import export_csv, export_pdf, export_xlsx
from report.filter_schema import build_filter_options, build_filter_schema
from report.models import (
    ReportFavorite,
    ReportFilterPreset,
    ReportRunLog,
    ReportSavedView,
    ReportSubscription,
)
from report.personalization import (
    DASHBOARD_PIN_PRIORITY_SLUGS,
    MAX_DASHBOARD_REPORT_PINS,
    SUGGESTED_REPORT_SLUGS,
    catalog_cards_for_slugs,
    favorite_slugs_for_user,
    filters_dict_from_request,
    is_favorited,
    log_report_run,
    presets_for_report,
    recent_run_slugs,
    saved_views_for_user,
    session_company_id,
)
from report.registry import (
    DOMAIN_LABELS,
    get_report,
    reports_by_domain,
    run_drilldown,
    run_report,
    run_report_kpis,
)
from report.views.explorer import explorer_domain_entries


def _export_meta(request, definition, filters, slug: str) -> dict:
    company = company_letterhead(request, company_id=filters.company_id)
    filters_pairs = filters.summary_pairs()
    return {
        "product_name": "Horilla HR · Standard Reports",
        "company": company,
        "user": getattr(request.user, "get_full_name", lambda: "")()
        or getattr(request.user, "username", ""),
        "slug": slug,
        "domain": definition.domain,
        # Structured (label, value) pairs with FK ids resolved to names —
        # the audit-ready form; filters_label stays as the joined fallback.
        "filters_pairs": filters_pairs,
        "filters_label": " · ".join(
            value if label == "Period" else f"{label}: {value}"
            for label, value in filters_pairs
        ),
        "generated_at": timezone.now(),
    }


def _ensure_definitions_loaded():
    import report.metrics  # noqa: F401


def _parse_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


# Per-domain icon for the catalog's category rail and report rows. Icons are
# Ionicons (already loaded app-wide). Every domain shares the same neutral
# tile color -- the rest of Horilla reserves color for hover/active/selected
# states, not for a rainbow of category accents, so this matches that
# convention instead of inventing a 5-color palette with no precedent
# elsewhere in the app.
DOMAIN_META = {
    "workforce": {"icon": "people-outline"},
    "time_leave": {"icon": "time-outline"},
    "payroll": {"icon": "cash-outline"},
    "talent": {"icon": "briefcase-outline"},
    "compliance": {"icon": "shield-checkmark-outline"},
}
_NEUTRAL_TILE = {"color": "#475569", "soft": "#F1F5F9"}
_DEFAULT_DOMAIN_META = {"icon": "document-text-outline", **_NEUTRAL_TILE}


@login_required
def standard_report_catalog(request):
    _ensure_definitions_loaded()
    from django.db.models import Max

    company_id = company_id_from_request(request)
    grouped = reports_by_domain(user=request.user, company_id=company_id)

    all_slugs = [r.slug for reports in grouped.values() for r in reports]
    last_run_by_slug = dict(
        ReportRunLog.objects.filter(
            user=request.user, report_slug__in=all_slugs, is_active=True
        )
        .values("report_slug")
        .annotate(last_run=Max("created_at"))
        .values_list("report_slug", "last_run")
    )

    sections = []
    for domain, reports in grouped.items():
        meta = DOMAIN_META.get(domain, _DEFAULT_DOMAIN_META)
        sections.append(
            {
                "domain": domain,
                "label": str(DOMAIN_LABELS.get(domain, domain)),
                "icon": meta["icon"],
                "color": _NEUTRAL_TILE["color"],
                "soft": _NEUTRAL_TILE["soft"],
                "reports": [
                    {
                        "slug": r.slug,
                        "name": str(r.name),
                        "description": str(r.description),
                        "url": reverse("standard-report-detail", args=[r.slug]),
                        "print_url": reverse(
                            "standard-report-print-filters", args=[r.slug]
                        ),
                        "favorite_url": reverse(
                            "standard-report-favorite", args=[r.slug]
                        ),
                        "subscribe_url": reverse(
                            "standard-report-subscribe", args=[r.slug]
                        ),
                        "inspector_url": reverse(
                            "standard-report-inspector", args=[r.slug]
                        ),
                        "can_subscribe": user_can_subscribe_report(
                            request.user, r, company_id=company_id
                        ),
                        "last_run": last_run_by_slug.get(r.slug),
                        "is_favorite": False,
                    }
                    for r in reports
                ],
            }
        )

    fav_slugs = favorite_slugs_for_user(request)
    for section in sections:
        for report in section["reports"]:
            report["is_favorite"] = report["slug"] in fav_slugs

    favorites = catalog_cards_for_slugs(
        sorted(fav_slugs), request.user, company_id=company_id
    )
    for card in favorites:
        card["is_favorite"] = True

    recent = catalog_cards_for_slugs(
        recent_run_slugs(request), request.user, company_id=company_id
    )
    for card in recent:
        card["is_favorite"] = card["slug"] in fav_slugs

    saved_views = [
        {"id": v.id, "name": v.name, "slugs_json": json.dumps(v.report_slugs or [])}
        for v in saved_views_for_user(request)
    ]

    can_view_audit = request.user.is_superuser or request.user.has_perm(
        "employee.view_employee"
    )
    # Tab chip-badge counts (Browse/Audit/Subscriptions). Audit reuses
    # ReportAuditListView's own base queryset (report/cbv/audit.py) rather
    # than a fresh filter, so the count always matches what that tab
    # actually lists; Subscriptions matches ReportSubscriptionsListView's
    # owner-scoped, status-unfiltered queryset (report/cbv/subscriptions.py)
    # for the same reason.
    audit_count = ReportRunLog.objects.count() if can_view_audit else 0
    subscription_count = (
        ReportSubscription.objects.get_queryset().filter(owner=request.user).count()
    )

    return render(
        request,
        "report/standard_catalog.html",
        {
            "sections": sections,
            "favorites": favorites,
            "recent": recent,
            "saved_views": saved_views,
            "report_count": sum(len(s["reports"]) for s in sections),
            "can_view_audit": can_view_audit,
            "audit_count": audit_count,
            "subscription_count": subscription_count,
            "has_explorer_access": bool(explorer_domain_entries(request)),
        },
    )


@login_required
@require_http_methods(["GET"])
def standard_report_favorites_chips(request):
    """HTMX fragment: re-fetched each time the Favorites dropdown opens, so
    it reflects favorites toggled elsewhere on the page without a reload."""
    company_id = company_id_from_request(request)
    fav_slugs = favorite_slugs_for_user(request)
    favorites = catalog_cards_for_slugs(
        sorted(fav_slugs), request.user, company_id=company_id
    )
    return render(
        request,
        "report/_catalog_chip_list.html",
        {"reports": favorites, "kind": "favorite"},
    )


@login_required
@require_http_methods(["GET"])
def standard_report_recent_chips(request):
    """HTMX fragment: re-fetched each time the Recent dropdown opens, so a
    report run earlier in the same session shows up without a reload."""
    company_id = company_id_from_request(request)
    recent = catalog_cards_for_slugs(
        recent_run_slugs(request), request.user, company_id=company_id
    )
    return render(
        request, "report/_catalog_chip_list.html", {"reports": recent, "kind": "recent"}
    )


@login_required
@require_http_methods(["GET"])
def standard_report_print_filters(request, slug):
    """
    HTMX partial: catalog quick-print modal with period, filters, PDF/Excel.
    Defaults to all-time + unrestricted employment so empty choices = complete data.
    """
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_view_report(
        request.user, definition, company_id=company_id
    ):
        return HttpResponseForbidden(
            _("You do not have permission to view this report.")
        )

    filter_options = build_filter_options(definition)
    filter_schema = build_filter_schema(definition, options=filter_options)
    can_export = user_can_export_report(
        request.user, definition, request=request, company_id=company_id
    )
    return render(
        request,
        "report/standard_report_print_modal.html",
        {
            "report": definition,
            "report_name": str(definition.name),
            "slug": slug,
            "filter_schema": filter_schema,
            "filter_options": filter_options,
            "export_url": reverse("standard-report-export", args=[slug]),
            "detail_url": reverse("standard-report-detail", args=[slug]),
            "can_export": can_export,
            "pdf_row_limit": 500,
            "xlsx_row_limit": 5000,
            "default_period": "all_time",
            "default_employment_status": "all",
        },
    )


@login_required
@require_http_methods(["GET"])
def standard_report_inspector(request, slug):
    """
    HTMX fragment for the catalog's right-side inspector panel — shown when
    a row/card is selected in list mode. "Your subscription" and audit
    history are real data (ReportSubscription / ReportRunLog), not the
    fabricated per-report "Owner"/"Schedule" fields the design mockup used
    (a report definition has no single owner, and can have 0-N
    subscriptions across different users with different frequencies).
    """
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_view_report(
        request.user, definition, company_id=company_id
    ):
        return HttpResponseForbidden(
            _("You do not have permission to view this report.")
        )

    subscription = (
        ReportSubscription.objects.filter(
            report_slug=slug, owner=request.user, is_active=True
        )
        .order_by("-created_at")
        .first()
    )

    can_view_audit = request.user.is_superuser or request.user.has_perm(
        "employee.view_employee"
    )
    audit_qs = ReportRunLog.objects.filter(report_slug=slug, is_active=True)
    session_company = session_company_id(request)
    if session_company is not None:
        audit_qs = audit_qs.filter(company_id_id=session_company)
    else:
        audit_qs = audit_qs.filter(company_id__isnull=True)
    if not can_view_audit:
        audit_qs = audit_qs.filter(user=request.user)
    audit_entries = list(
        audit_qs.select_related("user__employee_get").order_by("-created_at")[:5]
    )

    return render(
        request,
        "report/standard_report_inspector.html",
        {
            "report": definition,
            "report_name": str(definition.name),
            "report_description": str(definition.description),
            "slug": slug,
            "print_url": reverse("standard-report-print-filters", args=[slug]),
            "subscribe_url": reverse("standard-report-subscribe", args=[slug]),
            "can_subscribe": user_can_subscribe_report(
                request.user, definition, company_id=company_id
            ),
            "subscription": subscription,
            "audit_entries": audit_entries,
        },
    )


@login_required
def standard_report_detail(request, slug):
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_view_report(
        request.user, definition, company_id=company_id
    ):
        return HttpResponseForbidden(
            _("You do not have permission to view this report.")
        )

    explorer_url = None
    if definition.explorer_url_name:
        try:
            explorer_url = reverse(definition.explorer_url_name)
        except Exception:
            explorer_url = None

    filter_options = build_filter_options(definition)
    filter_schema = build_filter_schema(definition, options=filter_options)

    return render(
        request,
        "report/standard_report.html",
        {
            "report": definition,
            "report_name": str(definition.name),
            "report_description": str(definition.description),
            "slug": slug,
            "domain": definition.domain,
            "domain_label": str(
                DOMAIN_LABELS.get(definition.domain, definition.domain)
            ),
            "company": company_letterhead(request),
            "filter_schema": filter_schema,
            "filter_options": filter_options,
            "explorer_url": explorer_url,
            "is_favorite": is_favorited(request, slug),
            "filter_presets": presets_for_report(request, slug),
            "data_url": reverse("standard-report-data", args=[slug]),
            "export_xlsx_url": reverse("standard-report-export", args=[slug])
            + "?format=xlsx",
            "export_csv_url": reverse("standard-report-export", args=[slug])
            + "?format=csv",
            "export_pdf_url": reverse("standard-report-export", args=[slug])
            + "?format=pdf",
            "favorite_url": reverse("standard-report-favorite", args=[slug]),
            "presets_url": reverse("standard-report-presets", args=[slug]),
            "subscribe_url": reverse("standard-report-subscribe", args=[slug]),
            "subscriptions_url": reverse("report-subscriptions"),
            "drilldown_url": reverse("standard-report-drilldown", args=[slug]),
            "kpis_url": reverse("standard-report-kpis", args=[slug]),
            "has_drilldown": bool(definition.drilldown_fn),
            "default_recipient": getattr(request.user, "email", "") or "",
            "can_subscribe": user_can_subscribe_report(
                request.user, definition, company_id=company_id
            ),
            "can_export": user_can_export_report(
                request.user, definition, request=request, company_id=company_id
            ),
        },
    )


@login_required
@require_http_methods(["GET"])
def standard_report_data(request, slug):
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_view_report(
        request.user, definition, company_id=company_id
    ):
        return JsonResponse({"error": "Forbidden"}, status=403)

    filters = filters_from_request(request)
    try:
        payload = run_report(slug, filters)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)

    if payload.get("explorer_url_name"):
        try:
            payload["explorer_url"] = reverse(payload["explorer_url_name"])
        except Exception:
            pass
    log_report_run(request, slug, "view", filters_dict_from_request(request))
    return JsonResponse(payload)


@login_required
@require_http_methods(["GET"])
def standard_report_export(request, slug):
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_export_report(
        request.user, definition, request=request, company_id=company_id
    ):
        return JsonResponse({"error": "Forbidden"}, status=403)

    filters = filters_from_request(request)
    filters.extra["row_limit"] = 5000
    fmt = (request.GET.get("format") or "xlsx").lower()
    async_mode = (request.GET.get("async") or "").lower() in {"1", "true", "yes"}
    log_filters = filters_dict_from_request(request)
    log_filters["format"] = fmt
    if async_mode:
        log_filters["async"] = True
        to_email = (getattr(request.user, "email", "") or "").strip()
        if not to_email:
            return JsonResponse(
                {"error": _("Your account has no email address for async export.")},
                status=400,
            )
        from report.async_export import ExportQueueFull, queue_export_email

        meta = _export_meta(request, definition, filters, slug)
        # Serialize meta dates for the worker thread
        meta_safe = dict(meta)
        if meta_safe.get("generated_at"):
            meta_safe["generated_at"] = meta_safe["generated_at"].isoformat()
        try:
            queue_export_email(
                user_id=request.user.id,
                to_email=to_email,
                slug=slug,
                fmt=fmt,
                filters_dict=filters_dict_from_request(request),
                meta=meta_safe,
                # The worker has no session, so the selected company has to
                # travel with the job or the export is not tenant-scoped.
                company_id=company_id,
            )
        except ExportQueueFull:
            return JsonResponse(
                {
                    "error": _(
                        "Too many exports are running right now. "
                        "Please try again in a few minutes."
                    )
                },
                status=429,
            )
        log_report_run(request, slug, "export", log_filters)
        return JsonResponse(
            {
                "ok": True,
                "async": True,
                "message": _(
                    "Export started. You will receive an email at %(email)s when ready."
                )
                % {"email": to_email},
            }
        )

    payload = run_report(slug, filters)
    safe_name = slug.replace("/", "-")
    meta = _export_meta(request, definition, filters, slug)
    log_report_run(request, slug, "export", log_filters)
    if fmt == "csv":
        return export_csv(payload, filename=f"{safe_name}.csv", meta=meta)
    if fmt == "pdf":
        try:
            return export_pdf(payload, filename=f"{safe_name}.pdf", meta=meta)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)
    return export_xlsx(payload, filename=f"{safe_name}.xlsx", meta=meta)


@login_required
@require_http_methods(["GET"])
def standard_report_drilldown(request, slug):
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_view_report(
        request.user, definition, company_id=company_id
    ):
        return JsonResponse({"error": "Forbidden"}, status=403)
    if not definition.drilldown_fn:
        return JsonResponse(
            {"error": _("This report does not support drill-down.")}, status=400
        )

    filters = filters_from_request(request)
    params = {
        "dimension": request.GET.get("dimension") or "",
        "value": request.GET.get("value") or "",
        "chart_id": request.GET.get("chart_id") or "",
        "limit": request.GET.get("limit") or "",
    }
    try:
        payload = run_drilldown(slug, filters, params, request)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
    return JsonResponse(payload)


@login_required
@require_http_methods(["GET"])
def standard_report_kpis(request, slug):
    """KPI-only endpoint for dashboard pins (Phase 9)."""
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_view_report(
        request.user, definition, company_id=company_id
    ):
        return JsonResponse({"error": "Forbidden"}, status=403)
    filters = filters_from_request(request)
    try:
        payload = run_report_kpis(slug, filters)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)
    try:
        payload["report_url"] = reverse("standard-report-detail", args=[slug])
    except Exception:
        payload["report_url"] = ""
    return JsonResponse(payload)


@login_required
@require_http_methods(["GET"])
def standard_report_dashboard_pins(request):
    """
    Return KPI cards for the current user's favorited standard reports.
    Used as a lightweight home-dashboard pin surface (Phase 9).
    """
    _ensure_definitions_loaded()
    company_id = company_id_from_request(request)
    slugs = sorted(favorite_slugs_for_user(request))[:MAX_DASHBOARD_REPORT_PINS]
    cards = []
    for slug in slugs:
        definition = get_report(slug)
        if not definition or not user_can_view_report(
            request.user, definition, company_id=company_id
        ):
            continue
        filters = filters_from_request(request)
        try:
            payload = run_report_kpis(slug, filters)
        except Exception:
            continue
        cards.append(
            {
                "slug": slug,
                "title": payload.get("title") or str(definition.name),
                "domain": definition.domain,
                "kpis": (payload.get("kpis") or [])[:4],
                "report_url": reverse("standard-report-detail", args=[slug]),
                "period": payload.get("period"),
            }
        )
    return JsonResponse(
        {
            "pins": cards,
            "favorite_count": len(favorite_slugs_for_user(request)),
            "max_pins": MAX_DASHBOARD_REPORT_PINS,
        }
    )


@login_required
@require_http_methods(["GET"])
def standard_report_suggested_pack(request):
    """
    Opt-in Suggested reports for the home dashboard.

    Never auto-favorites — the client must call favorite toggle / pin-recommended.
    """
    _ensure_definitions_loaded()
    company_id = company_id_from_request(request)
    fav = favorite_slugs_for_user(request)
    suggestions = []
    for slug in SUGGESTED_REPORT_SLUGS:
        definition = get_report(slug)
        if not definition or not user_can_view_report(
            request.user, definition, company_id=company_id
        ):
            continue
        suggestions.append(
            {
                "slug": slug,
                "title": str(definition.name),
                "description": str(definition.description or ""),
                "domain": definition.domain,
                "report_url": reverse("standard-report-detail", args=[slug]),
                "is_favorite": slug in fav,
                "priority": slug in DASHBOARD_PIN_PRIORITY_SLUGS,
            }
        )
    return JsonResponse(
        {
            "suggestions": suggestions,
            "priority_slugs": [
                s
                for s in DASHBOARD_PIN_PRIORITY_SLUGS
                if s in {x["slug"] for x in suggestions}
            ],
            "favorite_count": len(fav),
            "max_pins": MAX_DASHBOARD_REPORT_PINS,
        }
    )


@login_required
@require_http_methods(["POST"])
def standard_report_pin_recommended(request):
    """
    Opt-in: favorite recommended Suggested slugs until the 6-pin cap is reached.

    Does not unfavorite existing pins; only fills empty slots.
    """
    _ensure_definitions_loaded()
    company_id = company_id_from_request(request)
    fav = set(favorite_slugs_for_user(request))
    added = []
    for slug in DASHBOARD_PIN_PRIORITY_SLUGS:
        if len(fav) >= MAX_DASHBOARD_REPORT_PINS:
            break
        if slug in fav:
            continue
        definition = get_report(slug)
        if not definition or not user_can_view_report(
            request.user, definition, company_id=company_id
        ):
            continue
        ReportFavorite.objects.create(
            user=request.user,
            report_slug=slug,
            company_id_id=company_id,
        )
        fav.add(slug)
        added.append(slug)
    return JsonResponse(
        {
            "added": added,
            "favorite_count": len(fav),
            "max_pins": MAX_DASHBOARD_REPORT_PINS,
        }
    )


@login_required
@require_http_methods(["POST"])
def standard_report_favorite_toggle(request, slug):
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_view_report(
        request.user, definition, company_id=company_id
    ):
        return JsonResponse({"error": "Forbidden"}, status=403)

    qs = ReportFavorite.objects.filter(user=request.user, report_slug=slug)
    if company_id is not None:
        qs = qs.filter(company_id_id=company_id)
    else:
        qs = qs.filter(company_id__isnull=True)

    existing = qs.first()
    if existing:
        existing.delete()
        return JsonResponse(
            {
                "favorited": False,
                "slug": slug,
                "favorite_count": len(favorite_slugs_for_user(request)),
                "max_pins": MAX_DASHBOARD_REPORT_PINS,
            }
        )

    if len(favorite_slugs_for_user(request)) >= MAX_DASHBOARD_REPORT_PINS:
        return JsonResponse(
            {
                "error": _("Pin limit reached (%(n)s). Unpin a report first.")
                % {"n": MAX_DASHBOARD_REPORT_PINS},
                "favorited": False,
                "slug": slug,
                "favorite_count": MAX_DASHBOARD_REPORT_PINS,
                "max_pins": MAX_DASHBOARD_REPORT_PINS,
            },
            status=400,
        )

    ReportFavorite.objects.create(
        user=request.user,
        report_slug=slug,
        company_id_id=company_id,
    )
    return JsonResponse(
        {
            "favorited": True,
            "slug": slug,
            "favorite_count": len(favorite_slugs_for_user(request)),
            "max_pins": MAX_DASHBOARD_REPORT_PINS,
        }
    )


@login_required
@require_http_methods(["GET", "POST"])
def standard_report_presets(request, slug):
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_view_report(
        request.user, definition, company_id=company_id
    ):
        return JsonResponse({"error": "Forbidden"}, status=403)

    if request.method == "GET":
        return JsonResponse({"presets": presets_for_report(request, slug)})

    body = _parse_json_body(request)
    name = (body.get("name") or request.POST.get("name") or "").strip()
    filters = body.get("filters")
    if filters is None:
        filters = filters_dict_from_request(request)
    if not name:
        return JsonResponse({"error": _("Preset name is required.")}, status=400)
    if not isinstance(filters, dict):
        return JsonResponse({"error": _("Invalid filters.")}, status=400)

    preset, created = ReportFilterPreset.objects.update_or_create(
        user=request.user,
        report_slug=slug,
        name=name,
        company_id_id=company_id,
        defaults={"filters": filters, "is_active": True},
    )
    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "preset": {"id": preset.id, "name": preset.name, "filters": preset.filters},
            "presets": presets_for_report(request, slug),
        }
    )


@login_required
@require_http_methods(["POST"])
def standard_report_bulk_subscribe(request):
    """
    Create one ReportSubscription per selected report, sharing a single
    frequency/format/recipients input — the catalog grid's bulk-select bar.
    Reports the user lacks subscribe access to are silently skipped and
    reported back rather than failing the whole batch.
    """
    _ensure_definitions_loaded()
    body = _parse_json_body(request)
    slugs = body.get("report_slugs") or []
    frequency = (body.get("frequency") or "weekly").strip()
    fmt = (body.get("format") or "xlsx").strip()
    recipients = (body.get("recipients") or "").strip()

    if not isinstance(slugs, list) or not slugs:
        return JsonResponse({"error": _("Select at least one report.")}, status=400)
    if not recipients:
        return JsonResponse({"error": _("Recipients are required.")}, status=400)
    if frequency not in dict(ReportSubscription.FREQUENCY_CHOICES):
        return JsonResponse({"error": _("Invalid frequency.")}, status=400)

    company_id = company_id_from_request(request)
    created = 0
    skipped = []
    for slug in slugs:
        definition = get_report(slug)
        if not definition or not user_can_subscribe_report(
            request.user, definition, company_id=company_id
        ):
            skipped.append(slug)
            continue
        ReportSubscription.objects.create(
            report_slug=slug,
            name=str(definition.name),
            frequency=frequency,
            recipients=recipients,
            filters={"format": fmt},
            owner=request.user,
            company_id_id=company_id,
        )
        created += 1

    return JsonResponse({"ok": True, "created": created, "skipped": skipped})


@login_required
@require_http_methods(["POST", "DELETE"])
def standard_report_preset_delete(request, slug, preset_id):
    _ensure_definitions_loaded()
    definition = get_report(slug)
    company_id = company_id_from_request(request)
    if not definition or not user_can_view_report(
        request.user, definition, company_id=company_id
    ):
        return JsonResponse({"error": "Forbidden"}, status=403)

    qs = ReportFilterPreset.objects.filter(
        id=preset_id, user=request.user, report_slug=slug
    )
    if company_id is not None:
        qs = qs.filter(company_id_id=company_id)
    else:
        qs = qs.filter(company_id__isnull=True)
    preset = get_object_or_404(qs)
    preset.delete()
    return JsonResponse({"ok": True, "presets": presets_for_report(request, slug)})
