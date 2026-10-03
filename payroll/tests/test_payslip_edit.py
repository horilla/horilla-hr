"""
Editing a generated payslip's components, by hand.

A payslip is a record once it exists, and correcting it should not mean
touching the shared Allowance/Deduction definitions everyone else's payslip
reads from -- these tests build a real payslip through the real engine, then
check that editing it only ever changes its own stored snapshot.

The arithmetic under test is the same rule the engine's own final step
applies: deductions capped at gross, net never negative. It is proven once in
payslip_edit.preview_totals and reused for the write, so there is exactly one
place that rule lives for this feature, matching the engine's own single cap
established in payroll_run.
"""

import pathlib
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.methods import payslip_edit
from payroll.methods.methods import payslip_fields, save_payslip
from payroll.methods.payroll_run import payroll_calculation
from payroll.models.models import Allowance, Contract, Deduction, Payslip
from payroll.tests.factories_payroll import make_active_contract

START = date(2026, 4, 1)
END = date(2026, 4, 30)

NO_LEAVE = {
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


class Fixture(TestCase):
    def setUp(self):
        self.user = make_user("payslipeditor", is_superuser=True)
        self.company = make_company("Edit Co")
        make_employee(
            company=self.company, email="payslipeditor@test.horilla", user=self.user
        )
        self.client.force_login(self.user)

        self.employee = make_employee(
            company=self.company, email="worker@edit.horilla", first_name="Worker"
        )
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=30000.0)

        Deduction.objects.create(
            title="Provident Fund",
            is_fixed=False,
            based_on="basic_pay",
            rate=12.0,
            include_active_employees=True,
            is_condition_based=False,
            is_pretax=True,
        )

        with patch("payroll.methods.methods.get_leaves", return_value=NO_LEAVE):
            result = payroll_calculation(self.employee, START, END)
        self.payslip = save_payslip(
            **payslip_fields(result, self.employee, status="draft")
        )

    def lines_by_title(self):
        return {
            line["title"]: line for line in payslip_edit.editable_lines(self.payslip)
        }


class EditableLinesTests(Fixture):
    def test_basic_pay_is_first_and_not_removable(self):
        lines = payslip_edit.editable_lines(self.payslip)
        self.assertEqual(lines[0]["key"], "basic")
        self.assertFalse(lines[0]["removable"])
        self.assertEqual(lines[0]["amount"], self.payslip.basic_pay)

    def test_income_tax_is_present_and_not_removable(self):
        by_title = self.lines_by_title()
        self.assertIn("Income Tax", by_title)
        self.assertFalse(by_title["Income Tax"]["removable"])

    def test_a_real_deduction_is_editable_and_removable(self):
        by_title = self.lines_by_title()
        self.assertIn("Provident Fund", by_title)
        self.assertTrue(by_title["Provident Fund"]["removable"])
        self.assertEqual(by_title["Provident Fund"]["section"], "deduction")

    def test_keys_are_stable_across_two_reads(self):
        """
        The form posts back these keys; if they moved between the GET that
        rendered the form and the POST that reads it, every edit would land
        on the wrong row.
        """
        first = [line["key"] for line in payslip_edit.editable_lines(self.payslip)]
        second = [line["key"] for line in payslip_edit.editable_lines(self.payslip)]
        self.assertEqual(first, second)


