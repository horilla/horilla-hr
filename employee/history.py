"""
Aggregated, cross-record history for a given employee + model, used by the
employee profile History tab.
"""

from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from employee.models import Employee
from horilla_audit.activity_feed import (
    normalize_log_entries,
    normalize_tracking_entries,
)
from horilla_views.history_methods import get_diff

# Overrides for models with more than one Employee FK, or reached only
# indirectly (a cross-relation lookup path instead of a field on the model
# itself -- Django's .filter(**{...}) accepts either the same way).
EMPLOYEE_FIELD_OVERRIDES = {
    ("asset", "assetassignment"): "assigned_to_employee_id",
    ("asset", "assetrequest"): "requested_employee_id",
    ("payroll", "salarystructure"): "contracts__employee_id",
    ("leave", "leavetype"): "employee_available_leave__employee_id",
    ("offboarding", "offboardingnote"): "employee_id__employee_id",
    ("offboarding", "employeetask"): "employee_id__employee_id",
    ("recruitment", "candidate"): "converted_employee_id",
    ("pms", "employeekeyresult"): "employee_objective_id__employee_id",
}

_PREFERRED_FIELD_NAMES = ("employee_id", "employee")

# Records scanned per model before filtering/sorting, to bound cost on
# high-volume models.
MAX_RECORDS_PER_MODEL = 200

# Every stage of the employment lifecycle this employee has an FK/O2O link
# to -- excluding M2M-only links (recruitment.InterviewSchedule, pms.Meetings,
# onboarding.*, project.Task, ...) and pure note/comment/attachment tables.
EMPLOYEE_HISTORY_MODELS = [
    # Work information
    ("employee", "employeeworkinformation"),
    ("employee", "employeebankdetails"),
    # Payroll / compensation
    ("payroll", "contract"),
    ("payroll", "payslip"),
    ("payroll", "salarystructure"),
    ("payroll", "loanaccount"),
    ("payroll", "reimbursement"),
    # Leave / attendance
    ("leave", "leaverequest"),
    ("leave", "availableleave"),
    ("leave", "leaveallocationrequest"),
    ("leave", "leavetype"),
    ("leave", "compensatoryleaverequest"),
    ("attendance", "attendance"),
    ("attendance", "attendanceovertime"),
    ("attendance", "attendanceactivity"),
    # Performance
    ("pms", "employeeobjective"),
    ("pms", "employeekeyresult"),
    ("pms", "feedback"),
    ("pms", "employeebonuspoint"),
    ("pms", "answer"),
    ("pms", "meetingsanswer"),
    ("pms", "keyresultfeedback"),
    ("pms", "anonymousfeedback"),
    ("employee", "bonuspoint"),
    # Recruitment / hiring
    ("recruitment", "candidate"),
    ("recruitment", "candidaterating"),
    # Conduct / penalties
    ("base", "penaltyaccounts"),
    # Documents / assets
    ("horilla_documents", "document"),
    ("asset", "assetassignment"),
    ("asset", "assetrequest"),
    # Helpdesk / meetings
    ("helpdesk", "ticket"),
    ("helpdesk", "claimrequest"),
    ("horilla_meet", "googlemeeting"),
    ("project", "timesheet"),
    # Offboarding
    ("offboarding", "offboardingemployee"),
    ("offboarding", "offboardingnote"),
    ("offboarding", "employeetask"),
    ("offboarding", "resignationletter"),
]

