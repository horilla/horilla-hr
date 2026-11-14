"""
Per-file authorization for protected_media.

protected_media used to serve every uploaded file to any authenticated user or
JWT holder, so a colleague's identity papers or contract were readable by URL
even though the document screens refuse them. This module resolves a requested
media path to the record that owns the file and applies the same idea those
screens use: the record's own employee, that employee's reporting manager, a
participant of the record (ticket assignee, project manager, recruitment
manager, ...), the uploader, or a holder of the view permission.

Paths under a model's upload directory whose owner cannot be found or is not
authorized are refused. Paths outside every model's upload directory keep the
previous behaviour (any authenticated user), and OPEN_MEDIA_PREFIXES lists the
model files that are legitimately shown to every signed-in employee.
"""

from django.apps import apps
from django.db import models

# Files rendered to every signed-in employee across the UI (avatars, icons,
# announcement and policy attachments). They carry no per-record access rule.
OPEN_MEDIA_PREFIXES = (
    "employee/employee/employee_profile/",
    "leave/leavetype/icon/",
    "base/company/icon/",
    "base/attachment/",
    "employee/policymultiplefile/",
    "employee/policies/",
    "onboarding/onboardingcandidate/profile/",
    "onboarding/onboardingportal/profile/",
    "employee/profile/",
)

# Lookup tables that say nothing about who may see a file; reaching them
# through a foreign key must not turn their view permission into access.
_NON_OWNER_MODELS = {
    "horilla_auth.HorillaUser",
    "employee.Employee",
    "base.Company",
    "base.Department",
    "base.JobPosition",
    "base.JobRole",
    "base.EmployeeShift",
    "base.WorkType",
    "leave.LeaveType",
    "employee.Actiontype",
    "payroll.Allowance",
    "payroll.FilingStatus",
    "payroll.SalaryStructure",
    "project.ProjectStage",
}

# Foreign keys to an employee that say nothing about who may see the record.
_NON_PARTICIPANT_FIELDS = {"referral", "converted_employee_id"}

_MAX_DEPTH = 2
_MAX_RELATED_ROWS = 100

_registry_cache = None


def _upload_prefix(model, field):
    """Directory a field's files are stored in, or None if it is not derivable."""
    from horilla.models import upload_path

    if field.upload_to is upload_path:
        return f"{model._meta.app_label}/{model._meta.model_name}/{field.name}/"
    if isinstance(field.upload_to, str) and field.upload_to:
        return field.upload_to if field.upload_to.endswith("/") else None
    return None


def _registry():
    """(model, field name, upload prefix or None) for every file field."""
    global _registry_cache
    if _registry_cache is None:
        entries = []
        for model in apps.get_models():
            if model._meta.proxy or model._meta.auto_created:
                continue
            for field in model._meta.get_fields():
                if isinstance(field, models.FileField) and not field.auto_created:
                    entries.append((model, field.name, _upload_prefix(model, field)))
        # model-level prefix ("app/model/") also covers legacy paths written
        # before the field name was part of the upload path.
        _registry_cache = entries
    return _registry_cache


def _model_app_labels():
    return {model._meta.app_label for model, _name, _prefix in _registry()}


def is_open_media(path):
    return path.startswith(OPEN_MEDIA_PREFIXES)


def is_model_media(path):
    """
    True when the path belongs to an app that stores uploads through models.
    Matching by app, not only by the derived upload directory, keeps files
    written under an older directory layout under the same rules.
    """
    return path.split("/", 1)[0] in _model_app_labels()


def find_holders(path):
    """Records whose file field holds exactly this media path."""
    app_label = path.split("/", 1)[0]
    candidates = [
        (model, field_name)
        for model, field_name, prefix in _registry()
        if (prefix and path.startswith(prefix))
        or model._meta.app_label == app_label
        # Fields with no derivable prefix (upload_to="") store at the root.
        or (not prefix and "/" not in path)
    ]
    holders = []
    for model, field_name in dict.fromkeys(candidates):
        holders.extend(
            model._base_manager.filter(**{field_name: path})[:_MAX_RELATED_ROWS]
        )
    return holders


