"""
The salary structure detail view.

It used to show allowances in one column and deductions in another, titles
only. That hid the two things someone opening a structure actually wants: what
each component works out to, and the single order they run in across both
lists — which is what decides whether a percentage is allowed to refer to
another component at all.

The worked example is asserted against the engine rather than against fixed
numbers. Its whole value is that it cannot disagree with a payslip; a test with
hardcoded totals would pass just as happily if it started computing them a
second way.
"""

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.forms.component_layout import component_picker_rows
from payroll.methods.component_summary import (
    applies_summary,
    calculation_summary,
    proration_summary,
)
from payroll.models.models import (
    Allowance,
    ApplyCondition,
    Deduction,
    FilingStatus,
    SalaryStructure,
)


class Stub:
    """A component-shaped object, for the summariser's own behaviour."""

    pk = None
    apply_conditions = None

    def __init__(self, **kw):
        self.is_fixed = False
        self.amount = None
        self.based_on = None
        self.rate = None
        self.formula = ""
        self.percentage_of_code = ""
        self.maximum_unit = "full_period"
        self.has_max_limit = False
        self.maximum_amount = None
        self.if_choice = "basic_pay"
        self.if_condition = "gt"
        self.if_amount = 0
        self.if_component_code = ""
        self.start_range = None
        self.end_range = None
        self.per_children_fixed_amount = None
        self.__dict__.update(kw)


class CalculationSummaryTests(TestCase):
    def test_a_fixed_amount_reads_as_the_amount(self):
        self.assertEqual(
            calculation_summary(Stub(is_fixed=True, amount=1600)), "1,600.00"
        )

    def test_a_percentage_names_what_it_is_a_percentage_of(self):
        self.assertEqual(
            calculation_summary(Stub(based_on="basic_pay", rate=50)), "50% of BASIC"
        )
        self.assertEqual(
            calculation_summary(Stub(based_on="gross_pay", rate=2.5)), "2.5% of GROSS"
        )

    def test_a_component_percentage_names_the_target_code(self):
        self.assertEqual(
            calculation_summary(
                Stub(based_on="component", rate=40, percentage_of_code="basic")
            ),
            "40% of BASIC",
        )

    def test_a_formula_reads_as_the_formula(self):
        self.assertEqual(
            calculation_summary(Stub(based_on="formula", formula="BASIC + HRA")),
            "BASIC + HRA",
        )

    def test_a_balance_component_says_so(self):
        self.assertEqual(
            calculation_summary(Stub(based_on="balance")), "Balance of CTC"
        )

    def test_a_per_unit_amount_names_the_unit(self):
        self.assertEqual(
            calculation_summary(
                Stub(based_on="children", per_children_fixed_amount=250)
            ),
            "250.00 per child",
        )

    def test_an_unconfigured_component_says_so_rather_than_guessing(self):
        self.assertEqual(calculation_summary(Stub()), "Not configured")

    def test_a_percentage_inherits_its_proration(self):
        """
        Neither "Yes" nor "No" is true of a percentage: it follows the period
        through whatever it is a percentage of, without a basis of its own.
        Reporting "No" would suggest it stays flat on a part-month period, and
        applying a basis as well would prorate it twice.
        """
        self.assertEqual(
            proration_summary(Stub(based_on="basic_pay", rate=10)), "Inherited"
        )
        self.assertEqual(
            proration_summary(Stub(based_on="formula", formula="BASIC")), "Inherited"
        )

    def test_a_flat_amount_reports_the_basis_it_actually_uses(self):
        """The only case where the basis governs anything."""
        self.assertEqual(
            proration_summary(
                Stub(is_fixed=True, amount=1, maximum_unit="full_period")
            ),
            "No",
        )

    def test_the_default_gate_is_reported_as_always(self):
        """
        Every component carries a hidden "basic pay > 0" rule, which is really
        asking whether the employee is paid at all. Reporting that as a
        condition someone configured would make every component look gated.
        """
        self.assertEqual(applies_summary(Stub(is_fixed=True, amount=1)), "Always")

    def test_a_real_gate_is_spelled_out(self):
        summary = applies_summary(
            Stub(
                is_fixed=True,
                amount=1,
                if_choice="gross_pay",
                if_condition="le",
                if_amount=21000,
            )
        )
        self.assertIn("GROSS", summary)
        self.assertIn("21,000.00", summary)


