"""
The filing status page saying what each status does.

It was an accordion of names. A filing status is a mode flag, a slab table and
four adjustment fields, so the name answers none of the questions the screen
raises -- which of these charges what, which are configured at all, and who is
being taxed under them.

The figure that was nowhere is the one that matters most: contracts with no
filing status. The engine computes zero tax for them, correctly and silently,
which looks exactly like a low earner until somebody reconciles a return.
"""

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import Contract, FilingStatus
from payroll.models.tax_models import TaxBracket
from payroll.tests.factories_payroll import make_active_contract


class Fixture(TestCase):
    def setUp(self):
        self.user = make_user("taxadmin", is_superuser=True)
        self.company = make_company("Tax Co")
        admin = make_employee(
            company=self.company, email="taxadmin@test.horilla", user=self.user
        )
        # An Employee gets a contract on save, and the admin's would count as
        # one more contract with no filing status -- which is what the page
        # reports. Correct of the page, noise in these tests.
        Contract.objects.filter(employee_id=admin).delete()
        self.client.force_login(self.user)

    def employee(self, name, **contract):
        person = make_employee(
            company=self.company,
            email=f"{name.lower()}@tax.horilla",
            first_name=name,
        )
        Contract.objects.filter(employee_id=person).delete()
        make_active_contract(person, wage=30000.0, **contract)
        return person

    def status(self, name="Single", slabs=(), **fields):
        status = FilingStatus.objects.create(filing_status=name, **fields)
        for low, high, rate in slabs:
            TaxBracket.objects.create(
                filing_status_id=status,
                min_income=low,
                max_income=high,
                tax_rate=rate,
            )
        return status

    def page(self):
        return self.client.get(reverse("filing-status-view"))


class WhatEachStatusDoesTests(Fixture):
    def test_the_slab_count_is_shown_not_just_the_name(self):
        self.status("Single", slabs=[(0, 10000, 5), (10000, None, 20)])
        self.assertContains(self.page(), "2 slabs")

    def test_the_top_rate_is_shown(self):
        self.status("Single", slabs=[(0, 10000, 5), (10000, None, 30)])
        self.assertContains(self.page(), "30%")

    def test_a_python_formula_says_so(self):
        self.status("Coded", use_py=True, python_code="tax = 0")
        self.assertContains(self.page(), "Python formula")

    def test_each_row_can_be_deleted_through_the_confirmation_dialog(self):
        single = self.status("Single", slabs=[(0, None, 10)])
        response = self.page()
        self.assertContains(
            response, "generic-delete/?model=payroll.FilingStatus&amp;pk=%s" % single.pk
        )
        self.assertContains(response, 'id="deleteConfirmationBody"')

    def test_the_basis_is_shown(self):
        """
        Tax on gross and tax on taxable gross are different amounts, and the
        name never said which.
        """
        self.status("Single", based_on="gross_pay", slabs=[(0, None, 10)])
        self.assertContains(self.page(), "Gross Pay")

    def test_the_adjustments_are_listed(self):
        self.status(
            "India",
            slabs=[(0, None, 10)],
            standard_deduction=50000,
            cess_percent=4,
        )
        body = self.page().content.decode()

        self.assertIn("Standard deduction", body)
        self.assertIn("Cess", body)

    def test_the_adjustments_carry_their_figures_above_the_slabs(self):
        """
        They are applied around whichever mode computes the tax, so a slab
        table read on its own is only part of the answer. Naming them twice
        would be repetition; the figures are the setting.
        """
        self.status(
            "India",
            slabs=[(0, None, 10)],
            standard_deduction=75000,
            rebate_income_limit=1200000,
            rebate_max_amount=60000,
            cess_percent=4,
        )
        body = self.page().content.decode()

        self.assertIn("<b>75,000</b>", body)
        self.assertIn("<b>60,000 below 1,200,000</b>", body)
        self.assertIn("<b>4%</b>", body)

    def test_the_working_is_on_the_page(self):
        """
        computation_steps() states the engine's real order. Having it two
        clicks away is how a status gets configured by guesswork.
        """
        self.status("India", slabs=[(0, None, 10)], standard_deduction=50000)
        self.assertContains(self.page(), "Subtract a standard deduction")

