"""
The Assets page lists assets directly; the category is chosen (or created) in the form.

The page used to open grouped by category, so what it showed was a handful of
category headers with assets loaded under each, and the counts people compared it
against (the dashboard's total and warranty figures) did not line up with it. It now
opens as the plain list, with grouping by category one choice away, and an asset's
category is picked, or created, in the asset form itself.
"""

import re

from django.test import TestCase
from django.urls import reverse

from asset.cbv.asset_category import (
    AssetCategoryListView,
    AssetCategoryNav,
    AssetFormView,
    DynamicCreateAssetCategory,
)
from asset.models import Asset, AssetCategory
from horilla.testkit import make_company, make_employee, make_user

HX = {"HTTP_HX_REQUEST": "true"}


class AssetPageTests(TestCase):
    def setUp(self):
        self.user = make_user("assets-admin", password="pw", is_superuser=True)
        make_employee(
            company=make_company("Asset Co"),
            email="assets-admin@test.horilla",
            first_name="Asset",
            last_name="Admin",
            user=self.user,
        )
        self.client.force_login(self.user)

    def test_the_list_opens_grouped_by_category(self):
        self.assertEqual(AssetCategoryNav.default_group_by, "asset_category_id")

    def test_category_is_a_nested_grouping_level_on_the_nav_and_the_list(self):
        for view in (AssetCategoryNav, AssetCategoryListView):
            fields = [name for name, _label in view.nested_group_by_fields]
            self.assertIn("asset_category_id", fields, view)

    def test_the_old_accordion_grouping_is_gone(self):
        self.assertFalse(AssetCategoryNav.group_by_fields)
        self.assertFalse(getattr(AssetCategoryListView, "group_by_template_name", ""))

    def test_the_page_opens_even_with_no_categories(self):
        """The category can be created from the asset form, so the page must be reachable first."""
        self.assertFalse(AssetCategory.objects.exists())
        response = self.client.get(reverse("asset-category-view"))
        self.assertTemplateUsed(response, "category/asset_category_view.html")

    def test_the_form_offers_to_create_a_category(self):
        fields = [name for name, _view in AssetFormView.dynamic_create_fields]
        self.assertIn("asset_category_id", fields)
        self.assertTrue(DynamicCreateAssetCategory.is_dynamic_create_view)

    def test_the_form_shows_a_category_choice_for_a_new_asset(self):
        AssetCategory.objects.create(asset_category_name="Laptops")
        response = self.client.get(reverse("asset-creation-new"), **HX)
        html = response.content.decode()
        self.assertIn('name="asset_category_id"', html)
        self.assertNotIn('type="hidden" name="asset_category_id"', html)
        self.assertIn("Laptops", html)

    def test_an_asset_can_be_created_in_an_existing_category(self):
        category = AssetCategory.objects.create(asset_category_name="Laptops")
        self.client.get(reverse("asset-creation-new"), **HX)
        self.client.post(
            reverse("asset-creation-new"),
            {
                "asset_name": "Dell Latitude",
                "asset_description": "work laptop",
                "asset_tracking_id": "DELL-001",
                "asset_purchase_date": "2026-09-01",
                "asset_purchase_cost": "1000",
                "asset_status": "Available",
                "quantity": "1",
                "notify_before": "1",
                "asset_category_id": str(category.pk),
                "asset_lot_number_id": "",
            },
            **HX,
        )
        asset = Asset.objects.get(asset_tracking_id="DELL-001")
        self.assertEqual(asset.asset_category_id, category)

    def test_a_category_can_be_created_from_the_asset_form(self):
        self.client.get(reverse("asset-creation-new"), **HX)  # registers the route
        route = "dynamic-path-asset_category_id-" + self.client.session.session_key
        # By path, as the form's own button does: reverse() does not see a route that was
        # appended to the URL list after its cache was built.
        url = "/" + route + "?dynamic_field=asset_category_id"
        self.client.post(
            url,
            {
                "asset_category_name": "Brand New",
                "asset_category_description": "made from the asset form",
                "dynamic_field": "asset_category_id",
            },
            **HX,
        )
        self.assertTrue(
            AssetCategory.objects.filter(asset_category_name="Brand New").exists()
        )

    def test_the_per_category_add_asset_link_still_works_and_preselects(self):
        category = AssetCategory.objects.create(asset_category_name="Phones")
        response = self.client.get(reverse("asset-creation", args=[category.pk]), **HX)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        option = re.search(r'<option[^>]*value="%d"[^>]*>' % category.pk, html)
        self.assertIsNotNone(option, "the category is offered")
        self.assertIn("selected", option.group(0))