class ComponentRowsTests(TestCase):
    def setUp(self):
        self.structure = SalaryStructure.objects.create(title="Rows")

    def test_earnings_and_deductions_share_one_evaluation_order(self):
        """
        The order runs across both, which two side-by-side columns could not
        show. A deduction at 100 is worked out before an allowance at 200.
        """
        late = Allowance.objects.create(
            title="Special", sequence=200, is_fixed=True, amount=1
        )
        early = Deduction.objects.create(
            title="PF", sequence=100, is_fixed=True, amount=1
        )
        self.structure.allowances.add(late)
        self.structure.deductions.add(early)

        rows = self.structure.component_rows
        self.assertEqual([row["title"] for row in rows], ["PF", "Special"])
        self.assertEqual([row["kind"] for row in rows], ["deduction", "earning"])

    def test_each_row_carries_what_the_table_shows(self):
        allowance = Allowance.objects.create(
            title="HRA",
            sequence=20,
            is_fixed=False,
            based_on="basic_pay",
            rate=50.0,
            is_taxable=True,
        )
        self.structure.allowances.add(allowance)

        row = self.structure.component_rows[0]
        self.assertEqual(row["code"], allowance.code)
        self.assertEqual(str(row["type_label"]), "Earning")
        self.assertEqual(row["calculation"], "50% of BASIC")
        self.assertEqual(str(row["taxable"]), "Yes")

    def test_a_deduction_is_labelled_by_which_phase_it_runs_in(self):
        for kwargs, expected in (
            ({"is_tax": True}, "Tax"),
            ({"is_pretax": True}, "Pre-tax deduction"),
            ({"is_pretax": False}, "Deduction"),
        ):
            with self.subTest(expected=expected):
                self.structure.deductions.clear()
                deduction = Deduction.objects.create(
                    title=f"D {expected}", is_fixed=True, amount=1, **kwargs
                )
                self.structure.deductions.add(deduction)
                self.assertEqual(
                    str(self.structure.component_rows[0]["type_label"]), expected
                )

    def test_extra_apply_rules_are_counted(self):
        allowance = Allowance.objects.create(
            title="Gated",
            is_fixed=True,
            amount=1,
            if_choice="basic_pay",
            if_condition="gt",
            if_amount=0,
        )
        allowance.apply_conditions.add(
            ApplyCondition.objects.create(choice="basic_pay", condition="gt", amount=5)
        )
        self.structure.allowances.add(allowance)
        self.assertIn("1 more", self.structure.component_rows[0]["applies"])

    def test_a_calculated_component_reports_inherited_proration(self):
        """
        "No" would be wrong: a percentage of basic follows the period through
        the basic it is a percentage of. Applying a basis as well would prorate
        it twice.
        """
        allowance = Allowance.objects.create(
            title="HRA",
            is_fixed=False,
            based_on="basic_pay",
            rate=50.0,
            maximum_unit="month_calendar_days",
        )
        self.structure.allowances.add(allowance)
        self.assertEqual(self.structure.component_rows[0]["prorates"], "Inherited")

    def test_a_flat_component_reports_its_own_basis(self):
        allowance = Allowance.objects.create(
            title="Meal",
            is_fixed=True,
            amount=1500.0,
            maximum_unit="month_calendar_days",
        )
        self.structure.allowances.add(allowance)
        self.assertIn("calendar", self.structure.component_rows[0]["prorates"].lower())

    def test_in_ctc_is_derived_from_what_the_component_is(self):
        """
        No stored flag. An earning is paid out and an employer share is a
        company cost, so both sit inside the total cost; a deduction comes out
        of gross, which is already counted.
        """
        self.structure.allowances.add(
            Allowance.objects.create(title="HRA", is_fixed=True, amount=1)
        )
        self.structure.deductions.add(
            Deduction.objects.create(title="PT", is_fixed=True, amount=1),
            Deduction.objects.create(
                title="PF", is_fixed=True, amount=1, employer_rate=12.0
            ),
        )
        by_title = {
            row["title"]: row["in_ctc"] for row in self.structure.component_rows
        }
        self.assertEqual(by_title["HRA"], "Yes")
        self.assertEqual(by_title["PT"], "—")
        self.assertIn("Employer", by_title["PF"])

    def test_an_empty_structure_has_no_rows(self):
        self.assertEqual(self.structure.component_rows, [])


