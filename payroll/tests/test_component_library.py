"""
The ready-made component library.

Every payroll department builds the same dozen components by hand and gets the
same details slightly wrong — the rate, the base it applies to, whether it
comes off before tax. These check that what the library creates is actually
usable by the engine, not merely that rows exist: a library entry that produces
a component the engine cannot compute would be worse than no library, because
it looks authoritative.
"""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.component_library import COMPONENT_LIBRARY, library_rows, load_components
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Allowance, Contract, Deduction
from payroll.tests.factories_payroll import (
    PERIOD_END,
    PERIOD_START,
    make_active_contract,
)

EMPTY_LEAVES = {
    "paid_leave": 0,
    "unpaid_leaves": 0,
    "partial_pay_days": 0,
    "total_leaves": 0,
    "paid_leave_dates": [],
    "unpaid_leave_dates": [],
    "custom_leave_dates": [],
    "custom_leave_breakdown": [],
    "leave_dates": [],
}


class LibraryDataTests(TestCase):
    def test_every_entry_has_what_the_chooser_shows(self):
        for entry in COMPONENT_LIBRARY:
            with self.subTest(key=entry["key"]):
                self.assertTrue(entry["name"])
                self.assertTrue(entry["summary"])
                self.assertIn(entry["kind"], ("allowance", "deduction"))
                self.assertTrue(entry["fields"])

    def test_keys_are_unique(self):
        keys = [entry["key"] for entry in COMPONENT_LIBRARY]
        self.assertEqual(len(keys), len(set(keys)))

    def test_names_are_unique(self):
        """Loading is idempotent on title, so two entries sharing one would
        mean the second could never be created."""
        names = [entry["name"].lower() for entry in COMPONENT_LIBRARY]
        self.assertEqual(len(names), len(set(names)))

    def test_every_entry_creates_a_component_the_engine_can_describe(self):
        """
        A library entry that produced something unconfigured would look
        authoritative and pay nothing.
        """
        from payroll.methods.component_summary import calculation_summary

        load_components()
        for entry in COMPONENT_LIBRARY:
            with self.subTest(key=entry["key"]):
                model = Allowance if entry["kind"] == "allowance" else Deduction
                component = model.objects.get(title=entry["name"])
                self.assertNotEqual(calculation_summary(component), "Not configured")

    def test_a_percentage_entry_always_carries_a_rate(self):
        """Without one the component silently pays zero."""
        for entry in COMPONENT_LIBRARY:
            fields = entry["fields"]
            if fields.get("is_fixed") or fields.get("based_on") in (
                None,
                "balance",
                "formula",
            ):
                continue
            with self.subTest(key=entry["key"]):
                self.assertTrue(fields.get("rate"), entry["key"])

    def test_a_fixed_entry_always_carries_an_amount(self):
        for entry in COMPONENT_LIBRARY:
            if not entry["fields"].get("is_fixed"):
                continue
            with self.subTest(key=entry["key"]):
                self.assertTrue(entry["fields"].get("amount"))

    def test_only_one_entry_claims_to_be_basic_pay(self):
        """Two would be refused by the structure form, so the library must not
        be the thing that creates that situation."""
        basics = [
            entry for entry in COMPONENT_LIBRARY if entry["fields"].get("is_basic_pay")
        ]
        self.assertEqual(len(basics), 1)


class LoadingTests(TestCase):
    def test_loading_creates_the_chosen_components(self):
        created = load_components(["in_hra", "in_pf"])
        self.assertEqual(len(created), 2)
        self.assertTrue(
            Allowance.objects.filter(title="House Rent Allowance (HRA)").exists()
        )
        self.assertTrue(Deduction.objects.filter(title="Provident Fund (PF)").exists())

    def test_loading_twice_creates_nothing_the_second_time(self):
        load_components(["in_pf"])
        self.assertEqual(load_components(["in_pf"]), [])
        self.assertEqual(
            Deduction.objects.filter(title="Provident Fund (PF)").count(), 1
        )

    def test_an_existing_component_of_the_same_name_is_left_alone(self):
        """
        Someone's own Provident Fund, with their own rate, must not be
        duplicated or overwritten by a library entry.
        """
        mine = Deduction.objects.create(
            title="Provident Fund (PF)", is_fixed=True, amount=999.0
        )
        load_components(["in_pf"])

        mine.refresh_from_db()
        self.assertEqual(mine.amount, 999.0)
        self.assertEqual(
            Deduction.objects.filter(title="Provident Fund (PF)").count(), 1
        )

    def test_rows_flag_what_already_exists(self):
        self.assertFalse(any(row["already_loaded"] for row in library_rows()))
        load_components(["in_hra"])
        rows = {
            row["key"]: row["already_loaded"]
            for row in library_rows(
                set(Allowance.objects.values_list("title", flat=True))
            )
        }
        self.assertTrue(rows["in_hra"])
        self.assertFalse(rows["in_pf"])


