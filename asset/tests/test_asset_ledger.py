"""The lifecycle of one asset: its events in order, with who holds it and its state after each."""

import base64

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from asset.ledger import build_ledger, collect_entries, summarize, unit_summary
from asset.models import (
    Asset,
    AssetAssignment,
    AssetCategory,
    AssetServiceRequest,
    AssetServiceRequestNote,
)
from horilla.testkit import make_company, make_employee, make_user

HX = {"HTTP_HX_REQUEST": "true"}
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class Fixture(TestCase):
    def setUp(self):
        self.user = make_user("ledger-admin", password="pw", is_superuser=True)
        company = make_company("Ledger Co")
        self.first = make_employee(
            company=company,
            email="ledger-admin@test.horilla",
            first_name="Ada",
            last_name="Admin",
            user=self.user,
        )
        self.second = make_employee(
            company=company,
            email="ledger-two@test.horilla",
            first_name="Ben",
            last_name="Second",
        )
        self.client.force_login(self.user)
        category = AssetCategory.objects.create(asset_category_name="Laptops")
        self.asset = Asset.objects.create(
            asset_name="Laptop",
            asset_tracking_id="LED-1",
            asset_purchase_date="2026-01-01",
            asset_purchase_cost=900,
            asset_category_id=category,
            quantity=1,
        )
        Asset.objects.filter(pk=self.asset.pk).update(created_at="2026-01-02T09:00:00Z")
        self.asset.refresh_from_db()

    def allocate(
        self,
        to,
        day,
        returned=None,
        status="Healthy",
        condition=None,
        asset=None,
        item=None,
    ):
        """An allocation on a given day, returned on another if asked."""
        assignment = AssetAssignment.objects.create(
            asset_id=asset or self.asset,
            assigned_to_employee_id=to,
            assigned_by_employee_id=self.first,
            asset_item_id=item,
        )
        AssetAssignment.objects.filter(pk=assignment.pk).update(
            assigned_date=day,
            return_date=returned,
            return_status=status if returned else None,
            return_condition=condition,
        )
        return assignment