class PreviewTotalsTests(Fixture):
    def test_an_ordinary_edit_recomputes_gross_and_net(self):
        lines = payslip_edit.editable_lines(self.payslip)
        pf_key = self.lines_by_title()["Provident Fund"]["key"]

        totals = payslip_edit.preview_totals(lines, {pf_key: 500.0}, set())
        self.assertAlmostEqual(
            totals["net_pay"],
            totals["gross_pay"] - totals["total_deductions"],
            places=2,
        )
        self.assertEqual(totals["total_deductions"], totals["deduction_before_cap"])
        self.assertEqual(totals["uncovered_deduction"], 0.0)

    def test_deductions_are_capped_at_gross_not_allowed_to_exceed_it(self):
        lines = payslip_edit.editable_lines(self.payslip)
        pf_key = self.lines_by_title()["Provident Fund"]["key"]
        huge = 10_000_000.0

        totals = payslip_edit.preview_totals(lines, {pf_key: huge}, set())
        self.assertEqual(totals["total_deductions"], totals["gross_pay"])
        self.assertGreater(totals["uncovered_deduction"], 0)
        self.assertEqual(totals["net_pay"], 0.0)

    def test_removing_a_line_drops_it_from_the_total(self):
        lines = payslip_edit.editable_lines(self.payslip)
        pf_key = self.lines_by_title()["Provident Fund"]["key"]

        with_it = payslip_edit.preview_totals(lines, {}, set())
        without_it = payslip_edit.preview_totals(lines, {}, {pf_key})
        self.assertLess(without_it["total_deductions"], with_it["total_deductions"])

    def test_a_locked_line_cannot_be_removed_by_key_alone(self):
        """
        preview_totals only honours removal for lines the caller marked
        removable -- the view is what enforces this against tampered form
        data, but the arithmetic itself should not silently drop Basic Pay
        just because "basic" showed up in a removed set.
        """
        lines = payslip_edit.editable_lines(self.payslip)
        totals = payslip_edit.preview_totals(lines, {}, {"basic", "tax"})
        untouched = payslip_edit.preview_totals(lines, {}, set())
        self.assertEqual(totals["gross_pay"], untouched["gross_pay"])
        self.assertEqual(totals["total_deductions"], untouched["total_deductions"])


class ApplyEditsTests(Fixture):
    def test_editing_basic_pay_moves_gross_and_is_saved(self):
        """
        This fixture's contract has no earnings beyond basic pay, so gross
        moving to match the new basic exactly -- not staying at the old
        figure -- is what proves the edit was actually picked up.
        """
        payslip_edit.apply_edits(self.payslip, {"basic": 40000.0}, set())
        self.payslip.refresh_from_db()

        self.assertEqual(self.payslip.basic_pay, 40000.0)
        self.assertEqual(self.payslip.gross_pay, 40000.0)

    def test_editing_income_tax_moves_net_and_is_stored_as_federal_tax(self):
        payslip_edit.apply_edits(self.payslip, {"tax": 1234.56}, set())
        self.payslip.refresh_from_db()

        self.assertEqual(self.payslip.pay_head_data["federal_tax"], 1234.56)

    def test_removing_a_deduction_line_takes_it_out_of_pay_head_data(self):
        pf_key = self.lines_by_title()["Provident Fund"]["key"]
        payslip_edit.apply_edits(self.payslip, {}, {pf_key})
        self.payslip.refresh_from_db()

        titles = [
            row["title"] for row in self.payslip.pay_head_data["pretax_deductions"]
        ]
        self.assertNotIn("Provident Fund", titles)

    def test_the_shared_deduction_definition_is_untouched(self):
        """
        The whole point: editing one payslip must never reach the Deduction
        row every other employee's payslip is computed from.
        """
        pf_key = self.lines_by_title()["Provident Fund"]["key"]
        pf = Deduction.objects.get(title="Provident Fund")
        original_rate = pf.rate

        payslip_edit.apply_edits(self.payslip, {pf_key: 999.0}, set())

        pf.refresh_from_db()
        self.assertEqual(pf.rate, original_rate)

    def test_saved_totals_never_exceed_gross(self):
        pf_key = self.lines_by_title()["Provident Fund"]["key"]
        payslip_edit.apply_edits(self.payslip, {pf_key: 10_000_000.0}, set())
        self.payslip.refresh_from_db()

        self.assertLessEqual(self.payslip.deduction, self.payslip.gross_pay)
        self.assertEqual(self.payslip.net_pay, 0.0)

    def test_what_was_previewed_is_what_gets_saved(self):
        """
        preview_totals and apply_edits share the same arithmetic on purpose --
        this is the guarantee that promise is worth anything.
        """
        lines = payslip_edit.editable_lines(self.payslip)
        pf_key = self.lines_by_title()["Provident Fund"]["key"]
        edits = {pf_key: 777.0, "basic": 31000.0}

        previewed = payslip_edit.preview_totals(lines, edits, set())
        payslip_edit.apply_edits(self.payslip, edits, set())
        self.payslip.refresh_from_db()

        self.assertEqual(self.payslip.gross_pay, previewed["gross_pay"])
        self.assertEqual(self.payslip.deduction, previewed["total_deductions"])
        self.assertEqual(self.payslip.net_pay, previewed["net_pay"])


