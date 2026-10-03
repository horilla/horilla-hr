"""
The payslip heads in the worked example, and the redesigned detail modal.

Four bare totals said what the figures were but not where they came from:
which earnings gross counted, what taxable gross took off, why net differs
from gross by more than the lines above it. The panel now states the equation
behind each head.

These assert those equations are the ENGINE's — calculate_gross_pay,
calculate_taxable_gross_pay and payroll_run's total_deductions — because a
panel that explains its arithmetic in terms payroll does not use would be
worse than one that explains nothing: it would be believed.
"""

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import Allowance, Deduction, FilingStatus, SalaryStructure


class ExampleHeadTests(TestCase):
    def setUp(self):
        user = make_user("headadmin", is_superuser=True)
        company = make_company("Head Co")
        make_employee(company=company, email="headadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}
        self.structure = SalaryStructure.objects.create(title="Heads")

    def _run(self, basic=50000, filing_status=""):
        response = self.client.post(
            reverse("salary-structure-preview", kwargs={"pk": self.structure.pk}),
            {"ctc": 0, "basic": basic, "lop_days": 0, "filing_status": filing_status},
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _head(self, data, key):
        return next(head for head in data["heads"] if head["key"] == key)

    def _stock(self):
        """A taxable earning, a non-taxable one, and a pre-tax deduction."""
        taxable = Allowance.objects.create(
            title="HRA",
            sequence=10,
            is_fixed=True,
            amount=10000.0,
            is_taxable=True,
            maximum_unit="full_period",
        )
        exempt = Allowance.objects.create(
            title="Meal Card",
            sequence=20,
            is_fixed=True,
            amount=2000.0,
            is_taxable=False,
            maximum_unit="full_period",
        )
        pretax = Deduction.objects.create(
            title="PF",
            sequence=30,
            is_fixed=True,
            amount=6000.0,
            is_pretax=True,
            maximum_unit="full_period",
        )
        self.structure.allowances.add(taxable, exempt)
        self.structure.deductions.add(pretax)

    def test_every_head_is_reported(self):
        self._stock()
        keys = [head["key"] for head in self._run()["heads"]]
        self.assertEqual(
            keys, ["gross_pay", "taxable_gross", "total_deductions", "net_pay"]
        )

    def test_each_head_carries_its_equation_and_the_figures_in_it(self):
        self._stock()
        for head in self._run()["heads"]:
            with self.subTest(head=head["key"]):
                self.assertTrue(head["label"])
                self.assertTrue(head["formula"])
                self.assertTrue(head["terms"])
                for term in head["terms"]:
                    self.assertTrue(term["label"])
                    self.assertIn(term["sign"], ("+", "−"))

    def test_the_terms_add_up_to_the_head(self):
        """
        The whole point of showing the working: an equation whose parts do not
        reach its own total would be actively misleading.
        """
        self._stock()
        for head in self._run()["heads"]:
            with self.subTest(head=head["key"]):
                total = sum(
                    term["amount"] if term["sign"] == "+" else -term["amount"]
                    for term in head["terms"]
                )
                self.assertAlmostEqual(total, head["amount"], places=2)

    def test_taxable_gross_takes_off_non_taxable_earnings_as_well(self):
        """
        calculate_taxable_gross_pay subtracts both non-taxable earnings and
        pre-tax deductions. The preview subtracted only the deductions, so a
        structure with an exempt earning previewed more tax than it charges.
        """
        self._stock()
        data = self._run()

        gross = self._head(data, "gross_pay")["amount"]
        taxable = self._head(data, "taxable_gross")["amount"]
        self.assertAlmostEqual(taxable, gross - 2000.0 - 6000.0, places=2)
        self.assertAlmostEqual(data["taxable_gross"], taxable, places=2)

    def test_gross_is_basic_plus_the_earnings(self):
        self._stock()
        data = self._run(basic=50000)
        self.assertAlmostEqual(
            self._head(data, "gross_pay")["amount"], 62000.0, places=2
        )

    def test_net_is_gross_less_the_deductions(self):
        self._stock()
        data = self._run()
        self.assertAlmostEqual(
            self._head(data, "net_pay")["amount"],
            self._head(data, "gross_pay")["amount"] - data["deductions_total"],
            places=2,
        )
        self.assertAlmostEqual(
            data["net_pay"], self._head(data, "net_pay")["amount"], places=2
        )

    def test_the_deduction_buckets_are_the_engine_three(self):
        """
        payslip_calc partitions deductions on is_pretax and is_tax into three
        disjoint sets, and total_deductions is their sum plus income tax.
        """
        self._stock()
        post = Deduction.objects.create(
            title="Union Dues",
            sequence=40,
            is_fixed=True,
            amount=100.0,
            is_pretax=False,
            maximum_unit="full_period",
        )
        self.structure.deductions.add(post)

        data = self._run()
        self.assertAlmostEqual(data["pretax_total"], 6000.0, places=2)
        self.assertAlmostEqual(data["post_tax_total"], 100.0, places=2)
        self.assertAlmostEqual(data["tax_component_total"], 0.0, places=2)
        self.assertAlmostEqual(data["deductions_total"], 6100.0, places=2)

    def test_an_empty_structure_still_reports_its_heads(self):
        data = self._run()
        self.assertEqual(len(data["heads"]), 4)

    def test_the_panel_has_what_its_footnotes_need(self):
        """
        The notes block states the period as facts rather than a trailing
        sentence, so it needs the calendar days and the loss-of-pay days, not
        just the worked/working pair.
        """
        self._stock()
        data = self._run()
        for key in ("calendar_days", "working_days", "worked_days", "lop_days"):
            self.assertIn(key, data)


class TaxBaseTests(TestCase):
    """
    Which figure the income tax is read from. It changes the answer
    substantially — taxing gross rather than taxable gross ignores every
    pre-tax deduction — and the panel did not say which it had used.
    """

    def setUp(self):
        user = make_user("baseadmin", is_superuser=True)
        company = make_company("Base Co")
        make_employee(company=company, email="baseadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}
        self.structure = SalaryStructure.objects.create(title="Base")
        self.structure.deductions.add(
            Deduction.objects.create(
                title="PF",
                sequence=30,
                is_fixed=True,
                amount=6000.0,
                is_pretax=True,
                maximum_unit="full_period",
            )
        )

    def _status(self, based_on):
        from payroll.tax_packs import load_tax_packs

        load_tax_packs(["in_new"])
        status = FilingStatus.objects.get(filing_status__startswith="India")
        status.based_on = based_on
        status.save()
        return status

    # Comfortably clear of the 87A rebate band. At 100,000 a month both bases
    # annualise to under 12,00,000 after the standard deduction, so the rebate
    # cancelled the tax on BOTH and the two came out equal at zero -- the
    # engine was right and the figures were badly chosen.
    SAMPLE_BASIC = 300000

    def _run(self, status):
        response = self.client.post(
            reverse("salary-structure-preview", kwargs={"pk": self.structure.pk}),
            {
                "ctc": 0,
                "basic": self.SAMPLE_BASIC,
                "lop_days": 0,
                "filing_status": status.pk,
            },
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_the_tax_line_names_the_figure_it_was_read_from(self):
        for based_on, expected in (
            ("taxable_gross_pay", "taxable gross pay"),
            ("gross_pay", "gross pay"),
            ("basic_pay", "basic pay"),
        ):
            with self.subTest(based_on=based_on):
                line = self._run(self._status(based_on))["tax_line"]
                self.assertEqual(line["base_key"], based_on)
                self.assertEqual(line["base_label"], expected)
                self.assertIn(expected, line["calculation"])

    def test_the_base_amount_is_the_head_it_names(self):
        data = self._run(self._status("taxable_gross_pay"))
        self.assertAlmostEqual(
            data["tax_line"]["base_amount"], data["taxable_gross"], places=2
        )

        data = self._run(self._status("gross_pay"))
        self.assertAlmostEqual(
            data["tax_line"]["base_amount"], data["gross_pay"], places=2
        )

    def test_the_two_bases_differ_by_the_pretax_deduction(self):
        """
        Which is why naming the base matters: the bases here are 6,000 apart,
        so the tax is not the same number either.
        """
        taxable = self._run(self._status("taxable_gross_pay"))
        gross = self._run(self._status("gross_pay"))
        self.assertAlmostEqual(
            gross["tax_line"]["base_amount"] - taxable["tax_line"]["base_amount"],
            6000.0,
            places=2,
        )
        self.assertNotAlmostEqual(
            gross["tax_line"]["amount"], taxable["tax_line"]["amount"], places=2
        )


class DetailModalStructureTests(TestCase):
    """
    The modal is one block with tabs now, not three stacked ones. Three put an
    employees list, a ten-column table and an interactive example into a single
    vertical scroll inside a dialog about 760px wide.
    """

    def setUp(self):
        user = make_user("modaladmin", is_superuser=True)
        company = make_company("Modal Co")
        self.employee = make_employee(
            company=company, email="modaladmin@test.horilla", user=user
        )
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

        self.structure = SalaryStructure.objects.create(title="Tabbed")
        # An employee is on a structure through their active contract; there is
        # no M2M from the structure's side.
        from payroll.models.models import Contract
        from payroll.tests.factories_payroll import make_active_contract

        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, salary_structure_id=self.structure)

        self.structure.allowances.add(
            Allowance.objects.create(
                title="HRA", sequence=10, is_fixed=True, amount=1000.0
            )
        )
        self.structure.deductions.add(
            Deduction.objects.create(
                title="PF", sequence=20, is_fixed=True, amount=500.0
            )
        )

    def _body(self):
        response = self.client.get(
            reverse("salary-structure-detail-view", kwargs={"pk": self.structure.pk}),
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_each_reading_is_a_tab_of_one_block(self):
        body = self._body()
        for marker in (
            'data-ssd-tab="components"',
            'data-ssd-tab="example"',
            'data-ssd-tab="working"',
            'data-ssd-panel="components"',
            'data-ssd-panel="example"',
            'data-ssd-panel="working"',
        ):
            self.assertIn(marker, body)

    def test_the_working_tab_is_hidden_until_an_example_has_been_run(self):
        """
        Until then there is nothing to explain, and a tab that opens on an
        empty panel is worse than no tab.
        """
        body = self._body()
        self.assertIn("data-ssd-tab-working hidden", body)
        self.assertIn("data-ssd-working hidden", body)

    def test_the_example_hands_its_working_over_rather_than_writing_the_tab(self):
        """
        Each template owns its own markup, so the example panel still works
        anywhere that does not listen for this.
        """
        body = self._body()
        self.assertIn("structure-example:working", body)
        # Both halves: the panel dispatches it, the modal listens for it.
        self.assertIn("publishWorking", body)
        self.assertIn("workingTab.hidden", body)

    def test_the_components_tab_is_the_one_open(self):
        """Opening a structure is most often to read it, not to run an example."""
        self.assertIn('data-ssd-panel="example" hidden', self._body())

    def test_the_summary_bar_is_counts_only(self):
        """
        The name chips were the widest thing in the bar and said the least.
        The count is the figure anyone wants at a glance; who they are is the
        Employees tab.
        """
        body = self._body()
        self.assertIn("Gross Up", body)
        self.assertIn("1 earning", body)
        self.assertIn("1 deduction", body)
        self.assertIn("1 employee", body)

    def _employees_panel(self):
        """The Employees tab loads on demand, so it has its own endpoint."""
        response = self.client.get(
            reverse("salary-structure-employees", kwargs={"pk": self.structure.pk}),
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_employees_tab_shows_who_is_on_the_structure(self):
        body = self._body()
        self.assertIn('data-ssd-tab="employees"', body)
        self.assertIn('data-ssd-panel="employees"', body)
        self.assertIn(str(self.employee), self._employees_panel())

    def test_the_employees_tab_shows_what_their_contract_tells_the_engine(self):
        """
        The contract figures are the other half of every calculation the
        Components tab describes: it says "50% of basic pay", this says whose
        basic pay is what.
        """
        panel = self._employees_panel()
        self.assertIn("Golden Contract", panel)
        self.assertIn("30000.00", panel)

    def test_the_employees_tab_leads_with_the_figure_the_mode_reads(self):
        """
        Under Gross Up the wage is basic pay and the CTC is only a target;
        under CTC Down it is the other way round, so the columns swap.
        """

        def header_order():
            # Sliced to the table's own thead: the labels sit on their own
            # lines inside an {% if %}, so there is no ">Wage<" to match, and
            # "Wage" appears further down the panel as well.
            head = (
                self._employees_panel()
                .split('class="ss-emp__table"')[1]
                .split("</thead>")[0]
            )
            return head.index("Wage"), head.index("Monthly CTC")

        wage, ctc = header_order()
        self.assertLess(wage, ctc)

        self.structure.structure_mode = "ctc_down"
        self.structure.save()
        wage, ctc = header_order()
        self.assertLess(ctc, wage)

    def test_the_component_table_no_longer_scrolls_sideways(self):
        """
        Ten columns did not fit, so the last four sat off the right-hand edge.
        They are labelled chips under each component now.
        """
        body = self._body()
        self.assertNotIn("ss-components__scroll", body)
        self.assertIn("ss-components__rules", body)
        for label in ("Prorates", "In CTC", "Ceiling", "Applies"):
            self.assertIn(label, body)

    def test_the_basic_pay_note_is_shown_once_outside_the_tabs(self):
        """It applies to both readings, so it must not live in either tab."""
        body = self._body()
        self.assertEqual(body.count('class="ssd__note"'), 1)

    def test_only_the_middle_scrolls(self):
        """
        The title row and the Edit / Delete / Duplicate row are pinned, and the
        summary, note and tab bar stay put above whichever panel is open.
        Without this, running an example scrolls its own actions off the bottom
        and the structure's name off the top.
        """
        body = self._body()
        self.assertIn("hdv--sticky", body)
        self.assertIn("hdv__head", body)
        self.assertIn("hdv__body", body)
        self.assertIn("hdv__foot", body)
        self.assertIn("ssd__chrome", body)

    def test_the_scroller_is_the_open_panel_not_the_dialog_body(self):
        """
        The scrollbar has to span only the content that moves. Scrolling the
        dialog body instead leaves a full-height track running past the pinned
        summary and tabs, which reads as though those scroll too.
        """
        body = self._body()
        self.assertIn(".hdv--sticky .hdv__body", body)
        self.assertIn("overflow: hidden", body)
        self.assertIn(".ssd__panel:not([hidden])", body)
        self.assertIn("overflow-y: auto", body)

    def test_other_detail_views_keep_the_whole_dialog_scrolling(self):
        """
        sticky_chrome is opt-in: a three-line body inside a flex column would
        sit against the top of an 85vh dialog rather than shrinking to fit, so
        every other Detail View in the app has to be left alone.
        """
        from horilla_views.generic.cbv.views import HorillaDetailedView

        self.assertFalse(HorillaDetailedView.sticky_chrome)


class LossOfPayLineTests(TestCase):
    """
    Loss of pay, shown where a payslip shows it.

    It is listed with the deductions but not added to their total, and says so
    on the line. This example reduces the pay itself — the behaviour of a
    contract with "deduct leave from basic pay" on, where the engine leaves
    loss_of_pay_amount at zero — so subtracting it again would take the same
    days off twice.
    """

    def setUp(self):
        user = make_user("lopadmin", is_superuser=True)
        company = make_company("LOP Co")
        make_employee(company=company, email="lopadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}
        self.structure = SalaryStructure.objects.create(title="LOP")

    def _run(self, lop_days=0, basic=44000):
        response = self.client.post(
            reverse("salary-structure-preview", kwargs={"pk": self.structure.pk}),
            {"ctc": 0, "basic": basic, "lop_days": lop_days},
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_no_loss_of_pay_means_no_line(self):
        self.assertIsNone(self._run()["lop_line"])

    def test_the_line_states_the_days_and_what_they_cost(self):
        data = self._run(lop_days=11, basic=44000)
        line = data["lop_line"]

        self.assertIsNotNone(line)
        self.assertIn("11", line["calculation"])
        # 11 of 22 working days lost is half the wage.
        self.assertAlmostEqual(line["amount"], 22000.0, places=2)

    def test_it_is_not_counted_twice(self):
        """
        The days are already gone from gross, so the deduction total and net
        must be identical whether or not the line is shown.
        """
        data = self._run(lop_days=11, basic=44000)

        self.assertTrue(data["lop_line"]["informational"])
        self.assertAlmostEqual(data["deductions_total"], 0.0, places=2)
        self.assertAlmostEqual(data["net_pay"], data["gross_pay"], places=2)

    def test_the_line_says_why_it_is_not_subtracted(self):
        """Otherwise it reads as an amount that failed to come off."""
        self.assertIn("not subtracted again", self._run(lop_days=5)["lop_line"]["note"])

    def test_the_gross_it_sits_under_is_already_reduced(self):
        full = self._run(lop_days=0, basic=44000)["gross_pay"]
        half = self._run(lop_days=11, basic=44000)["gross_pay"]
        self.assertAlmostEqual(half, full / 2, places=2)