class LedgerOrderTests(Fixture):
    def test_events_run_in_order_with_the_state_after_each(self):
        self.allocate(self.first, "2026-02-01", returned="2026-03-01")
        second = self.allocate(
            self.second,
            "2026-03-10",
            returned="2026-04-01",
            status="Major damage",
            condition="Cracked",
        )
        request = AssetServiceRequest.objects.create(
            assignment_id=second,
            requested_employee_id=self.second,
            issue_description="Slow",
        )
        AssetServiceRequest.objects.filter(pk=request.pk).update(
            request_date="2026-03-15",
            status="Completed",
            resolved_date="2026-03-20",
            resolved_by_employee_id=self.first,
        )
        note = AssetServiceRequestNote.objects.create(
            request_id=request, employee_id=self.first, note="Reset"
        )
        AssetServiceRequestNote.objects.filter(pk=note.pk).update(
            created_at="2026-03-16T10:00:00Z"
        )
        # What the return form does to the only unit of an asset that comes back damaged.
        Asset.objects.filter(pk=self.asset.pk).update(asset_status="Not-Available")
        self.asset.refresh_from_db()
        ledger = build_ledger(self.asset)
        sequence = [(str(e["label"]), e["status"]) for e in ledger]
        self.assertEqual(
            sequence,
            [
                ("Purchased", "available"),
                ("Registered", "available"),
                ("Allocated", "in_use"),
                ("Returned", "available"),
                ("Allocated", "in_use"),
                ("Service Requested", "service"),
                ("Service Note Added", "service"),
                ("Service Completed", "in_use"),
                ("Returned", "damaged"),
            ],
        )
        self.assertEqual(
            [e["employee"] for e in ledger if e["kind"] == "allocated"],
            ["Ada Admin", "Ben Second"],
        )
        self.assertEqual(
            [e["holders"] for e in ledger][-3:], [["Ben Second"], ["Ben Second"], []]
        )

    def test_returns_are_marked_with_their_condition_and_the_allocations_with_their_return(
        self,
    ):
        self.allocate(
            self.first,
            "2026-02-01",
            returned="2026-03-01",
            status="Major damage",
            condition="Cracked",
        )
        self.allocate(self.second, "2026-03-05")
        ledger = build_ledger(self.asset)
        returned = next(e for e in ledger if e["kind"] == "returned")
        self.assertEqual(
            (returned["condition"], str(returned["note"]), returned["detail"]),
            ("Major damage", "Held For 28 Days", "Cracked"),
        )
        notes = [str(e["note"]) for e in ledger if e["kind"] == "allocated"]
        self.assertEqual(notes, ["Returned On 01 Mar 2026", "Currently Held"])

    def test_a_return_on_the_day_of_the_next_allocation_comes_before_it(self):
        self.allocate(self.first, "2026-02-01", returned="2026-03-01")
        self.allocate(self.second, "2026-03-01")
        labels = [
            str(e["label"])
            for e in build_ledger(self.asset)
            if e["date"].isoformat() == "2026-03-01"
        ]
        self.assertEqual(labels, ["Returned", "Allocated"])

    def test_the_summary_reports_the_holder_and_the_open_service(self):
        assignment = self.allocate(self.second, "2026-02-01")
        request = AssetServiceRequest.objects.create(
            assignment_id=assignment,
            requested_employee_id=self.second,
            issue_description="Noisy",
        )
        AssetServiceRequest.objects.filter(pk=request.pk).update(
            request_date="2026-02-05"
        )
        summary = summarize(build_ledger(self.asset), self.asset)
        self.assertEqual(
            (summary["status"], summary["holders"]), ("service", ["Ben Second"])
        )
        self.assertEqual(
            (summary["allocations"], summary["services"], summary["open_services"]),
            (1, 1, 1),
        )

    def test_a_returned_asset_closes_its_open_service_request(self):
        assignment = self.allocate(self.second, "2026-02-01", returned="2026-02-10")
        request = AssetServiceRequest.objects.create(
            assignment_id=assignment,
            requested_employee_id=self.second,
            issue_description="Noisy",
            status="Returned",
        )
        AssetServiceRequest.objects.filter(pk=request.pk).update(
            request_date="2026-02-05"
        )
        summary = summarize(build_ledger(self.asset), self.asset)
        self.assertEqual(
            (summary["status"], summary["open_services"], summary["holders"]),
            ("available", 0, []),
        )

    def test_a_warranty_in_the_future_is_marked_as_not_yet_happened(self):
        Asset.objects.filter(pk=self.asset.pk).update(expiry_date="2099-01-01")
        self.asset.refresh_from_db()
        last = build_ledger(self.asset)[-1]
        self.assertEqual(
            (str(last["label"]), last["future"]), ("Warranty Expires", True)
        )