class ViewTests(Fixture):
    def url(self):
        return reverse("edit-payslip-components", args=[self.payslip.pk])

    def test_the_form_lists_every_line(self):
        response = self.client.get(self.url())
        self.assertContains(response, "Provident Fund")
        self.assertContains(response, "Income Tax")
        self.assertContains(response, "Basic Pay")

    def test_posting_an_edit_saves_it(self):
        pf_key = self.lines_by_title()["Provident Fund"]["key"]
        self.client.post(self.url(), {f"amount:{pf_key}": "555.00"})

        self.payslip.refresh_from_db()
        titles = {
            row["title"]: row["amount"]
            for row in self.payslip.pay_head_data["pretax_deductions"]
        }
        self.assertEqual(titles["Provident Fund"], 555.0)

    def test_posting_a_removal_removes_it(self):
        pf_key = self.lines_by_title()["Provident Fund"]["key"]
        self.client.post(self.url(), {"remove": [pf_key]})

        self.payslip.refresh_from_db()
        titles = [
            row["title"] for row in self.payslip.pay_head_data["pretax_deductions"]
        ]
        self.assertNotIn("Provident Fund", titles)

    def test_a_paid_payslip_cannot_be_edited(self):
        self.payslip.status = "paid"
        self.payslip.save()
        original = self.payslip.pay_head_data

        self.client.post(self.url(), {"amount:basic": "1.00"})

        self.payslip.refresh_from_db()
        self.assertEqual(self.payslip.pay_head_data, original)

    def test_a_paid_payslip_refuses_the_form_too(self):
        """
        The view refuses outright rather than rendering a locked-down form --
        there is no reading of "paid" under which opening the editor at all
        is the right response.
        """
        self.payslip.status = "paid"
        self.payslip.save()
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 302)

    def test_an_htmx_save_returns_the_payslip_fragment(self):
        response = self.client.post(
            self.url(), {"amount:basic": "1000.00"}, HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, "Net pay")

    def test_a_garbage_amount_is_ignored_not_a_500(self):
        response = self.client.post(self.url(), {"amount:basic": "not-a-number"})
        self.assertNotEqual(response.status_code, 500)

    def test_removing_basic_pay_by_tampered_key_does_nothing(self):
        """
        The template never renders a checkbox for Basic Pay, but nothing
        stops a POST claiming one anyway -- the view has to refuse it itself.
        """
        original_basic = self.payslip.basic_pay
        self.client.post(self.url(), {"remove": ["basic"]})

        self.payslip.refresh_from_db()
        self.assertEqual(self.payslip.basic_pay, original_basic)

    def test_it_needs_permission(self):
        stranger = make_user("nosy")
        make_employee(company=self.company, email="nosy@test.horilla", user=stranger)
        self.client.force_login(stranger)

        response = self.client.get(self.url())
        self.assertNotEqual(response.status_code, 200)