class LoadedComponentsComputeTests(TestCase):
    """
    The library's components, run through the real engine — which is the only
    way to know a written-down rate actually produces a figure.
    """

    def setUp(self):
        company = make_company("Lib Co")
        self.employee = make_employee(company=company, email="lib@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=30000.0)

    def _run(self):
        def months(wage, *_a, **_kw):
            return [
                {
                    "working_days_on_period": 22,
                    "working_days_on_month": 22,
                    "days": 30,
                    "start_date": "2026-04-01",
                    "end_date": "2026-04-30",
                    "per_day_amount": float(wage or 0) / 22,
                }
            ]

        with patch(
            "payroll.methods.methods.months_between_range", side_effect=months
        ), patch(
            "payroll.methods.methods.get_daily_salary",
            return_value={"day_wage": 1000.0},
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES
        ):
            return payroll_calculation(self.employee, PERIOD_START, PERIOD_END)

    def test_hra_pays_half_of_basic(self):
        [hra] = load_components(["in_hra"])
        hra.specific_employees.add(self.employee)

        line = next(
            l
            for l in self._run()["allowances"]
            if l["title"] == "House Rent Allowance (HRA)"
        )
        self.assertAlmostEqual(line["amount"], 15000.0, places=2)

    def test_esi_drops_out_above_its_ceiling(self):
        """
        The rule is the point of that entry: above 21,000 gross the employee is
        outside the scheme, not merely capped.
        """
        [esi] = load_components(["in_esi"])
        esi.specific_employees.add(self.employee)

        data = self._run()
        amounts = [
            line["amount"]
            for bucket in ("pretax_deductions", "post_tax_deductions")
            for line in data[bucket]
            if line["title"] == "Employee State Insurance (ESI)"
        ]
        # Gross is 30,000 here, so the ceiling excludes it.
        self.assertEqual(amounts, [0])

    def test_professional_tax_is_the_same_in_every_period(self):
        [pt] = load_components(["in_pt"])
        pt.specific_employees.add(self.employee)

        line = next(
            l
            for l in self._run()["pretax_deductions"]
            if l["title"] == "Professional Tax"
        )
        self.assertEqual(line["amount"], 200.0)


class LibraryViewTests(TestCase):
    def setUp(self):
        user = make_user("libadmin", is_superuser=True)
        company = make_company("Lib View Co")
        make_employee(company=company, email="libadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

    def test_the_picker_lists_every_entry(self):
        response = self.client.get(reverse("component-library"), **self.hx)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for entry in COMPONENT_LIBRARY:
            self.assertIn(entry["name"], body)

    def test_loading_through_the_view_creates_them(self):
        response = self.client.post(
            reverse("load-component-library"),
            {"components": ["in_hra", "us_401k"]},
            **self.hx,
        )
        self.assertIn(response.status_code, (200, 302))
        self.assertTrue(
            Allowance.objects.filter(title="House Rent Allowance (HRA)").exists()
        )
        self.assertTrue(Deduction.objects.filter(title="401(k) Contribution").exists())

    def test_choosing_nothing_creates_nothing(self):
        self.client.post(reverse("load-component-library"), {}, **self.hx)
        # The standard pay items are always present -- seeded on migrate --
        # so "nothing was created" has to be counted without them.
        self.assertEqual(Allowance.objects.exclude(is_system=True).count(), 0)
        self.assertEqual(Deduction.objects.exclude(is_system=True).count(), 0)

    def test_both_component_pages_offer_the_library(self):
        """
        The library is only worth having if it can be reached: everything
        below it worked for a while with nothing on screen linking to it.
        """
        for nav_name in ("allowances-nav-view", "deduction-view-nav"):
            with self.subTest(nav=nav_name):
                body = self.client.get(reverse(nav_name), **self.hx).content.decode()
                self.assertIn(reverse("component-library"), body)
                self.assertIn("Add from library", body)

    def test_the_nav_tells_the_chooser_which_page_opened_it(self):
        """
        Four pages share these two navs, so the nav is the only thing that
        knows where the user actually is.
        """
        for nav_name, expected in (
            ("allowances-nav-view", "from=allowance"),
            ("deduction-view-nav", "from=deduction"),
        ):
            with self.subTest(nav=nav_name):
                body = self.client.get(reverse(nav_name), **self.hx).content.decode()
                self.assertIn(expected, body)

        # The payroll-settings tabs say so, and get themselves back.
        body = self.client.get(
            reverse("deduction-view-nav"), {"from": "settings"}, **self.hx
        ).content.decode()
        self.assertIn("from=settings", body)

    def test_loading_from_a_settings_tab_returns_to_the_settings_page(self):
        response = self.client.post(
            reverse("load-component-library"),
            {"components": ["in_pf"], "return_to": "settings"},
        )
        target = response.headers.get("HX-Redirect") or response.headers.get("Location")
        self.assertEqual(target, reverse("payroll-settings-view"))

    def test_loading_returns_to_the_page_it_was_opened_from(self):
        """
        Both pages open the same chooser, so without this a deduction loaded
        from the Deductions page landed the user on Allowances.
        """
        response = self.client.post(
            reverse("load-component-library"),
            {"components": ["in_pf"], "return_to": "deduction"},
        )
        target = response.headers.get("HX-Redirect") or response.headers.get("Location")
        self.assertEqual(target, reverse("view-deduction"))

    def test_an_unknown_return_page_falls_back_rather_than_redirecting_to_it(self):
        """The field is posted, so it must not be reversible into anywhere."""
        response = self.client.post(
            reverse("load-component-library"),
            {"components": ["in_pf"], "return_to": "https://example.com/"},
        )
        target = response.headers.get("HX-Redirect") or response.headers.get("Location")
        self.assertEqual(target, reverse("view-allowance"))


class PickerModalTests(TestCase):
    """
    The two "start from something ready-made" choosers — components and tax
    configurations — are the same interaction and now share one design.

    The component one shipped with no close button at all, leaving Escape or a
    click outside as the only way out of it, which is the kind of thing only a
    rendered check catches.
    """

    def setUp(self):
        user = make_user("pickadmin", is_superuser=True)
        company = make_company("Pick Co")
        make_employee(company=company, email="pickadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

    def _bodies(self):
        return {
            "components": self.client.get(
                reverse("component-library"), **self.hx
            ).content.decode(),
            "tax": self.client.get(
                "/payroll/tax-pack-picker/", **self.hx
            ).content.decode(),
        }

    def test_both_can_be_closed(self):
        for name, body in self._bodies().items():
            with self.subTest(modal=name):
                self.assertIn("oh-modal__close--custom", body)
                self.assertIn("close-outline", body)
                # And a Cancel, for the same reason.
                self.assertIn("Cancel", body)

    def test_both_use_the_shared_design(self):
        for name, body in self._bodies().items():
            with self.subTest(modal=name):
                self.assertIn("pick__row", body)
                self.assertIn("pick__caveat", body)
                self.assertIn("pick__foot", body)

    def test_both_group_their_rows_rather_than_columning_the_region(self):
        """
        Country as a column left the descriptions fighting for what width
        remained; as a heading it costs nothing.
        """
        for name, body in self._bodies().items():
            with self.subTest(modal=name):
                self.assertIn("pick__group", body)

    def test_both_say_that_nothing_is_overwritten(self):
        for name, body in self._bodies().items():
            with self.subTest(modal=name):
                self.assertIn("Nothing is overwritten", body)


class LibraryPermissionTests(TestCase):
    """
    The chooser creates allowances and deductions from one list, so it takes
    both permissions — otherwise it is a way to create the kind you are not
    allowed to create.
    """

    def setUp(self):
        self.user = make_user("halfperms")
        company = make_company("Half Co")
        make_employee(company=company, email="halfperms@test.horilla", user=self.user)
        self.client.force_login(self.user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

    def _grant(self, *codenames):
        from django.contrib.auth.models import Permission

        self.user.user_permissions.add(
            *Permission.objects.filter(codename__in=codenames)
        )

    def test_only_the_allowance_permission_is_not_enough(self):
        """
        Asserted on content, not status: handle_no_permission renders the
        denial page with a 200 for an HTMX request, so a status check would
        pass whether or not the decorator fired.
        """
        self._grant("add_allowance")
        response = self.client.get(reverse("component-library"), **self.hx)
        self.assertNotIn("Provident Fund (PF)", response.content.decode())

    def test_only_the_allowance_permission_cannot_load(self):
        self._grant("add_allowance")
        self.client.post(
            reverse("load-component-library"), {"components": ["in_pf"]}, **self.hx
        )
        # Excluding the standard pay items, which are seeded on every migrate
        # and so are never a sign that something was created here.
        self.assertFalse(Deduction.objects.exclude(is_system=True).exists())

    def test_both_permissions_open_it(self):
        self._grant("add_allowance", "add_deduction")
        response = self.client.get(reverse("component-library"), **self.hx)
        self.assertEqual(response.status_code, 200)