def _employee_fields(obj):
    """(field, is_many) for every employee link on the record."""
    for field in obj._meta.get_fields():
        if (
            field.concrete
            and field.related_model is not None
            and field.related_model._meta.label == "employee.Employee"
            and field.name not in _NON_PARTICIPANT_FIELDS
        ):
            yield field


def _participants(obj):
    """(field name, employee) for every employee linked to the record."""
    people = []
    for field in _employee_fields(obj):
        if field.many_to_many:
            rows = getattr(obj, field.name).all()[:_MAX_RELATED_ROWS]
            people.extend((field.name, employee) for employee in rows)
        else:
            employee = getattr(obj, field.name, None)
            if employee is not None:
                people.append((field.name, employee))
    return people


def _linked_objects(obj, include_reverse):
    """Records one step away from obj."""
    linked = []
    for field in obj._meta.get_fields():
        if field.auto_created and not field.concrete:  # reverse relation
            if not include_reverse:
                continue
            if not (field.one_to_many or field.many_to_many or field.one_to_one):
                continue
            if field.related_model._meta.label in _NON_OWNER_MODELS:
                continue
            accessor = field.get_accessor_name()
            if not accessor:
                continue
            try:
                related = getattr(obj, accessor)
                rows = (
                    list(related.all()[:_MAX_RELATED_ROWS])
                    if hasattr(related, "all")
                    else [related]
                )
            except Exception:
                continue
            linked.extend(rows)
        elif field.concrete and field.related_model is not None:
            if field.related_model._meta.label in _NON_OWNER_MODELS:
                continue
            if field.name in ("created_by", "modified_by"):
                continue
            if field.many_to_many:
                continue
            row = getattr(obj, field.name, None)
            if row is not None:
                linked.append(row)
    return linked


def _owner_records(holder):
    """
    The holder and the records it hangs from. Records pointing at the holder
    (a request that lists the file among its attachments) are followed from
    the holder only; foreign keys are followed a couple of links deep.
    """
    seen = {(holder._meta.label, holder.pk)}
    records = [holder]
    frontier = [holder]
    for depth in range(_MAX_DEPTH):
        next_frontier = []
        for obj in frontier:
            for row in _linked_objects(obj, include_reverse=depth == 0):
                key = (row._meta.label, row.pk)
                if key in seen:
                    continue
                seen.add(key)
                records.append(row)
                next_frontier.append(row)
        frontier = next_frontier
    return records


def _view_perm(obj):
    return f"{obj._meta.app_label}.view_{obj._meta.model_name}"


def _created_by_user(obj, user):
    created_by = getattr(obj, "created_by_id", None)
    return created_by is not None and created_by == getattr(user, "pk", None)


def user_can_access_holder(user, holder):
    employee = getattr(user, "employee_get", None)
    for record in _owner_records(holder):
        if user.has_perm(_view_perm(record)):
            return True
        if _created_by_user(record, user):
            return True
        if employee is None:
            continue
        for field_name, participant in _participants(record):
            if participant == employee:
                return True
            # The subject employee's reporting manager sees what they own.
            if field_name == "employee_id" and (
                participant.get_reporting_manager() == employee
            ):
                return True
    return False


def user_can_access_media(user, path):
    """
    Whether `user` may read the media file at `path` (relative to MEDIA_ROOT).
    """
    if user is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if is_open_media(path):
        return True
    if not is_model_media(path):
        # Not stored by any model: unchanged, any authenticated user.
        return True
    holders = find_holders(path)
    if not holders:
        # Under a model's upload directory but no record owns it any more.
        return False
    return any(user_can_access_holder(user, holder) for holder in holders)