class FormulaContextTests(Fixture):
    """
    A formula written on a payslip is evaluated against that payslip, not
    against the illustrative figures the component form previews with.
    """

    def test_it_reports_this_payslip_s_own_figures(self):
        context = payslip_edit.formula_context(self.payslip)
        self.assertEqual(context["BASIC"], self.payslip.basic_pay)

    def test_a_payslip_without_a_stored_context_still_has_the_two_basics(self):
        """
        Payslips generated before the engine stored its context keep working:
        the two figures every payslip has are read off the record itself.
        """
        data = dict(self.payslip.pay_head_data)
        data.pop("component_context", None)
        self.payslip.pay_head_data = data
        self.payslip.save()

        context = payslip_edit.formula_context(self.payslip)
        self.assertEqual(context["BASIC"], self.payslip.basic_pay)
        self.assertEqual(context["GROSS"], self.payslip.gross_pay)

    def test_only_codes_this_payslip_resolved_are_offered(self):
        """
        A chip for a component this employee does not have would evaluate to
        zero while looking like it had done something.
        """
        Deduction.objects.create(
            title="Somebody Elses Levy",
            code="ELSEWHERE",
            is_fixed=True,
            amount=100.0,
            include_active_employees=False,
        )
        offered = {row["code"] for row in payslip_edit.formula_codes(self.payslip)}

        self.assertIn("BASIC", offered)
        self.assertNotIn("ELSEWHERE", offered)


class NewLineTests(Fixture):
    def post_data(self, **extra):
        data = {"new_title": "", "new_amount": "", "new_section": "earning"}
        data.update(extra)
        return data

    def test_an_untouched_composer_adds_nothing(self):
        self.assertIsNone(payslip_edit.parse_new_line(self.post_data(), self.payslip))

    def test_a_typed_amount_becomes_a_line(self):
        line = payslip_edit.parse_new_line(
            self.post_data(new_title="Travel reimbursement", new_amount="1500"),
            self.payslip,
        )
        self.assertEqual(line["section"], "earning")
        self.assertEqual(line["amount"], 1500.0)
        self.assertEqual(line["formula"], "")

    def test_a_formula_decides_the_amount_against_this_payslip(self):
        line = payslip_edit.parse_new_line(
            self.post_data(
                new_title="Festival bonus",
                # Deliberately different from the formula's answer: the client
                # does not get to say what a formula came to.
                new_amount="1.00",
                new_formula="BASIC * 0.1",
            ),
            self.payslip,
        )
        self.assertEqual(line["amount"], round(self.payslip.basic_pay * 0.1, 2))
        self.assertEqual(line["formula"], "BASIC * 0.1")

    def test_a_formula_that_will_not_evaluate_refuses_the_line(self):
        with self.assertRaises(payslip_edit.NewLineError):
            payslip_edit.parse_new_line(
                self.post_data(new_title="Nonsense", new_formula="BASIC * "),
                self.payslip,
            )

    def test_a_line_with_no_name_is_refused(self):
        with self.assertRaises(payslip_edit.NewLineError):
            payslip_edit.parse_new_line(self.post_data(new_amount="500"), self.payslip)

    def test_an_added_earning_moves_gross_and_net(self):
        before = self.payslip.gross_pay
        payslip_edit.apply_edits(
            self.payslip,
            {},
            set(),
            new_line={
                "section": "earning",
                "title": "Travel reimbursement",
                "amount": 1500.0,
                "formula": "",
            },
        )
        self.payslip.refresh_from_db()
        self.assertEqual(self.payslip.gross_pay, round(before + 1500.0, 2))

    def test_an_added_deduction_lands_in_a_bucket_the_payslip_shows(self):
        payslip_edit.apply_edits(
            self.payslip,
            {},
            set(),
            new_line={
                "section": "deduction",
                "title": "Canteen",
                "amount": 250.0,
                "formula": "",
            },
        )
        self.payslip.refresh_from_db()
        titles = [
            row["title"]
            for row in self.payslip.pay_head_data[payslip_edit.NEW_LINE_BUCKET]
        ]
        self.assertIn("Canteen", titles)

    def test_an_added_line_creates_no_component(self):
        """
        The whole reason this exists rather than the old Add buttons: a
        one-off correction must not leave a permanent component behind.
        """
        before = Deduction.objects.count()
        payslip_edit.apply_edits(
            self.payslip,
            {},
            set(),
            new_line={
                "section": "deduction",
                "title": "Canteen",
                "amount": 250.0,
                "formula": "",
            },
        )
        self.assertEqual(Deduction.objects.count(), before)

    def test_an_added_line_is_editable_and_removable_afterwards(self):
        payslip_edit.apply_edits(
            self.payslip,
            {},
            set(),
            new_line={
                "section": "earning",
                "title": "Travel reimbursement",
                "amount": 1500.0,
                "formula": "",
            },
        )
        self.payslip.refresh_from_db()
        line = self.lines_by_title()["Travel reimbursement"]
        self.assertTrue(line["removable"])

        payslip_edit.apply_edits(self.payslip, {}, {line["key"]})
        self.payslip.refresh_from_db()
        self.assertNotIn("Travel reimbursement", self.lines_by_title())

    def test_two_added_lines_do_not_share_a_key(self):
        """
        Neither has a component id, so both would key by position -- and a
        position can equal a real component's id. They carry their own.
        """
        for title in ("First", "Second"):
            payslip_edit.apply_edits(
                self.payslip,
                {},
                set(),
                new_line={
                    "section": "earning",
                    "title": title,
                    "amount": 10.0,
                    "formula": "",
                },
            )
            self.payslip.refresh_from_db()

        keys = [line["key"] for line in payslip_edit.editable_lines(self.payslip)]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_expression_is_kept_beside_the_figure(self):
        payslip_edit.apply_edits(
            self.payslip,
            {},
            set(),
            new_line={
                "section": "earning",
                "title": "Festival bonus",
                "amount": 3000.0,
                "formula": "BASIC * 0.1",
            },
        )
        self.payslip.refresh_from_db()
        row = self.payslip.pay_head_data["allowances"][-1]
        self.assertEqual(row["formula"], "BASIC * 0.1")


