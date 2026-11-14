"""The ledger of one asset, opened from the asset list."""

from typing import Any

from django.contrib import messages
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from asset.ledger import (
    KINDS,
    TONES,
    build_ledger,
    collect_entries,
    summarize,
    unit_summary,
)
from asset.models import Asset
from employee.models import Employee
from horilla.decorators import hx_request_required
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import login_required, permission_required

PAGE_SIZE = 20
PILLS = {
    "blue": "bg-blue-50 text-blue-700",
    "gray": "bg-gray-100 text-gray-600",
    "green": "bg-green-50 text-green-700",
    "amber": "bg-amber-50 text-amber-700",
    "violet": "bg-violet-50 text-violet-700",
    "sky": "bg-sky-50 text-sky-700",
}
CONDITION_PILLS = {
    "Healthy": "bg-green-50 text-green-700",
    "Minor damage": "bg-amber-50 text-amber-700",
    "Major damage": "bg-red-50 text-red-700",
    "Lost": "bg-gray-800 text-white",
}
CONDITION_LABELS = {
    "Healthy": _("Healthy"),
    "Minor damage": _("Minor Damage"),
    "Major damage": _("Major Damage"),
    "Lost": _("Lost"),
}
ICONS = {
    "unit": "cube-outline",
    "purchased": "pricetag-outline",
    "registered": "clipboard-outline",
    "allocated": "person-add-outline",
    "returned": "return-down-back-outline",
    "movement": "swap-horizontal-outline",
    "service": "construct-outline",
    "report": "document-text-outline",
    "warranty": "shield-checkmark-outline",
}
STATUS_PILLS = {
    "in_use": "bg-blue-50 text-blue-700",
    "available": "bg-green-50 text-green-700",
    "service": "bg-violet-50 text-violet-700",
    "damaged": "bg-red-50 text-red-700",
    "lost": "bg-red-50 text-red-700",
}
STATUS_LABELS = {
    "in_use": _("In Use"),
    "available": _("Available"),
    "service": _("Under Service"),
    "damaged": _("Damaged"),
    "lost": _("Lost"),
}


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(permission_required("asset.view_asset"), name="dispatch")
class AssetLedgerView(TemplateView):
    """Every event in an asset's life, with who holds it and its status after each one."""

    template_name = "cbv/asset_ledger/ledger.html"

    def get_template_names(self):
        """Scrolling to the end of the table asks for the next rows alone."""
        return (
            [self.rows_template]
            if self.request.GET.get("rows_only")
            else [self.template_name]
        )

    def get(self, request, *args, **kwargs):
        """An asset that is gone (deleted, or a stale row) gives a message and a reload, like the detail views."""
        if not Asset.objects.filter(pk=kwargs["pk"]).exists():
            messages.info(request, _("No Record Found..."))
            return HorillaRedirect(request)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        asset = Asset.objects.get(pk=self.kwargs["pk"])
        entries = collect_entries(asset)
        units = unit_summary(asset, entries)
        for unit in units["units"]:
            unit["status_label"] = STATUS_LABELS[unit["status"]]
        chosen_unit = self.request.GET.get("unit", "")
        unit = (
            int(chosen_unit)
            if chosen_unit.isdigit()
            and int(chosen_unit) in {u["pk"] for u in units["units"]}
            else None
        )
        ledger = build_ledger(asset, unit=unit, entries=entries)
        # With several units the table names each event's unit, so its columns follow that unit's own story.
        show_unit = len(units["units"]) > 1 and unit is None
        table_ledger = ledger
        if show_unit:
            own = {
                u["pk"]: {
                    e["uid"]: e
                    for e in build_ledger(asset, unit=u["pk"], entries=entries)
                }
                for u in units["units"]
            }
            table_ledger = [
                (
                    dict(
                        e,
                        holders=o["holders"],
                        holder_pks=o["holder_pks"],
                        status=o["status"],
                        units_total=None,
                        units_held=None,
                    )
                    if (o := own.get(e["item"], {}).get(e["uid"]))
                    else e
                )
                for e in ledger
            ]
        shown = ledger + table_ledger if show_unit else ledger
        # Who holds the asset is shown as a group of avatars, so the people behind each name are looked up once.
        pks = {pk for e in shown for pk in e["holder_pks"] if pk}
        people = {
            employee.pk: {
                "name": employee.get_full_name(),
                "avatar": employee.get_avatar(),
                "initials": "".join(
                    part[0] for part in employee.get_full_name().split()[:2]
                ).upper(),
            }
            for employee in Employee.objects.entire().filter(pk__in=pks)
        }
        serials = {u["pk"]: u["serial"] for u in units["units"]}
        for entry in shown:
            entry["icon"] = ICONS.get(entry["kind"], "ellipse-outline")
            entry["pill"] = PILLS[TONES.get(entry["kind"], "gray")]
            entry["status_label"] = STATUS_LABELS[entry["status"]]
            entry["status_pill"] = STATUS_PILLS[entry["status"]]
            entry["condition_label"] = CONDITION_LABELS.get(entry["condition"], "")
            entry["condition_pill"] = CONDITION_PILLS.get(entry["condition"], "")
            entry["unit_serial"] = serials.get(entry["item"], "")
            entry["unit_pk"] = entry["item"]
            entry["holder_people"] = [
                people.get(pk)
                or {"name": name, "avatar": "", "initials": name[:1].upper()}
                for name, pk in zip(entry["holders"], entry["holder_pks"])
            ]
        date_from = parse_date(self.request.GET.get("date_from", "") or "")
        date_to = parse_date(self.request.GET.get("date_to", "") or "")
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from
        in_range = [
            e
            for e in table_ledger
            if (not date_from or e["date"] >= date_from)
            and (not date_to or e["date"] <= date_to)
        ]
        counts = {
            key: sum(1 for e in in_range if e["kind"] == key) for key, _label in KINDS
        }
        chosen = [k for k in self.request.GET.getlist("kind") if k in counts]
        rows = [e for e in in_range if not chosen or e["kind"] in chosen]
        for entry in rows:
            entry["latest"] = False
        done = [e for e in rows if not e["future"]]
        if done:
            done[-1]["latest"] = True
        newest_first = self.request.GET.get("order", "desc") != "asc"
        if newest_first:
            rows = rows[::-1]
        # The line below each event leads to the next one shown, and is drawn as done only when both ends are past.
        for index, entry in enumerate(rows):
            entry["gap_future"] = entry["future"] or (
                index + 1 < len(rows) and rows[index + 1]["future"]
            )
        paginator = Paginator(rows, PAGE_SIZE)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        # The graphic needs one unit's story: a single-unit asset, or a unit picked from the list.
        single = units["total"] <= 1 or unit is not None
        view = (
            "timeline"
            if single and self.request.GET.get("view") == "timeline"
            else "table"
        )
        self.rows_template = "cbv/asset_ledger/%s.html" % (
            "timeline_items" if view == "timeline" else "rows"
        )
        summary = summarize(ledger, asset)
        summary["holder_people"] = ledger[-1]["holder_people"] if ledger else []
        summary["status_label"] = STATUS_LABELS[summary["status"]]
        summary["status_pill"] = STATUS_PILLS[summary["status"]]
        context.update(
            {
                "asset": asset,
                "rows": page_obj,
                "page_obj": page_obj,
                "total": len(in_range),
                "date_from": date_from,
                "date_to": date_to,
                "kinds": [
                    (key, label, counts[key]) for key, label in KINDS if counts[key]
                ],
                "chosen": chosen,
                "newest_first": newest_first,
                "summary": summary,
                "units": units,
                "single": single,
                "view": view,
                "views": [("table", _("Table")), ("timeline", _("Timeline"))],
                "unit": unit,
                "show_unit": show_unit,
                "unit_serial": next(
                    (u["serial"] for u in units["units"] if u["pk"] == unit), ""
                ),
            }
        )
        return context
