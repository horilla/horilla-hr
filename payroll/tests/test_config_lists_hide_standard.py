"""The Allowances and Deductions lists in Configuration leave out the standard, always applied items."""

import re

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import Allowance, Deduction

HX = {"HTTP_HX_REQUEST": "true"}


class ConfigurationListsTests(TestCase):
    def setUp(self):
        user = make_user("listsadmin", is_superuser=True)
        make_employee(
            company=make_company("Lists Co"), email="lists@test.horilla", user=user
        )
        self.client.force_login(user)
        Allowance.objects.create(title="Plain Allowance Row", is_fixed=True, amount=10)
        Deduction.objects.create(title="Plain Deduction Row", is_fixed=True, amount=10)
        self.standard_allowance = (
            Allowance.objects.entire().filter(is_system=True).first()
        )
        self.standard_deduction = (
            Deduction.objects.entire().filter(is_system=True).first()
        )

    def _body(self, name):
        return self.client.get(reverse(name), **HX).content.decode()

    @staticmethod
    def _shown(body, title):
        """Whether a cell of the list reads exactly ``title``."""
        return re.search(r">\s*" + re.escape(title) + r"\s*<", body) is not None

    def test_the_standard_items_exist_to_be_hidden(self):
        self.assertIsNotNone(self.standard_allowance)
        self.assertIsNotNone(self.standard_deduction)

    def test_the_allowance_lists_hide_the_standard_items_and_keep_the_rest(self):
        for name in ("allowances-list-view", "allowances-card-view"):
            body = self._body(name)
            self.assertTrue(self._shown(body, "Plain Allowance Row"), name)
            self.assertFalse(self._shown(body, self.standard_allowance.title), name)

    def test_the_deduction_lists_hide_the_standard_items_and_keep_the_rest(self):
        for name in ("deduction-view-list", "deduction-view-card"):
            body = self._body(name)
            self.assertTrue(self._shown(body, "Plain Deduction Row"), name)
            self.assertFalse(self._shown(body, self.standard_deduction.title), name)

    def test_every_standard_item_is_hidden_not_just_one(self):
        body = self._body("allowances-list-view")
        for item in Allowance.objects.entire().filter(is_system=True):
            self.assertFalse(self._shown(body, item.title), item.title)
        body = self._body("deduction-view-list")
        for item in Deduction.objects.entire().filter(is_system=True):
            self.assertFalse(self._shown(body, item.title), item.title)


class AlwaysAppliedTabTests(TestCase):
    """The Always Applied tab lists the standard earnings and deductions together."""

    def setUp(self):
        user = make_user("aaadmin", is_superuser=True)
        make_employee(
            company=make_company("Always Co"), email="always@test.horilla", user=user
        )
        self.client.force_login(user)

    def _get(self, name):
        return self.client.get(reverse(name), **HX).content.decode()

    def test_the_tab_lists_every_standard_earning_and_deduction_in_one_table(self):
        html = self._get("payroll-settings-always-applied-tab")
        self.assertIn('data-always-applied="all"', html)
        for item in Allowance.objects.entire().filter(is_system=True):
            self.assertIn(f">{item.title}</span>", html)
        for item in Deduction.objects.entire().filter(is_system=True):
            self.assertIn(f">{item.title}</span>", html)
        self.assertIn('data-always-applied-kind="allowance"', html)
        self.assertIn('data-always-applied-kind="deduction"', html)
        self.assertIn("Earning", html)
        self.assertIn("Pre-Tax Deduction", html)

    def test_the_earnings_come_before_the_deductions(self):
        html = self._get("payroll-settings-always-applied-tab")
        self.assertLess(
            html.index('data-always-applied-kind="allowance"'),
            html.index('data-always-applied-kind="deduction"'),
        )

    def test_each_row_has_the_edit_link_for_its_tax_treatment(self):
        html = self._get("payroll-settings-always-applied-tab")
        earning = Allowance.objects.entire().filter(is_system=True).first()
        deduction = Deduction.objects.entire().filter(is_system=True).first()
        self.assertIn(reverse("update-allowance", args=[earning.pk]), html)
        self.assertIn(reverse("update-deduction", args=[deduction.pk]), html)

    def test_the_edit_opens_in_the_standard_modal_not_inline(self):
        html = self._get("payroll-settings-always-applied-tab")
        self.assertIn('hx-target="#objectCreateModalTarget"', html)
        self.assertIn('data-target="#objectCreateModal"', html)
        self.assertNotIn('hx-target="#alwaysAppliedContainer"', html)

    def test_there_is_no_action_column_and_each_row_opens_its_own_edit(self):
        html = self._get("payroll-settings-always-applied-tab")
        self.assertNotIn("Actions", html)
        self.assertNotIn("create-outline", html)
        rows = re.findall(r"<tr data-always-applied-kind=.*?>", html, flags=re.S)
        from payroll.system_components import SYSTEM_COMPONENTS

        self.assertEqual(len(rows), len(SYSTEM_COMPONENTS))
        for row in rows:
            self.assertIn("hx-get=", row)
            self.assertIn('data-target="#objectCreateModal"', row)

    def test_the_tab_has_the_nav_bar_with_search_only(self):
        html = self._get("payroll-settings-always-applied-tab")
        self.assertIn("bg-[#f3f3f3]", html)
        self.assertRegex(html, r"<span>\s*Always Applied\s*</span>")
        self.assertIn('id="alwaysAppliedSearch"', html)
        for control in ("Filter", "Create", "Actions"):
            self.assertNotRegex(html, r">\s*" + control + r"\s*<", control)

    def test_saving_an_edit_has_a_reload_hook_for_the_tab(self):
        html = self._get("payroll-settings-always-applied-tab")
        self.assertIn('id="applyFilter"', html)
        self.assertIn(reverse("payroll-settings-always-applied-tab"), html)

    def test_an_ordinary_component_is_not_in_the_tab(self):
        Allowance.objects.create(title="Ordinary Pay Row", is_fixed=True, amount=10)
        Deduction.objects.create(
            title="Ordinary Deduction Row", is_fixed=True, amount=10
        )
        html = self._get("payroll-settings-always-applied-tab")
        self.assertNotIn(">Ordinary Pay Row</span>", html)
        self.assertNotIn(">Ordinary Deduction Row</span>", html)

    def test_the_allowances_and_deductions_tabs_no_longer_carry_the_section(self):
        for name in (
            "payroll-settings-allowance-tab",
            "payroll-settings-deduction-tab",
        ):
            self.assertNotIn("data-always-applied", self._get(name), name)

    def test_the_tab_bar_has_the_tab_with_the_count_of_its_rows(self):
        from payroll.cbv.settings_tabs import all_always_applied_rows

        html = self._get("payroll-settings-tab-view")
        self.assertIn("Always Applied", html)
        self.assertIn(reverse("payroll-settings-always-applied-tab"), html)
        self.assertGreater(len(all_always_applied_rows()), 0)


