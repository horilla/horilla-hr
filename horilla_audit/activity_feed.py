"""
Normalize simple-history / auditlog diffs into one activity-feed context.
"""

import html
import re
from datetime import timedelta

from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.translation import gettext as _


def history_action_phrase(changes, fallback=None):
    """Short activity-feed phrase from changed fields (e.g. 'updated department')."""
    if fallback:
        return fallback
    if not changes:
        return _("updated record")
    labels = [
        str(c.get("field_label") or c.get("field") or c.get("field_name") or "").strip()
        for c in changes
    ]
    labels = [label for label in labels if label]
    if not labels:
        return _("updated record")
    first = labels[0]
    if len(labels) == 1:
        return _("updated %(field)s") % {"field": first.lower()}
    if len(labels) == 2:
        return _("updated %(first)s and %(second)s") % {
            "first": first.lower(),
            "second": labels[1].lower(),
        }
    return _("updated %(field)s and %(count)s other fields") % {
        "field": first.lower(),
        "count": len(labels) - 1,
    }


def history_date_label(history_date, today=None):
    """Group header: Today / Yesterday / full date."""
    if history_date is None:
        return _("Unknown date")
    if timezone.is_aware(history_date):
        local_dt = timezone.localtime(history_date)
    else:
        local_dt = history_date
    day = local_dt.date() if hasattr(local_dt, "date") else local_dt
    today = today or timezone.localdate()
    if day == today:
        return _("Today")
    if day == today - timedelta(days=1):
        return _("Yesterday")
    return day.strftime("%b %d, %Y")


def _actor_name(updated_by):
    if updated_by is None:
        return _("Horilla Bot")
    if hasattr(updated_by, "get_full_name"):
        return updated_by.get_full_name() or str(updated_by)
    return str(updated_by) or _("Horilla Bot")


def _actor_avatar(updated_by):
    if updated_by is None:
        return "https://ui-avatars.com/api/?name=Horilla+Bot&background=random"
    getter = getattr(updated_by, "get_avatar", None)
    if callable(getter):
        return getter()
    return "https://ui-avatars.com/api/?name=Horilla+Bot&background=random"


_HTML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


def _plain_text(value):
    """
    Rich-text fields (summernote descriptions) are stored as HTML; the feed
    prints values as plain text, so show the text instead of the markup.
    """
    if not isinstance(value, str) or not _HTML_TAG_RE.search(value):
        return value
    text = html.unescape(strip_tags(value))
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return text or "—"


def _normalize_tracking_change(change):
    """Ensure change dict has labels/display values used by the feed template."""
    normalized = dict(change)
    label = (
        normalized.get("field_label")
        or normalized.get("field")
        or normalized.get("field_name")
        or ""
    )
    normalized["field_label"] = label
    if "old_value" not in normalized:
        old = normalized.get("old")
        normalized["old_value"] = "—" if old in (None, "") else str(old)
    if "new_value" not in normalized:
        new = normalized.get("new")
        normalized["new_value"] = "—" if new in (None, "") else str(new)
    normalized["old_value"] = _plain_text(normalized["old_value"])
    normalized["new_value"] = _plain_text(normalized["new_value"])
    return normalized


def normalize_tracking_entries(tracking):
    """Convert get_diff()-style tracking list into feed entries."""
    entries = []
    for history in tracking or []:
        changes = [
            _normalize_tracking_change(c) for c in (history.get("changes") or [])
        ]
        pair = history.get("pair")
        newer = pair[0] if pair else None
        history_date = getattr(newer, "history_date", None) if newer else None
        updated_by = history.get("updated_by")
        reason = None
        if newer is not None:
            reason = (
                getattr(newer, "history_title", None)
                or history.get("change_reason")
                or getattr(newer, "history_change_reason", None)
            )
        else:
            reason = history.get("change_reason")

        event_type = history.get("type") or ""
        history_type = getattr(newer, "history_type", None) if newer else None

        # Keep create/update snapshots even when there is no field-level diff.
        # Attendance and similar models often only store a single "~" row.
        if not changes:
            if event_type and event_type != "Changes":
                pass  # keep typed events like "Leave request created"
            elif history_type == "+":
                event_type = event_type or _("record created")
            elif history_type == "~" or event_type == "Changes":
                event_type = _("record updated")
            elif event_type:
                pass
            else:
                continue

        action_phrase = history_action_phrase(
            changes,
            fallback=(
                str(event_type).lower()
                if event_type and event_type != "Changes"
                else None
            ),
        )
        entries.append(
            {
                **history,
                "changes": changes,
                "history_date": history_date,
                "action_phrase": action_phrase,
                "actor_name": _actor_name(updated_by),
                "actor_avatar": _actor_avatar(updated_by),
                "reason": reason,
                "change_count": len(changes),
                "source": "tracking",
                "revert_history_id": (
                    getattr(pair[1], "pk", None)
                    if pair and len(pair) > 1 and pair[0] != pair[1]
                    else None
                ),
            }
        )
    return entries


