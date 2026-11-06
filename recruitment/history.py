"""
Aggregated history for one candidate, used by the candidate profile History tab.

Mirrors ``employee/history.py``: the same feed entries, model picker, date
range, sort, search and "view selected" behaviour, over the models that hold a
change history for a candidate.
"""

from datetime import date

from django.apps import apps
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from employee.history import (
    MAX_RECORDS_PER_MODEL,
    build_model_history,
    entry_search_text,
    filter_and_sort_entries,
)

# (app_label, model_name, lookup that ties a row to the candidate, label).
# Only models that record a change history are listed, so every choice in the
# picker has something to show.
CANDIDATE_HISTORY_MODELS = [
    ("recruitment", "candidate", "pk", _("Application")),
    ("recruitment", "rejectedcandidate", "candidate_id", _("Rejection")),
    ("onboarding", "candidatetask", "candidate_id", _("Onboarding Task")),
]

DEFAULT_MODEL = "recruitment.candidate"


def get_candidate_history_models():
    """[{key, label, model, lookup}] for each model that can be picked."""
    options = []
    for app_label, model_name, lookup, label in CANDIDATE_HISTORY_MODELS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        options.append(
            {
                "key": f"{app_label}.{model_name}",
                "label": label,
                "model": model,
                "lookup": lookup,
            }
        )
    return options


def get_candidate_model_history(
    candidate, model_key, date_from=None, date_to=None, sort="-date"
):
    """``(entries, tracking_status)`` for ``model_key`` rows of ``candidate``."""
    option = next(
        (o for o in get_candidate_history_models() if o["key"] == model_key), None
    )
    if option is None:
        return [], "none"
    model = option["model"]
    value = candidate.pk if option["lookup"] == "pk" else candidate
    rows = list(
        model._base_manager.filter(**{option["lookup"]: value})
        .distinct()
        .order_by("-pk")[:MAX_RECORDS_PER_MODEL]
    )
    entries, tracking_status = build_model_history(
        model, model_key, option["label"], rows
    )
    return (
        filter_and_sort_entries(entries, date_from, date_to, sort),
        tracking_status,
    )


def get_candidate_entries_by_keys(candidate, keys, sort="-date"):
    """Entries picked by ``entry_key`` across models, merged into one feed."""
    allowed = {o["key"] for o in get_candidate_history_models()}
    wanted = {}
    for key in keys:
        model_key = key.split("|", 1)[0]
        if model_key in allowed:
            wanted.setdefault(model_key, set()).add(key)

    selected = []
    for model_key, model_keys in wanted.items():
        model_entries, _status = get_candidate_model_history(
            candidate, model_key, sort=sort
        )
        selected.extend(e for e in model_entries if e.get("entry_key") in model_keys)

    selected.sort(
        key=lambda e: e["history_date"] or timezone.now(), reverse=sort != "date"
    )
    return selected


def get_candidate_history_search(
    candidate, model_options, search, date_from=None, date_to=None, sort="-date"
):
    """Entries from every given model whose text contains the search phrase."""
    phrase = search.lower()
    matched = []
    for option in model_options:
        model_entries, tracking_status = get_candidate_model_history(
            candidate, option["key"], date_from=date_from, date_to=date_to, sort=sort
        )
        if tracking_status == "none":
            continue
        matched.extend(e for e in model_entries if phrase in entry_search_text(e))

    matched.sort(
        key=lambda e: e["history_date"] or timezone.now(), reverse=sort != "date"
    )
    return matched


def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def build_candidate_history_context(request, candidate):
    """Template context for the candidate History tab, read from ``request.GET``."""
    model_options = get_candidate_history_models()
    selected_model = request.GET.get("model") or DEFAULT_MODEL
    if selected_model not in {m["key"] for m in model_options}:
        selected_model = DEFAULT_MODEL

    date_from = _parse_date(request.GET.get("date_from"))
    date_to = _parse_date(request.GET.get("date_to"))
    sort = request.GET.get("sort") or "-date"
    if sort not in {"date", "-date"}:
        sort = "-date"

    search = (request.GET.get("search") or "").strip()
    selected_view = request.GET.get("view") == "selected"
    if selected_view:
        entries = get_candidate_entries_by_keys(
            candidate, request.GET.getlist("selected"), sort=sort
        )
        tracking_status = "simple_history"
    elif search:
        entries = get_candidate_history_search(
            candidate,
            model_options,
            search,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
        )
        tracking_status = "simple_history"
    else:
        entries, tracking_status = get_candidate_model_history(
            candidate,
            selected_model,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
        )

    return {
        "selected_view": selected_view,
        "search": search,
        "candidate": candidate,
        "model_options": model_options,
        "selected_model": selected_model,
        "date_from": date_from,
        "date_to": date_to,
        "sort": sort,
        "entries": entries,
        "tracking_status": tracking_status,
    }