class SampleInputUsageTests(TestCase):
    """
    Which sample figures the example offers.

    A box that changes nothing is worse than no box: it invites someone to set
    a CTC, watch the totals not move, and conclude the example is broken. So
    each is enabled only when something in the structure reads it.
    """

    def setUp(self):
        self.structure = SalaryStructure.objects.create(title="Usage")

    def _add(self, **kw):
        kw.setdefault("title", "C")
        kw.setdefault("is_fixed", False)
        allowance = Allowance.objects.create(**kw)
        self.structure.allowances.add(allowance)
        return allowance

    def test_ctc_is_offered_only_when_something_reads_it(self):
        self._add(based_on="basic_pay", rate=50.0)
        inputs = self.structure.sample_inputs
        self.assertFalse(inputs["ctc"]["used"])
        self.assertIn("CTC", str(inputs["ctc"]["why"]))

    def test_a_percentage_of_ctc_turns_it_on(self):
        self._add(based_on="component", percentage_of_code="CTC", rate=50.0)
        self.assertTrue(self.structure.sample_inputs["ctc"]["used"])

    def test_a_balance_earning_turns_it_on(self):
        self._add(based_on="balance")
        self.assertTrue(self.structure.sample_inputs["ctc"]["used"])

    def test_a_formula_mentioning_ctc_turns_it_on(self):
        self._add(based_on="formula", formula="CTC * 0.5")
        self.assertTrue(self.structure.sample_inputs["ctc"]["used"])

    def test_a_ctc_down_structure_always_reads_it(self):
        self.structure.structure_mode = "ctc_down"
        self.structure.save()
        self.assertTrue(self.structure.sample_inputs["ctc"]["used"])

    def test_basic_is_offered_when_it_comes_from_the_contract(self):
        self._add(based_on="basic_pay", rate=50.0)
        self.assertTrue(self.structure.sample_inputs["basic"]["used"])

    def test_basic_is_not_offered_when_an_earning_works_it_out(self):
        self._add(title="Basic Pay", is_basic_pay=True, is_fixed=True, amount=1)
        inputs = self.structure.sample_inputs
        self.assertFalse(inputs["basic"]["used"])
        self.assertIn("Basic Pay", str(inputs["basic"]["why"]))

    def test_basic_is_not_offered_under_ctc_down(self):
        """It comes out of the package, so a typed figure would be unrelated."""
        self.structure.structure_mode = "ctc_down"
        self.structure.save()
        self._add(title="Basic Pay", is_basic_pay=True, is_fixed=True, amount=1)
        inputs = self.structure.sample_inputs
        self.assertFalse(inputs["basic"]["used"])
        self.assertIn("CTC", str(inputs["basic"]["why"]))

    def test_an_enabled_figure_gives_no_reason(self):
        """The hint is only shown for a disabled one, so it must be empty."""
        self._add(based_on="component", percentage_of_code="CTC", rate=50.0)
        inputs = self.structure.sample_inputs
        self.assertEqual(str(inputs["ctc"]["why"]), "")