class WhatIsWrongTests(Fixture):
    def test_contracts_with_no_filing_status_are_counted(self):
        """The whole reason the page needed rebuilding."""
        self.employee("Ann")
        self.employee("Ben")

        response = self.page()
        self.assertEqual(response.context["unassigned"], 2)
        self.assertContains(response, "no income tax is worked out")

    def test_an_assigned_contract_is_not_counted_as_missing(self):
        status = self.status("Single", slabs=[(0, None, 10)])
        self.employee("Ann", filing_status=status)

        self.assertEqual(self.page().context["unassigned"], 0)

    def test_a_status_with_nothing_configured_is_flagged(self):
        """
        No slabs and no formula charges nothing to everyone on it -- the same
        silent nothing as having no status at all.
        """
        self.status("Empty")
        response = self.page()

        self.assertEqual(response.context["unconfigured"], 1)
        self.assertContains(response, "Nothing configured")

    def test_a_configured_status_is_not_flagged(self):
        self.status("Single", slabs=[(0, None, 10)])
        self.assertEqual(self.page().context["unconfigured"], 0)

    def test_a_formula_with_no_code_is_flagged(self):
        """use_py on its own computes nothing."""
        self.status("Coded", use_py=True, python_code="")
        self.assertEqual(self.page().context["unconfigured"], 1)


class CoverageTests(Fixture):
    def test_contracts_are_counted_per_status(self):
        status = self.status("Single", slabs=[(0, None, 10)])
        self.employee("Ann", filing_status=status)
        self.employee("Ben", filing_status=status)

        row = self.page().context["rows"][0]
        self.assertEqual(row["status"].employee_count, 2)

    def test_an_expired_contract_is_not_counted(self):
        """
        A status still attached to expired contracts is not one anybody is
        being taxed under.
        """
        status = self.status("Single", slabs=[(0, None, 10)])
        person = self.employee("Ann", filing_status=status)
        Contract.objects.filter(employee_id=person).update(contract_status="expired")

        self.assertEqual(self.page().context["rows"][0]["status"].employee_count, 0)

    def test_the_covered_total_adds_the_statuses_up(self):
        first = self.status("A", slabs=[(0, None, 10)])
        second = self.status("B", slabs=[(0, None, 20)])
        self.employee("Ann", filing_status=first)
        self.employee("Ben", filing_status=second)

        self.assertEqual(self.page().context["total_covered"], 2)


