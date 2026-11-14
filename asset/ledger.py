"""The ledger of one asset: every event in its life in order, with who holds it and its status after each."""

from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from asset.models import AssetAssignment, AssetEvent, AssetReport

# Order of the event kinds, as filter chips and for counting.
KINDS = [
    ("purchased", _("Purchased")),
    ("registered", _("Registered")),
    ("allocated", _("Allocated")),
    ("returned", _("Returned")),
    ("movement", _("Movement")),
    ("service", _("Service")),
    ("report", _("Report")),
    ("warranty", _("Warranty")),
]

# The colour of an event's pill (a Tailwind colour name).
TONES = {
    "purchased": "blue",
    "registered": "gray",
    "unit": "gray",
    "allocated": "green",
    "returned": "amber",
    "movement": "amber",
    "service": "violet",
    "report": "sky",
    "warranty": "gray",
}


def _name(employee):
    """The full name of an employee, or an empty string."""
    return employee.get_full_name() if employee else ""


def _pk(employee):
    """The id of an employee, or None."""
    return employee.pk if employee else None


def _who(user):
    """The employee name behind a user, or an empty string."""
    return _name(getattr(user, "employee_get", None)) if user else ""


def _entry(day, seq, kind, label, **extra):
    """
    One ledger line. ``seq`` orders lines of the same day: an allocation, what happened under it and its
    return stay together and in that order, and a later allocation comes after an earlier return.
    """
    return {
        "date": day,
        "seq": seq,
        "kind": kind,
        "label": label,
        "detail": extra.get("detail", ""),
        "employee": extra.get("employee", ""),
        "employee_pk": extra.get("employee_pk"),
        "actor": extra.get("actor", ""),
        "amount": extra.get("amount"),
        "future": bool(extra.get("future")),
        "at": extra.get("at"),
        "holders_delta": extra.get("holders_delta", 0),
        "effect": extra.get("effect", ""),
        "assignment": extra.get("assignment"),
        "service": extra.get("service"),
        "item": extra.get("item"),
        "condition": extra.get("condition", ""),
        "note": extra.get("note", ""),
    }