class LedgerEventTests(Fixture):
    """What the other tables do not keep is logged when it happens, and the ledger merges it in."""

    def second_asset(self):
        other = Asset.objects.create(
            asset_name="Laptop 2",
            asset_tracking_id="LED-2",
            asset_purchase_date="2026-01-01",
            asset_purchase_cost=800,
            asset_category_id=self.asset.asset_category_id,
            quantity=1,
        )
        other.refresh_from_db()
        return other

    def test_reassigning_shows_on_both_assets(self):
        other = self.second_asset()
        assignment = self.allocate(self.second, "2026-02-01")
        response = self.client.post(
            reverse("asset-reassign", kwargs={"pk": assignment.pk}),
            {"asset_id": other.pk},
            **HX,
        )
        self.assertEqual(response.status_code, 200)
        old = [
            (str(e["label"]), e["holders"])
            for e in build_ledger(self.asset)
            if e["kind"] == "movement"
        ]
        new = [
            (str(e["label"]), e["holders"])
            for e in build_ledger(other)
            if e["kind"] == "movement"
        ]
        self.assertEqual(old, [("Reassigned Out", [])])
        self.assertEqual(new, [("Reassigned In", ["Ben Second"])])
        moved = next(e for e in build_ledger(self.asset) if e["kind"] == "movement")
        self.assertIn("LED-2", str(moved["detail"]))

    def test_taking_a_service_request_in_hand_is_a_line_of_its_own(self):
        assignment = self.allocate(self.second, "2026-02-01")
        request = AssetServiceRequest.objects.create(
            assignment_id=assignment,
            requested_employee_id=self.second,
            issue_description="Noisy",
        )
        AssetServiceRequest.objects.filter(pk=request.pk).update(
            request_date="2026-02-05"
        )
        self.client.post(
            reverse("asset-service-request-detail-view", kwargs={"pk": request.pk}),
            {"status": "In Progress"},
            **HX,
        )
        labels = [
            str(e["label"]) for e in build_ledger(self.asset) if e["kind"] == "service"
        ]
        self.assertEqual(labels, ["Service Requested", "Service In Progress"])
        self.assertEqual(build_ledger(self.asset)[-1]["status"], "service")

    def test_the_return_names_who_processed_it(self):
        assignment = self.allocate(self.second, "2026-02-01")
        response = self.client.post(
            reverse("asset-allocate-return", kwargs={"assignment_id": assignment.pk}),
            {
                "return_date": "2026-03-01",
                "return_status": "Healthy",
                "return_condition": "Fine",
                "return_images": SimpleUploadedFile(
                    "back.png", PNG, content_type="image/png"
                ),
            },
            **HX,
        )
        errors = (
            response.context["asset_return_form"].errors if response.context else None
        )
        self.assertFalse(errors, errors)
        returned = next(e for e in build_ledger(self.asset) if e["kind"] == "returned")
        self.assertEqual(returned["actor"], str(self.user.employee_get.get_full_name()))


class LedgerUnitTests(Fixture):
    """An asset with several units: the summary counts them and the ledger can follow one."""

    def setUp(self):
        super().setUp()
        self.pool = Asset.objects.create(
            asset_name="Phone",
            asset_tracking_id="PH-1",
            asset_purchase_date="2026-01-01",
            asset_purchase_cost=300,
            asset_category_id=self.asset.asset_category_id,
            quantity=4,
        )
        self.pool.refresh_from_db()
        self.units = list(self.pool.asset_items.order_by("pk"))

    def test_the_summary_counts_each_unit_by_its_own_history(self):
        self.allocate(self.first, "2026-02-01", asset=self.pool, item=self.units[0])
        self.allocate(
            self.first,
            "2026-02-01",
            returned="2026-03-01",
            status="Major damage",
            asset=self.pool,
            item=self.units[1],
        )
        self.allocate(
            self.second,
            "2026-02-01",
            returned="2026-03-01",
            status="Lost",
            asset=self.pool,
            item=self.units[2],
        )
        summary = unit_summary(self.pool, collect_entries(self.pool))
        self.assertEqual(
            (
                summary["total"],
                summary["in_use"],
                summary["available"],
                summary["damaged"],
                summary["lost"],
            ),
            (4, 1, 1, 1, 1),
        )
        self.assertEqual(
            [u["status"] for u in summary["units"]],
            ["in_use", "damaged", "lost", "available"],
        )

    def test_an_allocation_that_names_no_unit_takes_one_from_the_available(self):
        self.allocate(self.first, "2026-02-01", asset=self.pool)
        summary = unit_summary(self.pool, collect_entries(self.pool))
        self.assertEqual((summary["in_use"], summary["available"]), (1, 3))

    def test_an_asset_with_several_units_is_in_use_only_when_every_unit_is_held(self):
        for unit in self.units[:3]:
            self.allocate(self.first, "2026-02-01", asset=self.pool, item=unit)
        last = build_ledger(self.pool)[-1]
        self.assertEqual(
            (last["status"], last["units_held"], last["units_total"]),
            ("available", 3, 4),
        )
        self.allocate(self.second, "2026-02-02", asset=self.pool, item=self.units[3])
        self.assertEqual(build_ledger(self.pool)[-1]["status"], "in_use")

    def test_a_single_unit_asset_is_a_total_of_one(self):
        self.allocate(self.first, "2026-02-01")
        summary = unit_summary(self.asset, collect_entries(self.asset))
        self.assertEqual(
            (summary["total"], summary["in_use"], summary["available"]), (1, 1, 0)
        )

    def test_following_one_unit_keeps_its_events_and_the_assets_own(self):
        self.allocate(
            self.first,
            "2026-02-01",
            returned="2026-03-01",
            asset=self.pool,
            item=self.units[0],
        )
        self.allocate(self.second, "2026-02-02", asset=self.pool, item=self.units[1])
        ledger = build_ledger(self.pool, unit=self.units[0].pk)
        allocated = [e["employee"] for e in ledger if e["kind"] == "allocated"]
        self.assertEqual(allocated, ["Ada Admin"])
        self.assertIn("purchased", [e["kind"] for e in ledger])
        self.assertEqual(ledger[-1]["status"], "available")
        other = build_ledger(self.pool, unit=self.units[1].pk)
        self.assertEqual(other[-1]["status"], "in_use")

    def test_the_modal_offers_the_units_and_follows_the_chosen_one(self):
        self.allocate(self.first, "2026-02-01", asset=self.pool, item=self.units[0])
        self.allocate(self.second, "2026-02-02", asset=self.pool, item=self.units[1])
        url = reverse("asset-ledger", kwargs={"pk": self.pool.pk})
        html = self.client.get(url, **HX).content.decode()
        self.assertIn("All Units", html)
        self.assertIn(self.units[1].tracking_id, html)
        rows = self.client.get(url + f"?unit={self.units[1].pk}", **HX).context["rows"]
        self.assertEqual(
            [e["employee"] for e in rows if e["kind"] == "allocated"], ["Ben Second"]
        )
        self.assertEqual(
            self.client.get(url + "?unit=999999", **HX).context["unit"], None
        )

    def test_a_single_unit_asset_has_no_unit_choice(self):
        html = self.client.get(
            reverse("asset-ledger", kwargs={"pk": self.asset.pk}), **HX
        ).content.decode()
        self.assertNotIn("All Units", html)
        self.assertIn("Total Units", html)