# User-facing dropdown labels -- plain HR language instead of app_label/verbose_name.
MODEL_LABELS = {
    ("employee", "employeeworkinformation"): _("Work Information"),
    ("employee", "employeebankdetails"): _("Bank Details"),
    ("payroll", "contract"): _("Contract"),
    ("payroll", "payslip"): _("Payslip"),
    ("payroll", "salarystructure"): _("Salary Structure"),
    ("payroll", "loanaccount"): _("Loan"),
    ("payroll", "reimbursement"): _("Reimbursement"),
    ("leave", "leaverequest"): _("Leave Request"),
    ("leave", "availableleave"): _("Leave Balance"),
    ("leave", "leaveallocationrequest"): _("Leave Allocation Request"),
    ("leave", "leavetype"): _("Leave Type"),
    ("leave", "compensatoryleaverequest"): _("Compensatory Leave Request"),
    ("attendance", "attendance"): _("Attendance"),
    ("attendance", "attendanceovertime"): _("Hours & Overtime Balance"),
    ("attendance", "attendanceactivity"): _("Clock In / Clock Out Activity"),
    ("recruitment", "candidate"): _("Recruitment Application"),
    ("recruitment", "candidaterating"): _("Candidate Ratings Given"),
    ("pms", "employeeobjective"): _("Performance Objective"),
    ("pms", "employeekeyresult"): _("Key Result"),
    ("pms", "feedback"): _("360° Feedback"),
    ("pms", "employeebonuspoint"): _("Performance Bonus Points"),
    ("pms", "answer"): _("Feedback Answer"),
    ("pms", "meetingsanswer"): _("Meeting Answer"),
    ("pms", "keyresultfeedback"): _("Key Result Feedback"),
    ("pms", "anonymousfeedback"): _("Anonymous Feedback"),
    ("employee", "bonuspoint"): _("Bonus Points"),
    ("base", "penaltyaccounts"): _("Penalty"),
    ("horilla_documents", "document"): _("Document"),
    ("asset", "assetassignment"): _("Asset Allocation"),
    ("asset", "assetrequest"): _("Asset Request"),
    ("helpdesk", "ticket"): _("Helpdesk Ticket"),
    ("helpdesk", "claimrequest"): _("Claim Request"),
    ("horilla_meet", "googlemeeting"): _("Google Meeting"),
    ("project", "timesheet"): _("Timesheet"),
    ("offboarding", "offboardingemployee"): _("Offboarding"),
    ("offboarding", "offboardingnote"): _("Offboarding Note"),
    ("offboarding", "employeetask"): _("Offboarding Task"),
    ("offboarding", "resignationletter"): _("Resignation Letter"),
}


def _employee_field_name(model):
    key = (model._meta.app_label.lower(), model._meta.model_name.lower())
    if key in EMPLOYEE_FIELD_OVERRIDES:
        return EMPLOYEE_FIELD_OVERRIDES[key]

    candidates = [
        f.name
        for f in model._meta.get_fields()
        if getattr(f, "concrete", False)
        and not f.auto_created
        and not f.many_to_many
        and (f.many_to_one or getattr(f, "one_to_one", False))
        and getattr(f, "related_model", None) is Employee
    ]
    for preferred in _PREFERRED_FIELD_NAMES:
        if preferred in candidates:
            return preferred
    return candidates[0] if candidates else None


def _model_label(model):
    key = (model._meta.app_label.lower(), model._meta.model_name.lower())
    return MODEL_LABELS.get(key, model._meta.verbose_name.title())


def get_employee_history_models():
    """(key, label, model, field_name) for each curated HR-relevant model."""
    entries = []
    for app_label, model_name in EMPLOYEE_HISTORY_MODELS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        field_name = _employee_field_name(model)
        if not field_name:
            continue
        key = (model._meta.app_label.lower(), model._meta.model_name.lower())
        entries.append(
            {
                "key": f"{model._meta.app_label}.{model._meta.model_name}",
                "label": MODEL_LABELS.get(key, model._meta.verbose_name.title()),
                "model": model,
                "field_name": field_name,
            }
        )
    return entries


def _history_related_name(model):
    if hasattr(model, "history") and hasattr(getattr(model, "history"), "model"):
        return "history"
    if hasattr(model, "history_set"):
        return "history_set"
    if hasattr(model, "history"):
        return "history"
    return None


def _history_rows_by_pk(model, history_related_name, rows):
    """One query for every row's simple-history versions, newest first."""
    accessor = getattr(model, history_related_name)
    if hasattr(accessor, "model"):
        history_model = accessor.model
        link_field = model._meta.pk
    else:
        history_model = accessor.rel.related_model
        link_field = accessor.rel.field

    grouped = {row.pk: [] for row in rows}
    versions = (
        history_model.objects.filter(**{f"{link_field.name}__in": list(grouped)})
        .select_related("history_user")
        .order_by("-history_date", "-history_id")
    )
    for version in versions:
        grouped.setdefault(getattr(version, link_field.attname), []).append(version)
    return grouped