def collect_entries(asset):
    """The events stored for the asset, not yet in order and without the running columns."""
    from django.utils import timezone

    today = timezone.localdate()
    entries = [
        _entry(
            asset.asset_purchase_date,
            -2,
            "purchased",
            _("Purchased"),
            detail=asset.asset_name,
            amount=asset.asset_purchase_cost,
            effect="available",
        )
    ]
    if asset.created_at:
        entries.append(
            _entry(
                timezone.localtime(asset.created_at).date(),
                -1,
                "registered",
                _("Registered"),
                detail=_("Added To The System"),
                actor=_who(asset.created_by),
                at=asset.created_at,
            )
        )
    items = list(asset.asset_items.order_by("pk"))
    item_pks = {item.pk for item in items}
    sole = items[0].pk if len(items) == 1 else None

    def unit_of(assignment):
        """The unit an allocation is of: its own, or the only one the asset has; None when it is not known."""
        return (
            assignment.asset_item_id_id
            if assignment.asset_item_id_id in item_pks
            else sole
        )

    units = {}
    if len(items) > 1:
        for item in items:
            entries.append(
                _entry(
                    (
                        timezone.localtime(item.created_at).date()
                        if item.created_at
                        else asset.asset_purchase_date
                    ),
                    -0.5,
                    "registered",
                    _("Unit Added"),
                    detail=item.tracking_id,
                    at=item.created_at,
                    item=item.pk,
                )
            )

    assignments = (
        AssetAssignment.objects.entire()
        .filter(asset_id=asset)
        .select_related(
            "assigned_to_employee_id", "assigned_by_employee_id", "asset_item_id"
        )
        .prefetch_related(
            "service_requests__notes__employee_id",
            "service_requests__resolved_by_employee_id",
        )
    )
    for assignment in assignments:
        base = assignment.pk * 2
        unit = units[assignment.pk] = unit_of(assignment)
        serial = (
            assignment.asset_item_id.tracking_id if assignment.asset_item_id_id else ""
        )
        entries.append(
            _entry(
                assignment.assigned_date,
                base,
                "allocated",
                _("Allocated"),
                detail=serial,
                employee=_name(assignment.assigned_to_employee_id),
                employee_pk=_pk(assignment.assigned_to_employee_id),
                actor=_name(assignment.assigned_by_employee_id),
                at=assignment.created_at,
                holders_delta=1,
                assignment=assignment.pk,
                item=unit,
                note=(
                    _("Returned On %(date)s")
                    % {"date": date_format(assignment.return_date, "d M Y")}
                    if assignment.return_date
                    else _("Currently Held")
                ),
            )
        )
        for request in assignment.service_requests.all():
            entries.append(
                _entry(
                    request.request_date,
                    base + 0.5,
                    "service",
                    _("Service Requested"),
                    detail=request.issue_description,
                    employee=_name(request.requested_employee_id),
                    employee_pk=_pk(request.requested_employee_id),
                    actor=_name(request.requested_employee_id),
                    at=request.created_at,
                    effect="service_open",
                    assignment=assignment.pk,
                    service=request.pk,
                    item=unit,
                )
            )
            if request.status in ("Completed", "Rejected") and request.resolved_date:
                entries.append(
                    _entry(
                        request.resolved_date,
                        base + 0.7,
                        "service",
                        (
                            _("Service Completed")
                            if request.status == "Completed"
                            else _("Service Rejected")
                        ),
                        detail=request.issue_description,
                        employee=_name(request.requested_employee_id),
                        employee_pk=_pk(request.requested_employee_id),
                        actor=_name(request.resolved_by_employee_id),
                        effect="service_closed",
                        assignment=assignment.pk,
                        service=request.pk,
                        item=unit,
                    )
                )
            for note in request.notes.all():
                entries.append(
                    _entry(
                        timezone.localtime(note.created_at).date(),
                        base + 0.6,
                        "service",
                        _("Service Note Added"),
                        detail=note.note,
                        employee=_name(request.requested_employee_id),
                        employee_pk=_pk(request.requested_employee_id),
                        actor=_name(note.employee_id),
                        at=note.created_at,
                        assignment=assignment.pk,
                        service=request.pk,
                        item=unit,
                    )
                )
        if assignment.return_date:
            days = max((assignment.return_date - assignment.assigned_date).days, 0)
            entries.append(
                _entry(
                    assignment.return_date,
                    base + 1,
                    "returned",
                    _("Returned"),
                    detail=" ".join(
                        part
                        for part in (serial, assignment.return_condition or "")
                        if part
                    ),
                    employee=_name(assignment.assigned_to_employee_id),
                    employee_pk=_pk(assignment.assigned_to_employee_id),
                    actor="",
                    holders_delta=-1,
                    effect={
                        "Minor damage": "damaged",
                        "Major damage": "damaged",
                        "Lost": "lost",
                    }.get(assignment.return_status, "returned"),
                    assignment=assignment.pk,
                    item=unit,
                    condition=assignment.return_status or "",
                    note=ngettext(
                        "Held For %(days)s Day", "Held For %(days)s Days", days
                    )
                    % {"days": days},
                )
            )

    returners = {}
    for event in AssetEvent.objects.filter(asset_id=asset).select_related(
        "employee_id", "assignment_id", "service_request_id", "created_by"
    ):
        base = (event.assignment_id_id or 0) * 2
        day = timezone.localtime(event.event_date).date()
        unit = units.get(event.assignment_id_id)
        if unit is None and event.assignment_id_id:
            unit = unit_of(event.assignment_id)
        if event.event_type == "returned_by":
            returners[event.assignment_id_id] = _who(event.created_by)
        elif event.event_type in ("reassigned_out", "reassigned_in"):
            outgoing = event.event_type == "reassigned_out"
            entries.append(
                _entry(
                    day,
                    base + (0.95 if outgoing else 0.05),
                    "movement",
                    event.get_event_type_display(),
                    detail=(_("To %(asset)s") if outgoing else _("From %(asset)s"))
                    % {"asset": event.description},
                    employee=_name(event.employee_id),
                    employee_pk=_pk(event.employee_id),
                    actor=_who(event.created_by),
                    at=event.event_date,
                    effect="out" if outgoing else "in",
                    assignment=event.assignment_id_id,
                    item=unit,
                )
            )
        elif event.event_type == "service_in_progress":
            request = event.service_request_id
            entries.append(
                _entry(
                    day,
                    base + 0.55,
                    "service",
                    event.get_event_type_display(),
                    detail=request.issue_description if request else "",
                    employee=_name(event.employee_id),
                    employee_pk=_pk(event.employee_id),
                    actor=_who(event.created_by),
                    at=event.event_date,
                    effect="service_open",
                    assignment=event.assignment_id_id,
                    service=event.service_request_id_id,
                    item=unit,
                )
            )
    for entry in entries:
        if entry["kind"] == "returned":
            entry["actor"] = returners.get(entry["assignment"], "")

    for report in AssetReport.objects.filter(asset_id=asset).prefetch_related(
        "documents"
    ):
        documents = report.documents.count()
        title = report.title or ""
        entries.append(
            _entry(
                (
                    timezone.localtime(report.created_at).date()
                    if report.created_at
                    else asset.asset_purchase_date
                ),
                10**9,
                "report",
                _("Report Added"),
                detail=f"{title} ({documents})".strip() if documents else title,
                actor=_who(report.created_by),
                at=report.created_at,
            )
        )
    if asset.expiry_date:
        entries.append(
            _entry(
                asset.expiry_date,
                10**9 + 1,
                "warranty",
                (
                    _("Warranty Expires")
                    if asset.expiry_date >= today
                    else _("Warranty Expired")
                ),
                future=asset.expiry_date > today,
            )
        )
    for uid, entry in enumerate(entries):
        entry["uid"] = uid
    return entries