class NewLineViewTests(Fixture):
    def url(self):
        return reverse("edit-payslip-components", args=[self.payslip.pk])

    def preview_url(self):
        return reverse("payslip-line-formula-preview", args=[self.payslip.pk])

    def test_the_form_offers_the_composer_and_the_builder(self):
        response = self.client.get(self.url())
        self.assertContains(response, 'name="new_title"')
        self.assertContains(response, 'name="new_formula"')
        self.assertContains(response, "data-formula-builder")

    def test_the_builder_previews_against_this_payslip_not_a_sample(self):
        """
        The component form has no employee in view and can only preview
        against an illustrative basic pay. Here both the employee and the
        period are already decided, so offering a sample box would be offering
        a worse answer than the one available.
        """
        response = self.client.get(self.url())
        self.assertContains(response, self.preview_url())
        self.assertNotContains(response, "on a sample basic pay of")
        self.assertContains(response, "against this payslip")

    def test_posting_a_new_line_adds_it(self):
        self.client.post(
            self.url(),
            {
                "new_title": "Travel reimbursement",
                "new_amount": "1500",
                "new_section": "earning",
            },
        )
        self.payslip.refresh_from_db()
        titles = [row["title"] for row in self.payslip.pay_head_data["allowances"]]
        self.assertIn("Travel reimbursement", titles)

    def test_a_bad_formula_saves_nothing_at_all(self):
        """
        Not even the amount edits posted alongside it -- half a save is worse
        than none, and the message says which half failed.
        """
        original_basic = self.payslip.basic_pay
        self.client.post(
            self.url(),
            {
                "amount:basic": "99999.00",
                "new_title": "Nonsense",
                "new_formula": "BASIC * ",
            },
        )
        self.payslip.refresh_from_db()
        self.assertEqual(self.payslip.basic_pay, original_basic)

    def test_the_preview_endpoint_answers_with_this_payslips_figures(self):
        response = self.client.post(
            self.preview_url(), {"formula": "BASIC * 0.1"}, HTTP_HX_REQUEST="true"
        )
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"], round(self.payslip.basic_pay * 0.1, 2))

    def test_the_preview_endpoint_reports_a_bad_formula_rather_than_failing(self):
        response = self.client.post(
            self.preview_url(), {"formula": "BASIC * "}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_the_preview_endpoint_needs_permission(self):
        """
        A refused HTMX request gets this app's 200-with-a-refusal-page rather
        than a redirect, so what proves the refusal is that no figure came
        back -- not the status code.
        """
        stranger = make_user("nosy2")
        make_employee(company=self.company, email="nosy2@test.horilla", user=stranger)
        self.client.force_login(stranger)

        response = self.client.post(
            self.preview_url(), {"formula": "BASIC"}, HTTP_HX_REQUEST="true"
        )
        self.assertNotIn("application/json", response.headers.get("Content-Type", ""))


class TheOldAddButtonsAreGoneTests(Fixture):
    """
    The payslip page used to carry two "+" buttons that created a real
    component and then deleted and regenerated the payslip to pick it up. Both
    are replaced by the composer in the edit form.
    """

    def test_the_payslip_page_no_longer_offers_them(self):
        response = self.client.get(
            reverse("view-created-payslip", kwargs={"payslip_id": self.payslip.pk})
        )
        self.assertNotContains(response, reverse("add-bonus"))
        self.assertNotContains(response, reverse("add-payslip-deduction"))


class PayslipHelpTextTests(Fixture):
    """
    The payslip carried three info bubbles written against an older engine,
    two of which explained the same "update compensation" behaviour from
    opposite sides of the same column. What is left is the help a reader
    cannot work out from the figures in front of them.
    """

    SUMMARY = pathlib.Path(
        "horilla_theme/templates/payroll/payslip/individual_payslip_summery.html"
    )
    # The Loss of Pay row is a shared include -- lop_reflected_in_basic
    # decides which of the two columns actually renders it -- so its markup
    # lives here now, not inline in SUMMARY. Combined so the checks below
    # don't have to know which file a given string ended up in.
    LOP_ROW = pathlib.Path(
        "horilla_theme/templates/payroll/payslip/_loss_of_pay_row.html"
    )

    def source(self):
        return self.SUMMARY.read_text(encoding="utf-8") + self.LOP_ROW.read_text(
            encoding="utf-8"
        )

    def test_only_a_few_bubbles_are_left(self):
        self.assertEqual(self.source().count("info.svg"), 4)

    def test_basic_pay_says_where_the_figure_came_from(self):
        """
        With two structure modes in the engine, where basic pay comes from is
        the question the figure actually raises -- it is the contract wage in
        one mode and a component's share of CTC in the other.
        """
        self.assertIn("CTC Down", self.source())

    def test_paid_days_says_what_it_counts(self):
        """
        Paid days now includes week offs and holidays alongside present days
        and paid leave -- not something a reader would guess from the figure
        alone, since it no longer matches a plain "worked minus absent" count.
        """
        self.assertIn("week offs and holidays are all paid", self.source().lower())

    def test_the_old_wording_is_gone(self):
        self.assertNotIn("update compensation", self.source())

    def test_loss_of_pay_has_a_custom_breakdown_popover(self):
        """
        The sub-text already states which two contract settings decided the
        figure; the reader still can't tell from that alone how they combine
        into an actual number, or which other line the result comes off of.

        A custom hover panel, not the global title-attribute tooltip: that
        widget binds to every [title] in the document and was already the
        source of one real bug (orphaned popups left behind when their
        anchor is removed mid-hover).
        """
        source = self.source()
        self.assertIn('class="ps__pop"', source)
        self.assertNotIn("Leave amount will be calculated by dividing", source)
        source_lower = source.lower()
        self.assertIn("per-day amount", source_lower)
        self.assertIn("comes off basic pay above by default", source_lower)

    def test_every_info_icon_uses_the_custom_popover(self):
        """
        All four should share one mechanism -- a page where three use the
        custom popover and a fourth still relies on the global
        title-attribute tooltip is the inconsistency this replaced.
        """
        source = self.source()
        self.assertEqual(source.count('class="ps__info"'), 4)
        self.assertNotIn('title="{% trans', source)

    def test_the_page_still_renders_the_help_that_is_left(self):
        response = self.client.get(
            reverse("view-created-payslip", kwargs={"payslip_id": self.payslip.pk})
        )
        self.assertContains(response, "CTC Down")


class DerivedLinesFixture(Fixture):
    """
    A payslip whose lines are mostly percentages of other lines, which is what
    a real structure looks like -- the base Fixture has a single deduction on
    purpose, so the arithmetic in the tests above stays readable.
    """

    def setUp(self):
        super().setUp()
        hra = Allowance.objects.create(
            title="House Rent Allowance",
            code="HRA",
            sequence=20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=40.0,
            include_active_employees=True,
            is_taxable=True,
        )
        self.hra = hra
        Allowance.objects.create(
            title="Medical Allowance",
            code="MED",
            sequence=30,
            is_fixed=True,
            amount=1250.0,
            include_active_employees=True,
            is_taxable=True,
        )
        self.payslip.delete()
        with patch("payroll.methods.methods.get_leaves", return_value=NO_LEAVE):
            result = payroll_calculation(self.employee, START, END)
        self.payslip = save_payslip(
            **payslip_fields(result, self.employee, status="draft")
        )


class WhatALineIsTests(DerivedLinesFixture):
    def test_a_percentage_says_what_it_is_a_percentage_of(self):
        line = self.lines_by_title()["House Rent Allowance"]
        self.assertIn("40%", line["basis"])
        self.assertIn("BASIC", line["basis"])
        self.assertEqual(line["depends_on"], ["BASIC"])

    def test_a_flat_amount_is_not_explained(self):
        """
        "1,250.00" written beside a box reading 1,250.00 explains nothing, and
        an info bubble that says nothing is worse than none.
        """
        line = self.lines_by_title()["Medical Allowance"]
        self.assertEqual(line["basis"], "")
        self.assertEqual(line["depends_on"], [])

    def test_a_deduction_off_basic_pay_follows_basic_pay(self):
        line = self.lines_by_title()["Provident Fund"]
        self.assertEqual(line["depends_on"], ["BASIC"])

    def test_income_tax_follows_nothing_here(self):
        """
        Recomputing it would mean running the bracket engine, which this form
        deliberately does not do -- so it says so rather than implying the
        figure will keep up.
        """
        line = self.lines_by_title()["Income Tax"]
        self.assertEqual(line["depends_on"], [])

    def test_basic_pay_is_given_not_derived(self):
        """A line that recomputed itself could not be edited at all."""
        line = self.lines_by_title()["Basic Pay"]
        self.assertEqual(line["depends_on"], [])


class RecomputeDependentsTests(DerivedLinesFixture):
    def keys(self):
        return {title: line["key"] for title, line in self.lines_by_title().items()}

    def test_raising_basic_pay_raises_what_is_a_percentage_of_it(self):
        keys = self.keys()
        amounts = payslip_edit.recompute_dependents(
            self.payslip, {"basic": 40000.0}, given={"basic"}
        )
        self.assertAlmostEqual(amounts[keys["House Rent Allowance"]], 16000.0, places=2)
        self.assertAlmostEqual(amounts[keys["Provident Fund"]], 4800.0, places=2)

    def test_a_flat_line_does_not_move(self):
        keys = self.keys()
        amounts = payslip_edit.recompute_dependents(
            self.payslip, {"basic": 40000.0}, given={"basic"}
        )
        self.assertAlmostEqual(amounts[keys["Medical Allowance"]], 1250.0, places=2)

    def test_a_line_that_was_typed_into_is_left_alone(self):
        """
        Overriding a figure is the whole reason this form exists. A
        recalculation that wrote over what was just typed would make the
        derived lines uneditable.
        """
        keys = self.keys()
        amounts = payslip_edit.recompute_dependents(
            self.payslip,
            {"basic": 40000.0, keys["House Rent Allowance"]: 99.0},
            given={"basic", keys["House Rent Allowance"]},
        )
        self.assertAlmostEqual(amounts[keys["House Rent Allowance"]], 99.0, places=2)
        # the ones nobody touched still follow
        self.assertAlmostEqual(amounts[keys["Provident Fund"]], 4800.0, places=2)

    def test_changing_nothing_changes_nothing(self):
        """
        The figures the engine produced are what these rules produce, so a
        recalculation over an untouched form has to be a no-op -- if it is
        not, the two disagree and one of them is wrong.
        """
        before = {
            line["key"]: line["amount"]
            for line in payslip_edit.editable_lines(self.payslip)
        }
        after = payslip_edit.recompute_dependents(self.payslip, {})
        for key, amount in before.items():
            self.assertAlmostEqual(after[key], amount, places=2, msg=key)

    def test_a_removed_line_stops_feeding_the_ones_after_it(self):
        keys = self.keys()
        amounts = payslip_edit.recompute_dependents(
            self.payslip, {}, removed={keys["House Rent Allowance"]}
        )
        # HRA itself keeps its figure -- it is dropped from the totals by
        # preview_totals, not by being zeroed here.
        self.assertGreater(amounts[keys["House Rent Allowance"]], 0)


class RecalculateEndpointTests(DerivedLinesFixture):
    def url(self):
        return reverse("recalculate-payslip-lines", args=[self.payslip.pk])

    def test_it_returns_the_moved_amounts(self):
        keys = {title: line["key"] for title, line in self.lines_by_title().items()}
        response = self.client.post(
            self.url(),
            {"amount:basic": "40000.00", "given": ["basic"]},
            HTTP_HX_REQUEST="true",
        )
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertAlmostEqual(
            payload["amounts"][keys["House Rent Allowance"]], 16000.0, places=2
        )

    def test_it_saves_nothing(self):
        original = self.payslip.pay_head_data
        self.client.post(
            self.url(),
            {"amount:basic": "40000.00", "given": ["basic"]},
            HTTP_HX_REQUEST="true",
        )
        self.payslip.refresh_from_db()
        self.assertEqual(self.payslip.pay_head_data, original)

    def test_it_needs_permission(self):
        stranger = make_user("nosy3")
        make_employee(company=self.company, email="nosy3@test.horilla", user=stranger)
        self.client.force_login(stranger)

        response = self.client.post(self.url(), {}, HTTP_HX_REQUEST="true")
        self.assertNotIn("application/json", response.headers.get("Content-Type", ""))


class TheFormShowsTheComputationTests(DerivedLinesFixture):
    def test_the_percentage_is_on_the_line(self):
        response = self.client.get(
            reverse("edit-payslip-components", args=[self.payslip.pk])
        )
        self.assertContains(response, "pe__basis")
        self.assertContains(response, "40% of BASIC")

    def test_a_derived_line_offers_the_popover(self):
        response = self.client.get(
            reverse("edit-payslip-components", args=[self.payslip.pk])
        )
        self.assertContains(response, "pe__pop")
        self.assertContains(response, "moves when they do")

    def test_the_popover_is_built_outside_the_modal(self):
        """
        Shown where it sits, it was clipped by the dialog's own scrolling and
        painted under the modal -- the icon lit up on hover and nothing else
        happened. It is copied to the end of <body> instead, where no ancestor
        of the row can reach it.
        """
        response = self.client.get(
            reverse("edit-payslip-components", args=[self.payslip.pk])
        )
        self.assertContains(response, "document.body.appendChild(pop)")
        self.assertContains(response, "pe__pop--float")

    def test_the_form_knows_where_to_recalculate(self):
        response = self.client.get(
            reverse("edit-payslip-components", args=[self.payslip.pk])
        )
        self.assertContains(
            response, reverse("recalculate-payslip-lines", args=[self.payslip.pk])
        )