class SlabPresentationTests(Fixture):
    def test_a_range_is_one_column_not_two(self):
        """
        Split across From and To, a range reads as two unrelated numbers with
        the page's width between them -- which is what made a seven-slab table
        hard to follow.
        """
        self.status("Single", slabs=[(0, 16550, 10)])
        body = self.page().content.decode()

        self.assertIn("Income band", body)
        self.assertNotIn(">From<", body)

    def test_figures_carry_thousands_separators(self):
        self.status("Single", slabs=[(0, 1234567, 10)])
        self.assertContains(self.page(), "1,234,567")

    def test_an_open_ended_slab_stored_as_null_reads_as_and_above(self):
        bracket = TaxBracket.objects.create(
            filing_status_id=self.status("Single"),
            min_income=609350,
            max_income=None,
            tax_rate=37,
        )
        self.assertEqual(str(bracket.band_label()), "609,350 and above")

    def test_an_open_ended_slab_stored_as_infinity_reads_the_same(self):
        """
        Some tax packs store NULL and others store float("inf"). Only the first
        was handled, so the last row of a US table read "inf".
        """
        import math

        bracket = TaxBracket.objects.create(
            filing_status_id=self.status("Single"),
            min_income=609350,
            max_income=math.inf,
            tax_rate=37,
        )
        self.assertEqual(str(bracket.band_label()), "609,350 and above")

    def test_infinity_never_reaches_the_page(self):
        import math

        TaxBracket.objects.create(
            filing_status_id=self.status("Single"),
            min_income=0,
            max_income=math.inf,
            tax_rate=37,
        )
        body = self.page().content.decode()

        self.assertNotIn(">inf<", body)
        self.assertIn("and above", body)

    def test_the_slabs_come_before_the_steps(self):
        """
        Source order is reading order -- the grid does not reorder -- so the
        slabs have to lead in the markup too, keeping the tab order and what a
        screen reader hears the same as what is on screen.
        """
        self.status("Single", slabs=[(0, None, 10)])
        body = self.page().content.decode()

        self.assertLess(body.index(">Slabs<"), body.index(">In order<"))

    def test_the_panel_links_to_where_the_slabs_are_set(self):
        """
        Spotting something wrong in the working and having to go back up to the
        row to fix it is the trip this saves.
        """
        status = self.status("Single", slabs=[(0, None, 10)])
        self.assertContains(self.page(), status.get_rules_url())

    def test_a_formula_status_gets_the_same_link(self):
        """A formula is edited on the same page as the slabs."""
        self.status("Coded", use_py=True, python_code="tax = 0")
        body = self.page().content.decode()

        self.assertIn('oh-btn--small fs__edit"', body)
        self.assertIn(">Formula<", body)

    def test_a_status_with_no_slabs_gets_it_too(self):
        """It is the one most likely to need it."""
        self.status("Empty")
        self.assertContains(self.page(), 'oh-btn--small fs__edit"')

    def test_every_status_gets_exactly_one(self):
        """
        The three branches -- slabs, formula, nothing configured -- each carry
        their own head, so one of them appearing twice or not at all would mean
        a branch was missed.
        """
        self.status("WithSlabs", slabs=[(0, None, 10)])
        self.status("WithFormula", use_py=True, python_code="tax = 0")
        self.status("WithNothing")

        body = self.page().content.decode()
        self.assertEqual(body.count('oh-btn--small fs__edit"'), 3)
        self.assertEqual(body.count('class="fs__slabhead"'), 3)

    def test_it_is_hidden_without_permission_to_change(self):
        viewer = make_user("viewer")
        make_employee(company=self.company, email="viewer@test.horilla", user=viewer)
        from django.contrib.auth.models import Permission

        viewer.user_permissions.add(
            Permission.objects.get(codename="view_filingstatus")
        )
        self.status("Single", slabs=[(0, None, 10)])
        self.client.force_login(viewer)

        self.assertNotContains(self.page(), 'oh-btn--small fs__edit"')

    def test_the_bands_are_numbered(self):
        """
        The slabs are ordered by min_income, so the counter is the band's place
        in the ladder -- what somebody checking a tax table against a published
        one counts down.
        """
        self.status("Single", slabs=[(0, 100, 5), (100, 200, 10), (200, None, 20)])
        body = self.page().content.decode()

        for position in ("1", "2", "3"):
            self.assertIn(f'<td class="fs__sn">{position}</td>', body)

    def test_the_numbering_restarts_for_each_status(self):
        """
        A counter carried across statuses would number the second table from
        where the first left off, which is not that band's place in anything.
        """
        self.status("First", slabs=[(0, 100, 5), (100, None, 10)])
        self.status("Second", slabs=[(0, None, 30)])
        body = self.page().content.decode()

        self.assertEqual(body.count('<td class="fs__sn">1</td>'), 2)
        self.assertEqual(body.count('<td class="fs__sn">2</td>'), 1)

class ComputationStepsTests(Fixture):
    def test_one_slab_is_not_described_as_slab_open_bracket_s(self):
        """
        Read by somebody checking a tax configuration. A parenthesised plural
        reads as a placeholder nobody finished.
        """
        status = self.status("Single", slabs=[(0, None, 10)])
        steps = " ".join(str(step) for step in status.computation_steps)

        self.assertNotIn("slab(s)", steps)
        self.assertIn("the single tax slab", steps)

    def test_several_slabs_read_as_plural(self):
        status = self.status(
            "Single", slabs=[(0, 100, 5), (100, 200, 10), (200, None, 20)]
        )
        steps = " ".join(str(step) for step in status.computation_steps)

        self.assertIn("Apply 3 tax slabs", steps)
        self.assertNotIn("slab(s)", steps)


class PageTests(Fixture):
    def test_an_empty_install_says_what_is_missing(self):
        response = self.page()
        self.assertContains(response, "No filing statuses yet")
        self.assertContains(response, "no income tax is worked out for anybody")

    def test_it_needs_permission(self):
        stranger = make_user("nosy")
        make_employee(company=self.company, email="nosy@test.horilla", user=stranger)
        self.client.force_login(stranger)

        self.assertNotEqual(self.page().status_code, 200)