def build_ledger(asset, unit=None, entries=None):
    """
    The asset's events oldest first, each with ``holders`` (who has it after the event) and ``status`` (what
    state it is in after the event). With ``unit`` (an asset item's id) only that unit's events and the
    asset's own (purchase, warranty, reports) are kept, and the running columns follow that one unit.
    ``entries`` is what ``collect_entries`` returned, when it is already at hand.
    """
    entries = collect_entries(asset) if entries is None else entries
    entries = [dict(e) for e in entries]
    if unit:
        entries = [
            e
            for e in entries
            if e["item"] == unit or (e["item"] is None and e["assignment"] is None)
        ]
    entries.sort(
        key=lambda e: (e["date"], e["seq"], e["at"].timestamp() if e["at"] else 0)
    )

    holders = {}
    open_service = set()
    removed = 0
    last_removed = ""
    # A unit that came back damaged or lost leaves the pool for good. Taking one out lowers the quantity, except
    # for the last unit, which leaves the asset Not-Available with its quantity unchanged.
    gone = sum(1 for e in entries if e["effect"] in ("damaged", "lost"))
    original = asset.quantity + gone
    if gone and asset.quantity == 1 and asset.asset_status == "Not-Available":
        original -= 1
    if unit:
        original = 1
    for entry in entries:
        key = entry["assignment"]
        if entry["kind"] == "allocated":
            holders[key] = (entry["employee"], entry["employee_pk"])
        elif entry["effect"] == "in":
            holders.setdefault(key, (entry["employee"], entry["employee_pk"]))
        elif entry["effect"] == "out":
            holders.pop(key, None)
        elif entry["kind"] == "returned":
            holders.pop(key, None)
            for service in [s for s in open_service if s[0] == key]:
                open_service.discard(service)
            if entry["effect"] in ("damaged", "lost"):
                removed += 1
                last_removed = entry["effect"]
        if entry["effect"] == "service_open":
            open_service.add((key, entry["service"]))
        elif entry["effect"] == "service_closed":
            open_service.discard((key, entry["service"]))

        entry["holders"] = [who for who, _ in holders.values()]
        entry["holder_pks"] = [pk for _, pk in holders.values()]
        entry["open_services"] = len(open_service)
        entry["status"] = _status(
            holders, open_service, removed, last_removed, original
        )
        # With several units the asset is In Use only once every unit still in the pool is held.
        entry["units_total"] = original if original > 1 else None
        entry["units_held"] = len(holders)
    return entries


def _status(holders, open_service, removed, last_removed, total):
    """The state after an event: In Use, Under Service, Damaged, Lost or Available."""
    if open_service:
        return "service"
    if holders:
        return "in_use" if len(holders) >= total - removed else "available"
    if removed and removed >= total:
        return last_removed
    return "available"


def summarize(ledger, asset):
    """Figures for the strip above the ledger."""
    services = {e["service"] for e in ledger if e["service"]}
    last = ledger[-1] if ledger else None
    return {
        "status": last["status"] if last else "available",
        "holders": last["holders"] if last else [],
        "holder_pks": last["holder_pks"] if last else [],
        "allocations": sum(1 for e in ledger if e["kind"] == "allocated"),
        "services": len(services),
        "open_services": last["open_services"] if last else 0,
        "units_total": last["units_total"] if last else None,
        "units_held": last["units_held"] if last else 0,
        "cost": asset.asset_purchase_cost,
    }


def unit_summary(asset, entries):
    """
    How many units the asset has and how many are in use, available, damaged or lost, each worked out from
    that unit's own history. ``units`` lists them with their serial number and state.
    """
    items = list(asset.asset_items.order_by("pk"))
    counts = {"in_use": 0, "available": 0, "damaged": 0, "lost": 0}
    units = []
    for item in items:
        state = build_ledger(asset, unit=item.pk, entries=entries)[-1]["status"]
        if state == "service":
            state = "in_use"
        # A unit marked damaged or lost on the unit itself stays so, unless someone holds it.
        if state == "available" and item.status in ("Damaged", "Lost"):
            state = item.status.lower()
        counts[state] += 1
        units.append({"pk": item.pk, "serial": item.tracking_id, "status": state})

    # Allocations that name no unit on an asset with several: they take their units from the available ones.
    if len(items) > 1:
        held = {}
        for entry in sorted(entries, key=lambda e: (e["date"], e["seq"])):
            if entry["assignment"] is None or entry["item"] is not None:
                continue
            if entry["kind"] == "allocated":
                held[entry["assignment"]] = "in_use"
            elif entry["kind"] == "returned":
                held[entry["assignment"]] = (
                    entry["effect"] if entry["effect"] in ("damaged", "lost") else None
                )
        for state in held.values():
            if state and counts["available"]:
                counts["available"] -= 1
                counts[state] += 1
    if not items:
        counts["available"] = asset.quantity
    return {"total": len(items) or asset.quantity, **counts, "units": units}