class DetailViewRenderTests(TestCase):
    def setUp(self):
        user = make_user("ssadmin", is_superuser=True)
        company = make_company("SS Co")
        make_employee(company=company, email="ssadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

        self.structure = SalaryStructure.objects.create(title="Standard")
        basic = Allowance.objects.create(
            title="Basic Pay", sequence=10, is_fixed=True, amount=25000.0
        )
        hra = Allowance.objects.create(
            title="HRA",
            sequence=20,
            is_fixed=False,
            based_on="component",
            percentage_of_code=basic.code,
            rate=50.0,
        )
        self.structure.allowances.add(basic, hra)

    def test_the_detail_view_renders_the_component_table(self):
        response = self.client.get(
            reverse("salary-structure-detail-view", kwargs={"pk": self.structure.pk}),
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()

        self.assertIn("ss-components__table", body)
        self.assertIn("Basic Pay", body)
        self.assertIn("50% of", body)
        self.assertIn("Evaluated top to bottom", body)
        # And the example panel, pointed at its own endpoint.
        self.assertIn("data-structure-example", body)
        # CTC is disabled here: nothing in this structure reads it.
        self.assertIn("data-example-ctc", body)
        self.assertIn("disabled", body)
        self.assertIn(
            reverse("salary-structure-preview", kwargs={"pk": self.structure.pk}), body
        )


class ExamplePreviewTests(TestCase):
    def setUp(self):
        user = make_user("exadmin", is_superuser=True)
        company = make_company("Ex Co")
        make_employee(company=company, email="exadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}
        self.structure = SalaryStructure.objects.create(title="Example")

    def _earning(self, data, title):
        """
        The earning line for one component. By title, not by position: the
        first line is the synthetic Basic Pay row when basic comes from the
        contract.
        """
        return next(line for line in data["earning_lines"] if line["title"] == title)

    def _run(self, ctc=50000, basic=50000, lop_days=0, filing_status=""):
        response = self.client.post(
            reverse("salary-structure-preview", kwargs={"pk": self.structure.pk}),
            {
                "ctc": ctc,
                "basic": basic,
                "lop_days": lop_days,
                "filing_status": filing_status,
            },
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_a_fixed_earning_comes_back_at_its_amount(self):
        allowance = Allowance.objects.create(
            title="Travel",
            sequence=10,
            is_fixed=True,
            amount=1600.0,
            maximum_unit="full_period",
        )
        self.structure.allowances.add(allowance)

        data = self._run()
        self.assertTrue(data["ok"])
        self.assertEqual(self._earning(data, "Travel")["amount"], 1600.0)
        self.assertEqual(data["earnings_total"], 1600.0)

    def test_a_percentage_of_basic_uses_the_sample_wage(self):
        allowance = Allowance.objects.create(
            title="HRA", sequence=10, is_fixed=False, based_on="basic_pay", rate=50.0
        )
        self.structure.allowances.add(allowance)
        self.assertEqual(
            self._earning(self._run(basic=50000), "HRA")["amount"], 25000.0
        )

    def test_loss_of_pay_days_reduce_the_period(self):
        """
        11 of 22 working days lost halves the wage the percentage is taken of,
        the same way compute_salary_on_period prorates it.
        """
        allowance = Allowance.objects.create(
            title="HRA", sequence=10, is_fixed=False, based_on="basic_pay", rate=50.0
        )
        self.structure.allowances.add(allowance)

        data = self._run(basic=50000, lop_days=11)
        self.assertEqual(data["worked_days"], 11)
        self.assertEqual(self._earning(data, "HRA")["amount"], 12500.0)

    def test_a_flat_amount_on_a_monthly_basis_prorates_with_the_period(self):
        allowance = Allowance.objects.create(
            title="Meal",
            sequence=10,
            is_fixed=True,
            amount=3000.0,
            maximum_unit="month_working_days",
        )
        self.structure.allowances.add(allowance)
        data = self._run(lop_days=11)
        self.assertAlmostEqual(
            self._earning(data, "Meal")["amount"], 3000 * 11 / 22, places=2
        )

    def test_a_component_that_needs_attendance_says_so_instead_of_guessing(self):
        allowance = Allowance.objects.create(
            title="OT",
            sequence=10,
            is_fixed=False,
            based_on="overtime",
            amount_per_one_hr=100.0,
        )
        self.structure.allowances.add(allowance)

        row = self._earning(self._run(), "OT")
        self.assertIsNone(row["amount"])
        self.assertIn("attendance", row["note"].lower())

    def test_deductions_are_shown_now_that_gross_is_known(self):
        """
        A deduction needs gross, which exists once the earnings pass has run —
        so the example can evaluate them through the real pre-tax and post-tax
        strategies rather than leaving them out.
        """
        self.structure.allowances.add(
            Allowance.objects.create(
                title="Basic",
                sequence=10,
                is_fixed=True,
                amount=20000.0,
                maximum_unit="full_period",
            )
        )
        self.structure.deductions.add(
            Deduction.objects.create(
                title="PF",
                sequence=100,
                is_fixed=True,
                amount=1800.0,
                maximum_unit="full_period",
            )
        )
        data = self._run()

        self.assertEqual(len(data["deduction_lines"]), 1)
        self.assertEqual(data["deduction_lines"][0]["amount"], 1800.0)
        self.assertEqual(data["deductions_total"], 1800.0)
        self.assertEqual(data["net_pay"], data["gross_pay"] - 1800.0)

    def test_an_employer_share_is_reported_separately_from_the_deduction(self):
        """
        It is a company cost, not money taken from the employee, so it must not
        land in the deduction total or reduce net pay.
        """
        self.structure.deductions.add(
            Deduction.objects.create(
                title="PF",
                sequence=100,
                is_fixed=True,
                amount=1800.0,
                employer_rate=100.0,
                maximum_unit="full_period",
            )
        )
        data = self._run()

        self.assertEqual(data["deduction_lines"][0]["employer"], 1800.0)
        self.assertEqual(data["employer_total"], 1800.0)
        self.assertEqual(data["deductions_total"], 1800.0)

    def test_the_sample_period_is_thirty_calendar_days(self):
        """
        Matches the calendar-days proration default, so the example and the
        default setting describe the same month.
        """
        data = self._run()
        self.assertEqual(data["calendar_days"], 30)
        self.assertEqual(data["working_days"], 22)

    def test_a_wage_that_is_not_a_number_is_refused(self):
        response = self.client.post(
            reverse("salary-structure-preview", kwargs={"pk": self.structure.pk}),
            {"ctc": "abc", "basic": "0"},
            **self.hx,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_ctc_down_reports_what_is_left_unaccounted(self):
        """
        The gap is almost always a missing balance earning, so the panel can
        name that rather than leaving someone to spot it in the totals.
        """
        self.structure.structure_mode = "ctc_down"
        self.structure.save()
        self.structure.allowances.add(
            Allowance.objects.create(
                title="Basic Pay",
                code="BASIC",
                sequence=10,
                is_fixed=False,
                based_on="component",
                percentage_of_code="CTC",
                rate=50.0,
            )
        )
        data = self._run(basic=50000)

        self.assertFalse(data["ctc_reconciles"])
        self.assertAlmostEqual(data["ctc_gap"], data["ctc_target"] / 2, places=2)

    def test_ctc_down_reconciles_once_a_balance_earning_absorbs_the_rest(self):
        self.structure.structure_mode = "ctc_down"
        self.structure.save()
        self.structure.allowances.add(
            Allowance.objects.create(
                title="Basic Pay",
                code="BASIC",
                sequence=10,
                is_fixed=False,
                based_on="component",
                percentage_of_code="CTC",
                rate=50.0,
            ),
            Allowance.objects.create(
                title="Special", sequence=900, is_fixed=False, based_on="balance"
            ),
        )
        data = self._run(basic=50000)

        self.assertTrue(data["ctc_reconciles"])
        self.assertAlmostEqual(data["ctc_gap"], 0.0, places=2)

    def test_basic_pay_is_asked_for_only_when_no_earning_supplies_it(self):
        """
        With a flagged earning the structure works basic out itself, so a typed
        figure would be a second, unrelated number.
        """
        self.assertFalse(self.structure.has_basic_pay_component)
        self.assertTrue(self._run()["needs_basic_input"])

        self.structure.allowances.add(
            Allowance.objects.create(
                title="Basic Pay",
                sequence=10,
                is_basic_pay=True,
                is_fixed=True,
                amount=20000.0,
                maximum_unit="full_period",
            )
        )
        self.structure.refresh_from_db()
        self.assertTrue(self.structure.has_basic_pay_component)
        self.assertFalse(self._run()["needs_basic_input"])

    def test_a_flagged_earning_is_reported_as_not_paid_when_basic_is_given(self):
        """
        The precedence, shown rather than silently applied: with a contract
        basic the earning is skipped, and the example says why instead of
        leaving a line out.
        """
        self.structure.allowances.add(
            Allowance.objects.create(
                title="Basic Pay",
                sequence=10,
                is_basic_pay=True,
                is_fixed=True,
                amount=20000.0,
                maximum_unit="full_period",
            )
        )
        line = self._run(basic=30000)["earning_lines"][0]
        self.assertIsNone(line["amount"])
        self.assertIn("contract", line["note"].lower())

    def test_the_reconciliation_is_shown_in_gross_up_too(self):
        """
        It answers "does this structure add up to the package I mean to offer?",
        which is a question in either mode.
        """
        self.structure.allowances.add(
            Allowance.objects.create(
                title="Bonus",
                sequence=10,
                is_fixed=True,
                amount=1000.0,
                maximum_unit="full_period",
            )
        )
        data = self._run(ctc=50000, basic=0)
        self.assertIn("ctc_gap", data)
        self.assertFalse(data["ctc_reconciles"])

    def test_basic_pay_appears_as_an_earnings_line(self):
        """
        Without it the earnings read "HRA 1,125" above a gross of 26,125, and
        the missing 25,000 has no visible origin. The real payslip shows basic
        as the first row of the same table.
        """
        self.structure.allowances.add(
            Allowance.objects.create(
                title="HRA",
                sequence=20,
                is_fixed=False,
                based_on="basic_pay",
                rate=4.5,
            )
        )
        data = self._run(basic=25000)

        first = data["earning_lines"][0]
        self.assertEqual(first["code"], "BASIC")  # deliberately positional
        self.assertEqual(first["amount"], 25000.0)
        # And it adds up: basic + HRA is the gross shown.
        self.assertAlmostEqual(
            data["gross_pay"],
            sum(line["amount"] for line in data["earning_lines"]),
            places=2,
        )

    def test_basic_pay_is_not_duplicated_when_an_earning_supplies_it(self):
        """
        The flagged earning is already a line of its own, so a synthetic one
        would show basic twice and imply a gross that is too high.
        """
        self.structure.allowances.add(
            Allowance.objects.create(
                title="Basic Pay",
                sequence=10,
                is_basic_pay=True,
                is_fixed=True,
                amount=20000.0,
                maximum_unit="full_period",
            )
        )
        lines = self._run()["earning_lines"]
        self.assertEqual(len([l for l in lines if l["code"] == "BASIC"]), 0)
        self.assertEqual(len(lines), 1)

    def test_income_tax_is_left_out_until_a_filing_status_is_chosen(self):
        data = self._run(basic=50000)
        self.assertIsNone(data["tax_line"])
        self.assertFalse(data["tax_included"])

    def test_choosing_a_filing_status_taxes_the_example(self):
        """
        Through compute_yearly_tax, which is the only implementation of what a
        filing status means — the same function calculate_taxable_amount calls
        for a real payslip.
        """
        from payroll.methods.tax_calc import compute_yearly_tax
        from payroll.tax_packs import load_tax_packs

        load_tax_packs(["in_new"])
        status = FilingStatus.objects.get(filing_status__startswith="India — New")

        data = self._run(basic=100000, filing_status=status.pk)
        self.assertTrue(data["tax_included"])

        # Asserted against the engine, not a hardcoded figure: a fixed number
        # would keep passing if the preview started working tax out its own way.
        yearly, _breakdown = compute_yearly_tax(status, round(100000 / 30 * 365, 2))
        self.assertAlmostEqual(data["tax_line"]["amount"], yearly / 365 * 30, places=2)

    def test_the_tax_is_counted_in_the_deduction_total_and_net(self):
        from payroll.tax_packs import load_tax_packs

        load_tax_packs(["in_new"])
        status = FilingStatus.objects.get(filing_status__startswith="India — New")

        without = self._run(basic=100000)
        with_tax = self._run(basic=100000, filing_status=status.pk)

        tax = with_tax["tax_line"]["amount"]
        self.assertAlmostEqual(
            with_tax["deductions_total"], without["deductions_total"] + tax, places=2
        )
        self.assertAlmostEqual(with_tax["net_pay"], without["net_pay"] - tax, places=2)

    def test_a_filing_status_that_cannot_compute_is_reported_not_raised(self):
        """
        A broken Python formula must not take the whole panel down; it says so
        on its own line, the way the payslip path reports it per employee.
        """
        status = FilingStatus.objects.create(
            filing_status="Broken",
            based_on="basic_pay",
            use_py=True,
            python_code="def calculate_federal_tax(y): return 1 / 0",
        )
        data = self._run(basic=50000, filing_status=status.pk)
        self.assertIsNone(data["tax_line"]["amount"])
        self.assertTrue(data["tax_line"]["note"])
        self.assertFalse(data["tax_included"])

    def test_the_preview_saves_nothing(self):
        from payroll.models.models import Payslip

        self.structure.allowances.add(
            Allowance.objects.create(title="Travel", is_fixed=True, amount=100.0)
        )
        before = Payslip.objects.count()
        self._run()
        self.assertEqual(Payslip.objects.count(), before)


class ComponentPickerTests(TestCase):
    """
    The structure form's component chooser.

    It was two tag boxes. "House Rent Allowance (HRA)" and "House Rent
    Allowance (Metro)" are two near-identical chips there, and nothing says
    which pays half of basic and which pays a flat 1,600 — choosing between
    them meant opening each component in another screen.
    """

    def setUp(self):
        user = make_user("pickeradmin", is_superuser=True)
        company = make_company("Picker Co")
        make_employee(company=company, email="pickeradmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

        self.hra = Allowance.objects.create(
            title="HRA",
            sequence=20,
            is_fixed=False,
            based_on="basic_pay",
            rate=50.0,
        )
        self.pf = Deduction.objects.create(
            title="PF",
            sequence=100,
            is_fixed=False,
            based_on="basic_pay",
            rate=12.0,
            is_pretax=True,
        )
        self.structure = SalaryStructure.objects.create(title="Picked")
        self.structure.allowances.add(self.hra)

    def _body(self, pk=None):
        url = (
            reverse("update-salary-structure", kwargs={"pk": pk})
            if pk
            else reverse("create-salary-structure")
        )
        response = self.client.get(url, **self.hx)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_picker_replaces_the_tag_boxes(self):
        body = self._body(self.structure.pk)
        self.assertIn("data-component-picker", body)
        self.assertIn('name="allowances" value="%s"' % self.hra.pk, body)
        self.assertIn('name="deductions" value="%s"' % self.pf.pk, body)

    def test_it_says_what_each_component_does(self):
        """The reason for a table rather than a chip."""
        body = self._body(self.structure.pk)
        self.assertIn("50% of BASIC", body)
        self.assertIn("12% of BASIC", body)

    def test_what_is_already_on_the_structure_is_ticked(self):
        # Keyed by (field, pk): the two models have separate primary key
        # sequences, so an allowance and a deduction can both be #1 and a
        # pk-only key silently overwrites one with the other.
        rows = {
            (row["field"], row["pk"]): row["checked"]
            for row in component_picker_rows(
                self.structure.allowances.values_list("pk", flat=True),
                self.structure.deductions.values_list("pk", flat=True),
            )
        }
        self.assertTrue(rows[("allowances", self.hra.pk)])
        self.assertFalse(rows[("deductions", self.pf.pk)])

    def test_earnings_and_deductions_share_the_evaluation_order(self):
        """
        One list, ordered the way the engine runs them, so the chooser doubles
        as a preview of that order.
        """
        rows = component_picker_rows()
        sequences = [row["sequence"] or 0 for row in rows]
        self.assertEqual(sequences, sorted(sequences))

    def test_loan_instalments_are_not_offered(self):
        """
        One auto-generated Deduction per due date. They belong to an employee's
        repayment schedule, not to a reusable structure.
        """
        Deduction.objects.create(
            title="Loan - 2026-01-01",
            is_fixed=True,
            amount=100.0,
            is_installment=True,
        )
        titles = [row["title"] for row in component_picker_rows()]
        self.assertNotIn("Loan - 2026-01-01", titles)

    def test_saving_through_the_picker_sets_the_components(self):
        from django.http import QueryDict

        data = QueryDict(mutable=True)
        data["title"] = "Picked"
        data["structure_mode"] = "gross_up"
        data.setlist("allowances", [str(self.hra.pk)])
        data.setlist("deductions", [str(self.pf.pk)])

        response = self.client.post(
            reverse("update-salary-structure", kwargs={"pk": self.structure.pk}),
            data,
            **self.hx,
        )
        self.assertIn(response.status_code, (200, 302))

        self.structure.refresh_from_db()
        self.assertIn(self.pf, self.structure.deductions.all())
        self.assertIn(self.hra, self.structure.allowances.all())