class _AuditActor:
    """Minimal actor shape for auditlog entries in the shared feed."""

    def __init__(self, employee=None, name=None):
        self.employee = employee
        self.name = name or _("Horilla Bot")

    def get_full_name(self):
        if self.employee and hasattr(self.employee, "get_full_name"):
            return self.employee.get_full_name()
        return self.name

    def get_avatar(self):
        if self.employee and hasattr(self.employee, "get_avatar"):
            return self.employee.get_avatar()
        return f"https://ui-avatars.com/api/?name={self.name.replace(' ', '+')}&background=random"

    def __str__(self):
        return self.get_full_name()


def normalize_log_entries(log_entries):
    """Convert django-auditlog LogEntry queryset/list into feed entries."""
    entries = []
    for entry in log_entries or []:
        employee = None
        actor = getattr(entry, "actor", None)
        if actor is not None:
            employee = getattr(actor, "employee_get", None)
        updated_by = _AuditActor(employee=employee)

        changes = []
        display = getattr(entry, "changes_display_dict", None) or {}
        for field, values in display.items():
            if not values or values[0] == "type":
                continue
            old_val = _plain_text(values[0]) if len(values) > 0 else "—"
            new_val = _plain_text(values[1]) if len(values) > 1 else "—"
            changes.append(
                {
                    "field": field,
                    "field_label": field,
                    "field_name": field,
                    "is_fk": False,
                    "old_value": old_val,
                    "new_value": new_val,
                }
            )

        action = getattr(entry, "action", None)
        if action == 0:
            fallback = _("created record")
        elif action == 2:
            fallback = _("deleted record")
        else:
            fallback = None

        if not changes and fallback is None:
            continue

        entries.append(
            {
                "type": "Changes",
                "pair": None,
                "changes": changes,
                "updated_by": updated_by,
                "history_date": getattr(entry, "timestamp", None),
                "action_phrase": history_action_phrase(changes, fallback=fallback),
                "actor_name": _actor_name(updated_by),
                "actor_avatar": _actor_avatar(updated_by),
                "reason": None,
                "change_count": len(changes),
                "source": "auditlog",
                "revert_history_id": None,
                "object_pk": getattr(entry, "object_pk", None),
                "log_id": getattr(entry, "pk", None),
            }
        )
    return entries


def group_history_entries(entries):
    """Group normalized entries under Today / Yesterday / date labels."""
    today = timezone.localdate()
    grouped = {}
    group_order = []
    for entry in entries:
        label = history_date_label(entry.get("history_date"), today=today)
        if label not in grouped:
            grouped[label] = []
            group_order.append(label)
        grouped[label].append(entry)
    return [{"label": label, "entries": grouped[label]} for label in group_order]


def build_activity_history_feed(tracking=None, log_entries=None, entries=None):
    """
    Build the shared activity-history context used by templates / inclusion tags.
    Prefers simple-history tracking when present; otherwise uses auditlog entries.
    ``entries`` bypasses normalization for callers that already merged and
    normalized entries themselves (e.g. across several records of a model).
    """
    if entries is None:
        if tracking:
            entries = normalize_tracking_entries(tracking)
        else:
            entries = normalize_log_entries(log_entries)

    history_groups = group_history_entries(entries)
    return {
        "has_history": bool(entries),
        "history_groups": history_groups,
        "filtered_empty": False,
        "search": "",
    }