def build_model_history(model, model_key, model_label, rows):
    """
    History entries for already-fetched ``rows`` of ``model``, tagged with the
    record they belong to. Shared by the employee and candidate History tabs.

    Returns ``(entries, tracking_status)`` where ``tracking_status`` is one
    of "simple_history", "auditlog", or "none".
    """
    history_related_name = _history_related_name(model)
    entries = []

    if history_related_name:
        tracking_status = "simple_history"
        versions_by_pk = _history_rows_by_pk(model, history_related_name, rows)
        actor_cache = {}
        for row in rows:
            diffs = get_diff(
                row,
                history_related_name,
                history_list=versions_by_pk.get(row.pk, []),
                actor_cache=actor_cache,
            )
            record_repr = str(row)
            for entry in normalize_tracking_entries(diffs):
                pair = entry.get("pair")
                entry["record"] = row
                entry["record_repr"] = record_repr
                entry["model_label"] = model_label
                history_id = getattr(pair[0], "pk", None) if pair else None
                entry["entry_key"] = (
                    f"{model_key}|h|{history_id}"
                    if history_id is not None
                    else f"{model_key}|c|{row.pk}"
                )
                entries.append(entry)
    else:
        # Query existing LogEntry rows before checking live registration --
        # a model unregistered after being tracked keeps its old LogEntry
        # rows, and those should still show up here.
        ct = ContentType.objects.get_for_model(model)
        row_ids = [str(row.pk) for row in rows]
        log_entries = LogEntry.objects.filter(
            content_type=ct, object_pk__in=row_ids
        ).order_by("-timestamp")
        by_pk = {str(row.pk): row for row in rows}
        for entry in normalize_log_entries(log_entries):
            row = by_pk.get(entry.get("object_pk"))
            entry["record"] = row
            entry["record_repr"] = str(row) if row else entry.get("object_pk")
            entry["model_label"] = model_label
            entry["entry_key"] = f"{model_key}|l|{entry['log_id']}"
            entries.append(entry)

        if entries or auditlog.contains(model):
            tracking_status = "auditlog"
        else:
            tracking_status = "none"

    return entries, tracking_status


def filter_and_sort_entries(entries, date_from=None, date_to=None, sort="-date"):
    """Date-range filter and order a merged feed."""
    if date_from:
        entries = [
            e
            for e in entries
            if e["history_date"] and e["history_date"].date() >= date_from
        ]
    if date_to:
        entries = [
            e
            for e in entries
            if e["history_date"] and e["history_date"].date() <= date_to
        ]

    entries.sort(
        key=lambda e: e["history_date"] or timezone.now(), reverse=sort != "date"
    )
    return entries


def get_employee_model_history(
    employee, model_key, date_from=None, date_to=None, sort="-date"
):
    """
    Merged, per-record-tagged history feed for every row of ``model_key``
    belonging to ``employee``.

    Returns ``(entries, tracking_status)`` where ``tracking_status`` is one
    of "simple_history", "auditlog", or "none".
    """
    app_label, model_name = model_key.split(".", 1)
    model = apps.get_model(app_label, model_name)
    field_name = _employee_field_name(model)
    if not field_name:
        return [], "none"

    rows = list(
        model._base_manager.filter(**{field_name: employee})
        .distinct()
        .order_by("-pk")[:MAX_RECORDS_PER_MODEL]
    )
    if "__" not in field_name:
        for row in rows:
            setattr(row, field_name, employee)

    entries, tracking_status = build_model_history(
        model, model_key, _model_label(model), rows
    )
    return (
        filter_and_sort_entries(entries, date_from, date_to, sort),
        tracking_status,
    )


def get_employee_entries_by_keys(employee, keys, sort="-date"):
    """Entries picked by ``entry_key`` across models, merged into one feed."""
    allowed = {m["key"] for m in get_employee_history_models()}
    wanted = {}
    for key in keys:
        model_key = key.split("|", 1)[0]
        if model_key in allowed:
            wanted.setdefault(model_key, set()).add(key)

    selected = []
    for model_key, model_keys in wanted.items():
        model_entries, _status = get_employee_model_history(
            employee, model_key, sort=sort
        )
        selected.extend(e for e in model_entries if e.get("entry_key") in model_keys)

    selected.sort(
        key=lambda e: e["history_date"] or timezone.now(), reverse=sort != "date"
    )
    return selected


def entry_search_text(entry):
    parts = [
        entry.get("model_label"),
        entry.get("record_repr"),
        entry.get("actor_name"),
        entry.get("action_phrase"),
        entry.get("reason"),
    ]
    for change in entry.get("changes") or []:
        parts.extend(
            [
                change.get("field_label") or change.get("field"),
                change.get("old_value"),
                change.get("new_value"),
            ]
        )
    return " ".join(str(p) for p in parts if p).lower()


def get_employee_history_search(
    employee, model_options, search, date_from=None, date_to=None, sort="-date"
):
    """Entries from every given model whose text contains the search phrase."""
    phrase = search.lower()
    matched = []
    for option in model_options:
        model_entries, tracking_status = get_employee_model_history(
            employee, option["key"], date_from=date_from, date_to=date_to, sort=sort
        )
        if tracking_status == "none":
            continue
        for entry in model_entries:
            if phrase in entry_search_text(entry):
                matched.append(entry)

    matched.sort(
        key=lambda e: e["history_date"] or timezone.now(), reverse=sort != "date"
    )
    return matched
