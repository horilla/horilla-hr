"""
horilla_views/generic/cbv/kanban.py
"""

import json

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.http import HttpResponse, JsonResponse

from horilla_views.cbv_methods import get_nested_field
from horilla_views.generic.cbv.views import HorillaCardView


class HorillaKanbanView(HorillaCardView):
    group_key: str = ""
    group_filter_class = None
    template_name: str = "generic/horilla_kanban_view.html"
    kanban_attrs: str = ""
    instance_order_by: str = "sequence"
    group_order_by: str = "sequence"
    records_per_page: int = 10
    custom_card_content_template: str = ""
    group_actions: list = []
    show_kanban_confirmation: bool = True
    folded_groups: list = []
    action_method: str = """"""
    group_label_key: str = ""

    def get_related_groups(self, *args, **kwargs):
        related_groups = self.group_filter_class(self.request.GET).qs
        return related_groups

    def has_kanban_change_permission(self) -> bool:
        """Whether the requesting user may regroup or reorder this board's records."""
        return True

    def get_kanban_group_field(self):
        """The field this board groups by, resolved from the view's own group_key."""
        return get_nested_field(self.model, self.group_key)

    def get_kanban_group_queryset(self):
        """Groups this board is allowed to assign records to, or None for choice groups."""
        related_model = getattr(self.get_kanban_group_field(), "related_model", None)
        if not related_model:
            return None
        if self.group_filter_class:
            return self.get_related_groups()
        return related_model._default_manager.all()

    def resolve_kanban_group(self, group_id):
        """Resolve a submitted group id against this board's own groups, or None."""
        if group_id in (None, ""):
            return None
        field = self.get_kanban_group_field()
        if getattr(field, "related_model", None):
            return self.get_kanban_group_queryset().filter(pk=group_id).first()
        choices = getattr(field, "choices", None)
        if choices:
            return (
                group_id
                if any(str(value) == str(group_id) for value, _ in choices)
                else None
            )
        return None

    def get_kanban_order(self, key="order"):
        """Record ids submitted by a drag-and-drop, in their new display order."""
        try:
            order = json.loads(self.request.POST.get(key, "[]"))
        except json.JSONDecodeError:
            return []
        return [str(pk) for pk in order if pk not in (None, "")]

    def assign_kanban_values(self, records, order, group=None):
        """Write the new sequence, and optionally the new group, onto the given records."""
        record_map = {str(record.pk): record for record in records}
        updated = 0
        for index, pk in enumerate(order):
            record = record_map.get(pk)
            if not record:
                continue
            assignments = [(self.instance_order_by, index)]
            if group is not None:
                assignments.append((self.group_key, group))
            targets = {}
            for path, value in assignments:
                parts = path.split("__")
                target = record
                for part in parts[:-1]:
                    target = getattr(target, part, None)
                if target is None:
                    continue
                setattr(target, parts[-1], value)
                targets[id(target)] = target
            for target in targets.values():
                target.save()
            updated += 1
        return updated

    def kanban_move_item(self):
        """Move the dragged record into a new group and resequence that column."""
        group = self.resolve_kanban_group(self.request.POST.get("groupId"))
        if group is None:
            return JsonResponse({"error": "Invalid group."}, status=400)
        order = self.get_kanban_order()
        if not order:
            return JsonResponse({"error": "Missing order."}, status=400)
        records = self.get_queryset().filter(pk__in=order)
        updated = self.assign_kanban_values(records, order, group=group)
        return JsonResponse({"status": "success", "updated": updated})

    def kanban_reorder_items(self):
        """Resequence records within a single column."""
        order = self.get_kanban_order()
        if not order:
            return JsonResponse({"error": "Missing order."}, status=400)
        records = self.get_queryset().filter(pk__in=order)
        updated = self.assign_kanban_values(records, order)
        return JsonResponse({"status": "success", "updated": updated})

    def kanban_reorder_groups(self):
        """Resequence the board's group columns."""
        groups = self.get_kanban_group_queryset()
        if groups is None:
            return JsonResponse({"info": "This board's groups cannot be reordered."})
        order = self.get_kanban_order("sequence")
        if not order:
            return JsonResponse({"error": "Missing sequence."}, status=400)
        group_map = {str(group.pk): group for group in groups.filter(pk__in=order)}
        updated = []
        for index, pk in enumerate(order):
            group = group_map.get(pk)
            if not group:
                continue
            setattr(group, self.group_order_by, index)
            updated.append(group)
        if updated:
            groups.model._default_manager.bulk_update(updated, [self.group_order_by])
        return JsonResponse({"status": "success", "updated": len(updated)})

    def kanban_card_count(self):
        """Card count for one column, matching the board's current filters."""
        group = self.resolve_kanban_group(self.request.GET.get("group_id"))
        if group is None:
            return HttpResponse("0")
        count = self.get_queryset().filter(**{self.group_key: group}).count()
        return HttpResponse(f"{count}")

    def get(self, request, *args, **kwargs):
        """Serve the board, or a single column's card count."""
        if request.GET.get("kanban_action") == "card-count":
            return self.kanban_card_count()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Handle drag-and-drop updates for this view's own model and group field."""
        handlers = {
            "move-item": self.kanban_move_item,
            "reorder-items": self.kanban_reorder_items,
            "reorder-groups": self.kanban_reorder_groups,
        }
        handler = handlers.get(request.POST.get("kanban_action"))
        if not handler:
            return JsonResponse({"error": "Unknown kanban action."}, status=400)
        if not self.has_kanban_change_permission():
            return JsonResponse({"error": "Permission denied."}, status=403)
        return handler()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        queryset = self.queryset

        app_label = self.model._meta.app_label if self.model else ""
        model_name = self.model.__name__ if self.model else ""
        context["app_label"] = app_label
        context["model_name"] = model_name
        context["tab_id"] = self.kwargs.get("pk", None)

        grouped_items = {}
        paginated_groups = {}

        try:
            field = get_nested_field(self.model, self.group_key)

            if isinstance(
                field, (models.ForeignKey, models.OneToOneField, models.OneToOneRel)
            ):
                queryset = queryset.prefetch_related(self.group_key)

                related_groups = []
                for obj in self.get_related_groups():
                    label = getattr(obj, self.group_label_key, str(obj))
                    related_groups.append(
                        {
                            "pk": obj.pk,
                            "label": str(label),
                            "instance": obj,
                        }
                    )

            elif hasattr(field, "choices") and field.choices:
                related_groups = [
                    {"pk": value, "label": str(label), "instance": value}
                    for value, label in field.choices
                ]
                context["is_choice_group"] = True

            else:
                related_groups = []

            # -------------------------
            # Group items
            # -------------------------
            for rg in related_groups:
                pk = rg["pk"]

                grouped_items[pk] = {
                    "label": rg["label"],
                    "instance": rg.get("instance"),
                    "items": queryset.filter(**{self.group_key: pk}),
                }

            # -------------------------
            # Sort groups (preserve order)
            # -------------------------
            sorted_items = {
                rg["pk"]: grouped_items[rg["pk"]]
                for rg in related_groups
                if rg["pk"] in grouped_items
            }

            # -------------------------
            # Paginate each group
            # -------------------------
            for key, group in sorted_items.items():
                try:
                    ordered_items = group["items"].order_by(self.instance_order_by)
                except Exception:
                    ordered_items = group["items"].order_by("pk")

                paginator = Paginator(ordered_items, self.records_per_page)
                page = self.request.GET.get(f"page_{key}", 1)

                try:
                    page_obj = paginator.page(page)
                except PageNotAnInteger:
                    page_obj = paginator.page(1)
                except EmptyPage:
                    page_obj = paginator.page(paginator.num_pages)

                paginated_groups[key] = {
                    "label": group["label"],
                    "instance": group.get("instance"),
                    "page_obj": page_obj,
                }
            context.update(
                {
                    "grouped_items": paginated_groups,
                    "actions": self.actions,
                    "filter_class": self.filter_class.__name__,
                    "group_by_field": self.group_key,
                    "kanban_attrs": self.kanban_attrs,
                }
            )

        except Exception as e:
            print(f"Error in KanbanViewItems: {e}")
            raise e

        return context