class LedgerViewTests(Fixture):
    def url(self):
        return reverse("asset-ledger", kwargs={"pk": self.asset.pk})

    def test_the_modal_shows_the_figures_and_the_events(self):
        self.allocate(self.first, "2026-02-01")
        html = self.client.get(self.url(), **HX).content.decode()
        for text in (
            "Asset Lifecycle",
            "LED-1",
            "Times Allocated",
            "Allocated",
            "Ada Admin",
            "Purchased",
        ):
            self.assertIn(text, html)

    def test_the_modal_marks_a_return_with_its_condition(self):
        self.allocate(self.first, "2026-02-01", returned="2026-03-01", status="Lost")
        html = self.client.get(self.url(), **HX).content.decode()
        for text in ("Returned", "Lost", "Held For 28 Days", "Returned On 01 Mar 2026"):
            self.assertIn(text, html)

    def test_the_newest_event_comes_first_unless_oldest_is_asked_for(self):
        self.allocate(self.first, "2026-02-01")
        newest = self.client.get(self.url(), **HX).context["rows"]
        oldest = self.client.get(self.url() + "?order=asc", **HX).context["rows"]
        self.assertEqual(
            [str(e["label"]) for e in newest], [str(e["label"]) for e in oldest][::-1]
        )

    def test_a_chosen_kind_leaves_out_the_others(self):
        self.allocate(self.first, "2026-02-01", returned="2026-03-01")
        rows = self.client.get(self.url() + "?kind=returned", **HX).context["rows"]
        self.assertEqual([str(e["label"]) for e in rows], ["Returned"])

    def test_the_timeline_lists_the_events_down_a_line_with_the_latest_marked(self):
        self.allocate(self.first, "2026-02-01", returned="2026-03-01")
        self.allocate(self.second, "2026-03-10")
        response = self.client.get(self.url() + "?view=timeline&order=asc", **HX)
        self.assertEqual(response.context["view"], "timeline")
        self.assertTemplateUsed(response, "cbv/asset_ledger/timeline_items.html")
        rows = list(response.context["rows"])
        self.assertEqual([e["latest"] for e in rows].count(True), 1)
        self.assertTrue(
            [e for e in rows if e["latest"]][0]["date"] <= timezone.localdate()
        )
        self.assertTrue(all(e["icon"] for e in rows))
        self.assertContains(response, "Ben Second")
        more = self.client.get(self.url() + "?view=timeline&rows_only=1", **HX)
        self.assertTemplateUsed(more, "cbv/asset_ledger/timeline_items.html")
        self.assertNotContains(more, "<table")

    def test_who_holds_the_asset_is_shown_as_an_avatar_group(self):
        self.allocate(self.first, "2026-02-01")
        response = self.client.get(self.url(), **HX)
        people = response.context["summary"]["holder_people"]
        self.assertEqual(
            [(p["name"], p["initials"]) for p in people], [("Ada Admin", "AA")]
        )
        self.assertTrue(people[0]["avatar"])
        self.assertContains(
            response, '<div class="inline-flex items-center" data-holders>'
        )
        self.assertNotContains(response, '<button type="button" data-holders-toggle')

    def test_a_quantity_asset_names_the_unit_of_each_event(self):
        pool = Asset.objects.create(
            asset_name="Phone",
            asset_tracking_id="PH-3",
            asset_purchase_date="2026-01-01",
            asset_purchase_cost=300,
            asset_category_id=self.asset.asset_category_id,
            quantity=3,
        )
        unit = pool.asset_items.order_by("pk").first()
        AssetAssignment.objects.create(
            asset_id=pool,
            asset_item_id=unit,
            assigned_to_employee_id=self.first,
            assigned_by_employee_id=self.first,
        )
        url = reverse("asset-ledger", kwargs={"pk": pool.pk})
        response = self.client.get(url, **HX)
        self.assertTrue(response.context["show_unit"])
        self.assertContains(response, ">Unit</th>")
        self.assertIn(
            unit.tracking_id, [e["unit_serial"] for e in response.context["rows"]]
        )
        self.assertContains(response, "hx-vals='{\"unit\": %d}'" % unit.pk)
        other = pool.asset_items.order_by("pk").last()
        AssetAssignment.objects.create(
            asset_id=pool,
            asset_item_id=other,
            assigned_to_employee_id=self.second,
            assigned_by_employee_id=self.first,
        )
        rows = self.client.get(url, **HX).context["rows"]
        # Each unit's rows show only its own holder, not everyone who holds the asset.
        self.assertEqual(
            {e["unit_serial"]: e["holders"] for e in rows if e["kind"] == "allocated"},
            {unit.tracking_id: ["Ada Admin"], other.tracking_id: ["Ben Second"]},
        )
        one = self.client.get(url + f"?unit={unit.pk}", **HX)
        self.assertFalse(one.context["show_unit"])
        self.assertFalse(self.client.get(self.url(), **HX).context["show_unit"])

    def test_the_toggle_is_offered_for_one_unit_only(self):
        html = self.client.get(self.url(), **HX).content.decode()
        self.assertIn('name="view"', html)
        pool = Asset.objects.create(
            asset_name="Phone",
            asset_tracking_id="PH-2",
            asset_purchase_date="2026-01-01",
            asset_purchase_cost=300,
            asset_category_id=self.asset.asset_category_id,
            quantity=3,
        )
        url = reverse("asset-ledger", kwargs={"pk": pool.pk})
        everything = self.client.get(url + "?view=timeline", **HX)
        self.assertEqual(everything.context["view"], "table")
        self.assertNotIn('name="view"', everything.content.decode())
        unit = pool.asset_items.first()
        one = self.client.get(url + f"?view=timeline&unit={unit.pk}", **HX)
        self.assertEqual(one.context["view"], "timeline")
        self.assertIn('name="view"', one.content.decode())

    def test_events_load_in_pages_as_the_table_is_scrolled(self):
        for month in range(1, 13):
            self.allocate(
                self.first, f"2026-{month:02d}-01", returned=f"2026-{month:02d}-20"
            )
        response = self.client.get(self.url(), **HX)
        page = response.context["page_obj"]
        self.assertEqual(
            (
                len(response.context["rows"]),
                page.paginator.count,
                page.paginator.num_pages,
            ),
            (20, 26, 2),
        )
        self.assertContains(response, "26 Events In Total")
        self.assertContains(response, "rows_only")
        more = self.client.get(self.url() + "?page=2&rows_only=1", **HX)
        self.assertEqual(len(more.context["rows"]), 6)
        self.assertNotContains(more, "<table")
        self.assertNotContains(more, "rows_only")

    def test_paging_keeps_the_chosen_kind_and_a_page_past_the_end_shows_the_last(self):
        for month in range(1, 13):
            self.allocate(
                self.first, f"2026-{month:02d}-01", returned=f"2026-{month:02d}-20"
            )
        context = self.client.get(self.url() + "?kind=returned&page=99", **HX).context
        self.assertEqual(
            (context["page_obj"].paginator.count, context["page_obj"].number), (12, 1)
        )
        self.assertTrue(all(str(e["label"]) == "Returned" for e in context["rows"]))

    def test_a_date_range_keeps_only_the_events_inside_it(self):
        self.allocate(self.first, "2026-02-01", returned="2026-03-01")
        self.allocate(self.second, "2026-05-01", returned="2026-06-01")
        context = self.client.get(
            self.url() + "?date_from=2026-04-01&date_to=2026-07-01", **HX
        ).context
        self.assertEqual(
            [(str(e["label"]), e["date"].isoformat()) for e in context["rows"]][::-1],
            [("Allocated", "2026-05-01"), ("Returned", "2026-06-01")],
        )
        self.assertEqual(context["total"], 2)
        self.assertEqual(
            dict((k, c) for k, _l, c in context["kinds"]),
            {"allocated": 1, "returned": 1},
        )
        self.assertEqual(context["summary"]["allocations"], 2)

    def test_a_range_given_the_wrong_way_round_is_swapped_and_a_bad_date_is_ignored(
        self,
    ):
        self.allocate(self.first, "2026-02-01")
        swapped = self.client.get(
            self.url() + "?date_from=2026-12-01&date_to=2026-01-01", **HX
        ).context
        self.assertEqual(
            (swapped["date_from"].isoformat(), swapped["date_to"].isoformat()),
            ("2026-01-01", "2026-12-01"),
        )
        ignored = self.client.get(self.url() + "?date_from=nonsense", **HX).context
        self.assertEqual((ignored["date_from"], ignored["total"]), (None, 3))

    def test_the_timeline_follows_the_date_range(self):
        self.allocate(self.first, "2026-02-01", returned="2026-06-01")
        context = self.client.get(
            self.url() + "?view=timeline&date_from=2026-03-01&date_to=2026-04-01", **HX
        ).context
        self.assertEqual(list(context["rows"]), [])
        empty = self.client.get(
            self.url() + "?view=timeline&date_from=2099-01-01&date_to=2099-02-01", **HX
        )
        self.assertContains(empty, "No Events Match The Chosen Filters.")

    def test_the_date_inputs_are_in_the_controls(self):
        html = self.client.get(
            self.url() + "?date_from=2026-01-01", **HX
        ).content.decode()
        self.assertIn('name="date_from" value="2026-01-01"', html)
        self.assertIn('name="date_to"', html)
        self.assertIn("Clear Dates", html)

    def test_an_asset_that_is_gone_gives_a_message_not_an_error(self):
        response = self.client.get(
            reverse("asset-ledger", kwargs={"pk": self.asset.pk + 999}), **HX
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Asset Lifecycle", response.content.decode())

    def test_someone_without_the_permission_is_refused(self):
        plain = make_user("ledger-plain", password="pw")
        make_employee(
            company=make_company("Plain Co"),
            email="plain@test.horilla",
            first_name="P",
            last_name="Q",
            user=plain,
        )
        self.client.force_login(plain)
        response = self.client.get(self.url(), **HX)
        self.assertTemplateUsed(response, "decorator_404.html")
        self.assertNotIn("Asset Lifecycle", response.content.decode())

    def test_the_asset_list_offers_the_ledger_on_each_row(self):
        response = self.client.get(
            reverse("asset-list", kwargs={"cat_id": self.asset.asset_category_id_id}),
            **HX,
        )
        self.assertContains(response, str(self.asset.ledger_url()))