class DefaultGroupingTests(TestCase):
    """The default grouping is for opening the page on its own, not for a filtered link."""

    def setUp(self):
        user = make_user("assets-nav", password="pw", is_superuser=True)
        make_employee(
            company=make_company("Nav Co"),
            email="assets-nav@test.horilla",
            first_name="Nav",
            last_name="Admin",
            user=user,
        )
        self.client.force_login(user)

    def _groups_by_category(self, query=""):
        html = self.client.get(
            reverse("asset-category-nav") + query, **HX
        ).content.decode()
        return bool(re.search(r'value="asset_category_id"\s+selected', html))

    def test_opened_on_its_own_it_groups_by_category(self):
        self.assertTrue(self._groups_by_category())

    def test_a_dashboard_status_link_shows_just_the_filtered_assets(self):
        self.assertFalse(
            self._groups_by_category("?asset_status=In+use&filter_applied=1")
        )

    def test_a_dashboard_warranty_link_shows_just_the_filtered_assets(self):
        query = (
            "?expiry_date__gte=2026-10-06&expiry_date__lte=2026-11-05&filter_applied=1"
        )
        self.assertFalse(self._groups_by_category(query))

    def test_an_explicit_grouping_in_the_address_is_not_treated_as_a_filter(self):
        self.assertTrue(self._groups_by_category("?nested_fields=asset_category_id"))


class DashboardCountsMatchTheirListsTests(TestCase):
    """What a dashboard bar says and what the list it opens shows must be the same number."""

    def setUp(self):
        from asset.models import AssetAssignment

        self.AssetAssignment = AssetAssignment
        user = make_user("assets-dash", password="pw", is_superuser=True)
        self.employee = make_employee(
            company=make_company("Dash Co"),
            email="assets-dash@test.horilla",
            first_name="Dash",
            last_name="Admin",
            user=user,
        )
        self.client.force_login(user)
        self.category = AssetCategory.objects.create(asset_category_name="Laptops")
        self.assets = {}
        for n, status in enumerate(
            ["In use", "In use", "Available", "Not-Available"], start=1
        ):
            asset = Asset.objects.create(
                asset_name=f"Laptop {n}",
                asset_tracking_id=f"DASH-{n}",
                asset_purchase_date="2026-01-01",
                asset_purchase_cost=100,
                asset_category_id=self.category,
                quantity=1,
            )
            # Saving a new asset sets its own status; the one wanted is written after.
            Asset.objects.filter(pk=asset.pk).update(asset_status=status)
            self.assets[n] = asset

    def test_the_category_columns_add_up_to_the_category_total(self):
        data = self.client.get(reverse("asset-dashboard-category")).json()["categories"]
        row = next(c for c in data if c["category"] == "Laptops")
        self.assertEqual(
            (row["in_use"], row["available"], row["not_available"]), (2, 1, 1)
        )
        self.assertEqual(
            row["in_use"] + row["available"] + row["not_available"], row["total"]
        )

    def test_the_currently_held_filter_leaves_out_returned_assignments(self):
        from asset.filters import AssetAllocationFilter

        for asset in (self.assets[1], self.assets[2]):
            self.AssetAssignment.objects.create(
                asset_id=asset,
                assigned_to_employee_id=self.employee,
                assigned_by_employee_id=self.employee,
            )
        self.AssetAssignment.objects.filter(asset_id=self.assets[2]).update(
            return_status="Healthy", return_date="2026-02-01"
        )
        everything = AssetAllocationFilter(
            {}, queryset=self.AssetAssignment.objects.all()
        ).qs
        held = AssetAllocationFilter(
            {"held": "true"}, queryset=self.AssetAssignment.objects.all()
        ).qs
        self.assertEqual(everything.count(), 2)
        self.assertEqual(held.count(), 1)
