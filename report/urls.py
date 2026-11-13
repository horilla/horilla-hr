from django.apps import apps
from django.urls import path

from report.cbv import audit as audit_cbv
from report.cbv import subscriptions as subscriptions_cbv
from report.views import (
    asset_report,
    attendance_report,
    check_export_access,
    employee_report,
    explorer,
    leave_report,
    payroll_report,
    pms_report,
    recruitment_report,
    report_templates,
    saved_views,
    standard_reports,
    subscriptions,
)

urlpatterns = [
    path(
        "standard/",
        standard_reports.standard_report_catalog,
        name="standard-report-catalog",
    ),
    path(
        "standard/dashboard-pins/",
        standard_reports.standard_report_dashboard_pins,
        name="standard-report-dashboard-pins",
    ),
    path(
        "standard/suggested-pack/",
        standard_reports.standard_report_suggested_pack,
        name="standard-report-suggested-pack",
    ),
    path(
        "standard/pin-recommended/",
        standard_reports.standard_report_pin_recommended,
        name="standard-report-pin-recommended",
    ),
    path(
        "subscriptions/",
        subscriptions_cbv.ReportSubscriptionsView.as_view(),
        name="report-subscriptions",
    ),
    path(
        "subscriptions/nav/",
        subscriptions_cbv.ReportSubscriptionsNav.as_view(),
        name="report-subscriptions-nav",
    ),
    path(
        "subscriptions/list/",
        subscriptions_cbv.ReportSubscriptionsListView.as_view(),
        name="report-subscriptions-list",
    ),
    path(
        "subscriptions/panel/",
        subscriptions_cbv.ReportSubscriptionsView.as_view(
            template_name="cbv/subscriptions/subscriptions_panel.html"
        ),
        name="report-subscriptions-panel",
    ),
    path(
        "audit/",
        audit_cbv.ReportAuditView.as_view(),
        name="report-audit",
    ),
    path(
        "audit/panel/",
        audit_cbv.ReportAuditView.as_view(template_name="cbv/audit/audit_panel.html"),
        name="report-audit-panel",
    ),
    path(
        "audit/nav/",
        audit_cbv.ReportAuditNav.as_view(),
        name="report-audit-nav",
    ),
    path(
        "audit/list/",
        audit_cbv.ReportAuditListView.as_view(),
        name="report-audit-list",
    ),
    path(
        "explorer/",
        explorer.explorer_picker,
        name="report-explorer",
    ),
    path(
        "subscriptions/<int:subscription_id>/toggle/",
        subscriptions.subscription_toggle,
        name="report-subscription-toggle",
    ),
    path(
        "subscriptions/<int:subscription_id>/delete/",
        subscriptions.subscription_delete,
        name="report-subscription-delete",
    ),
    path(
        "subscriptions/<int:subscription_id>/run/",
        subscriptions.subscription_run_now,
        name="report-subscription-run",
    ),
    path(
        "subscriptions/<int:subscription_id>/view/",
        subscriptions_cbv.ReportSubscriptionDetailView.as_view(),
        name="report-subscription-view",
    ),
    path(
        "subscriptions/create/",
        subscriptions_cbv.ReportSubscriptionFormView.as_view(),
        name="report-subscription-create",
    ),
    path(
        "subscriptions/<int:pk>/edit/",
        subscriptions_cbv.ReportSubscriptionFormView.as_view(),
        name="report-subscription-edit",
    ),
    path(
        "standard/favorites-chips/",
        standard_reports.standard_report_favorites_chips,
        name="standard-report-favorites-chips",
    ),
    path(
        "standard/recent-chips/",
        standard_reports.standard_report_recent_chips,
        name="standard-report-recent-chips",
    ),
    # These must come before "standard/<slug:slug>/" below — that pattern
    # matches any single path segment (e.g. it would treat "bulk-subscribe"
    # or "saved-views" as a report slug otherwise, since Django resolves
    # urlpatterns in order and the first structural match wins).
    path(
        "standard/bulk-subscribe/",
        standard_reports.standard_report_bulk_subscribe,
        name="standard-report-bulk-subscribe",
    ),
    path(
        "standard/saved-views/",
        saved_views.report_saved_views,
        name="report-saved-views",
    ),
    path(
        "standard/saved-views/<int:view_id>/reports/",
        saved_views.report_saved_view_add_reports,
        name="report-saved-view-add-reports",
    ),
    path(
        "standard/saved-views/<int:view_id>/reports/<slug:slug>/",
        saved_views.report_saved_view_remove_report,
        name="report-saved-view-remove-report",
    ),
    path(
        "standard/saved-views/<int:view_id>/delete/",
        saved_views.report_saved_view_delete,
        name="report-saved-view-delete",
    ),
    path(
        "standard/<slug:slug>/print-filters/",
        standard_reports.standard_report_print_filters,
        name="standard-report-print-filters",
    ),
    path(
        "standard/<slug:slug>/preview/",
        standard_reports.standard_report_preview,
        name="standard-report-preview",
    ),
    path(
        "standard/<slug:slug>/",
        standard_reports.standard_report_detail,
        name="standard-report-detail",
    ),
    path(
        "standard/<slug:slug>/data/",
        standard_reports.standard_report_data,
        name="standard-report-data",
    ),
    path(
        "standard/<slug:slug>/drilldown/",
        standard_reports.standard_report_drilldown,
        name="standard-report-drilldown",
    ),
    path(
        "standard/<slug:slug>/kpis/",
        standard_reports.standard_report_kpis,
        name="standard-report-kpis",
    ),
    path(
        "standard/<slug:slug>/export/",
        standard_reports.standard_report_export,
        name="standard-report-export",
    ),
    path(
        "standard/<slug:slug>/subscribe/",
        subscriptions_cbv.ReportSubscriptionFormView.as_view(),
        name="standard-report-subscribe",
    ),
    path(
        "standard/<slug:slug>/favorite/",
        standard_reports.standard_report_favorite_toggle,
        name="standard-report-favorite",
    ),
    path(
        "standard/<slug:slug>/presets/",
        standard_reports.standard_report_presets,
        name="standard-report-presets",
    ),
    path(
        "standard/<slug:slug>/presets/<int:preset_id>/delete/",
        standard_reports.standard_report_preset_delete,
        name="standard-report-preset-delete",
    ),
    path("employee-report/", employee_report.employee_report, name="employee-report"),
    path("employee-pivot/", employee_report.employee_pivot, name="employee-pivot"),
    path(
        "employee-filter-options/",
        employee_report.employee_filter_field_options,
        name="employee-filter-options",
    ),
    path(
        "report-templates/list/",
        report_templates.list_report_templates,
        name="report-templates-list",
    ),
    path(
        "report-templates/save/",
        report_templates.save_report_template,
        name="report-templates-save",
    ),
    path(
        "report-templates/<int:template_id>/",
        report_templates.get_report_template,
        name="report-templates-get",
    ),
    path(
        "report-templates/<int:template_id>/delete/",
        report_templates.delete_report_template,
        name="report-templates-delete",
    ),
    path(
        "check-export-access/", check_export_access, name="report-check-export-access"
    ),
]