class ListColumnTests(TestCase):
    """The Allowances and Deductions lists read the way the components are now configured."""

    def setUp(self):
        user = make_user("colsadmin", is_superuser=True)
        make_employee(
            company=make_company("Cols Co"), email="cols@test.horilla", user=user
        )
        self.client.force_login(user)

    def _body(self, name):
        return self.client.get(reverse(name), **HX).content.decode()

    def test_the_allowance_list_has_the_new_columns_and_none_of_the_old(self):
        body = self._body("allowances-list-view")
        for heading in ("Allowance", "Code", "Taxable", "Calculation", "Applied To"):
            self.assertRegex(body, r">\s*" + heading + r"\s*<", heading)
        for gone in ("Condition", "Condition Based", "Based On", "Rate"):
            self.assertNotRegex(body, r">\s*" + gone + r"\s*<", gone)

    def test_the_deduction_list_has_the_new_columns_and_none_of_the_old(self):
        body = self._body("deduction-view-list")
        for heading in ("Deduction", "Code", "Type", "Calculation", "Applied To"):
            self.assertRegex(body, r">\s*" + heading + r"\s*<", heading)
        for gone in ("Condition", "Condition Based", "Based On", "Rate"):
            self.assertNotRegex(body, r">\s*" + gone + r"\s*<", gone)

    def test_a_calculation_reads_as_one_line(self):
        fixed = Allowance.objects.create(title="Cols Fixed", is_fixed=True, amount=300)
        percent = Allowance.objects.create(
            title="Cols Percent", is_fixed=False, based_on="basic_pay", rate=40
        )
        self.assertEqual(fixed.get_calculation_col(), "300.00")
        self.assertEqual(percent.get_calculation_col(), "40% of BASIC")

    def test_applied_to_names_who_it_reaches(self):
        company = make_company("Applied Co")
        adam = make_employee(company=company, email="adam-applied@test.horilla")
        everyone = Allowance.objects.create(
            title="Cols Everyone",
            is_fixed=True,
            amount=1,
            include_active_employees=True,
        )
        picked = Allowance.objects.create(title="Cols Picked", is_fixed=True, amount=1)
        picked.specific_employees.add(adam)
        nobody = Allowance.objects.create(title="Cols Nobody", is_fixed=True, amount=1)
        self.assertEqual(everyone.get_applied_to_col(), "Everyone")
        everyone.exclude_employees.add(adam)
        self.assertEqual(everyone.get_applied_to_col(), "Everyone Except 1")
        self.assertEqual(picked.get_applied_to_col(), "1 Employee")
        self.assertEqual(nobody.get_applied_to_col(), "—")

    def test_applied_to_names_the_group_it_is_limited_to(self):
        from base.models import Department

        sales, _ = Department.objects.get_or_create(department="Cols Sales")
        rule = Deduction.objects.create(
            title="Cols Group", is_fixed=True, amount=1, apply_by="department"
        )
        rule.apply_departments.add(sales)
        self.assertEqual(rule.get_applied_to_col(), "Department: Cols Sales")

    def test_a_deduction_type_uses_the_global_terms(self):
        tax = Deduction.objects.create(
            title="Cols Tax", is_fixed=True, amount=1, is_tax=True
        )
        pre = Deduction.objects.create(
            title="Cols Pre", is_fixed=True, amount=1, is_pretax=True
        )
        post = Deduction.objects.create(
            title="Cols Post", is_fixed=True, amount=1, is_pretax=False
        )
        self.assertEqual(
            [
                str(tax.get_type_col()),
                str(pre.get_type_col()),
                str(post.get_type_col()),
            ],
            ["Tax", "Pre-Tax Deduction", "Deduction"],
        )