if apps.is_installed("recruitment"):
    urlpatterns.extend(
        [
            path(
                "recruitment-report/",
                recruitment_report.recruitment_report,
                name="recruitment-report",
            ),
            path(
                "recruitment-pivot/",
                recruitment_report.recruitment_pivot,
                name="recruitment-pivot",
            ),
            path(
                "recruitment-filter-options/",
                recruitment_report.recruitment_filter_field_options,
                name="recruitment-filter-options",
            ),
        ]
    )

if apps.is_installed("attendance"):
    urlpatterns.extend(
        [
            path(
                "attendance-report/",
                attendance_report.attendance_report,
                name="attendance-report",
            ),
            path(
                "attendance-pivot/",
                attendance_report.attendance_pivot,
                name="attendance-pivot",
            ),
            path(
                "attendance-filter-options/",
                attendance_report.attendance_filter_field_options,
                name="attendance-filter-options",
            ),
        ]
    )

if apps.is_installed("leave"):
    urlpatterns.extend(
        [
            path("leave-report/", leave_report.leave_report, name="leave-report"),
            path("leave-pivot/", leave_report.leave_pivot, name="leave-pivot"),
            path(
                "leave-filter-options/",
                leave_report.leave_filter_field_options,
                name="leave-filter-options",
            ),
        ]
    )

if apps.is_installed("payroll"):
    urlpatterns.extend(
        [
            path(
                "payroll-report/", payroll_report.payroll_report, name="payroll-report"
            ),
            path("payroll-pivot/", payroll_report.payroll_pivot, name="payroll-pivot"),
            path(
                "payroll-filter-options/",
                payroll_report.payroll_filter_field_options,
                name="payroll-filter-options",
            ),
        ]
    )

if apps.is_installed("asset"):
    urlpatterns.extend(
        [
            path("asset-report/", asset_report.asset_report, name="asset-report"),
            path("asset-pivot/", asset_report.asset_pivot, name="asset-pivot"),
            path(
                "asset-filter-options/",
                asset_report.asset_filter_field_options,
                name="asset-filter-options",
            ),
        ]
    )

if apps.is_installed("pms"):
    urlpatterns.extend(
        [
            path("pms-report/", pms_report.pms_report, name="pms-report"),
            path("pms-pivot/", pms_report.pms_pivot, name="pms-pivot"),
            path(
                "pms-filter-options/",
                pms_report.pms_filter_field_options,
                name="pms-filter-options",
            ),
        ]
    )
