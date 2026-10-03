"""
The standard pay items — loans, fines, loss of pay and the rest — as
configurable components.

These exist because the tax treatment and proration of every generated pay row
was decided by model defaults that nobody set: a reimbursement was taxable and
a loan repayment pre-tax because `is_taxable` and `is_pretax` default that way
and the generators never mentioned them. The tests that matter here are the
ones that show the generators now READ the template, and that the template
cannot be deleted out from under them.
"""

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.forms.component_forms import AllowanceForm, DeductionForm
from payroll.models.models import Allowance, Deduction, LoanAccount
from payroll.system_components import (
    BY_KEY,
    SYSTEM_COMPONENTS,
    editable_fields,
    policy_fields,
    seed,
)
from payroll.tests.factories_payroll import PERIOD_END, PERIOD_START


class SeedingTests(TestCase):
    def test_every_kind_is_seeded(self):
        # post_migrate seeds them, so they are already here.
        for entry in SYSTEM_COMPONENTS:
            with self.subTest(key=entry["key"]):
                model = Allowance if entry["kind"] == "allowance" else Deduction
                self.assertTrue(
                    model.objects.entire().filter(system_key=entry["key"]).exists()
                )

    def test_seeding_again_creates_nothing(self):
        self.assertEqual(seed(), [])

    def test_seeding_does_not_overwrite_a_changed_setting(self):
        """
        The settings on a template are the user's. Re-seeding on every migrate
        must not quietly put them back.
        """
        template = Deduction.objects.entire().get(system_key="loan_repayment")
        template.is_pretax = False
        template.save()

        seed()

        template.refresh_from_db()
        self.assertFalse(template.is_pretax)

    def test_keys_are_unique(self):
        keys = [entry["key"] for entry in SYSTEM_COMPONENTS]
        self.assertEqual(len(keys), len(set(keys)))


class EditableFieldTests(TestCase):
    """
    Only the settings that mean something. A template holds no amount, no
    formula and no employees — those come from the loan schedule, the
    attendance record and the request — so offering them would be offering
    settings that change nothing.
    """

    def test_an_earning_offers_taxability_not_pretax(self):
        """An allowance has no is_pretax; pre-tax is a deduction's phase."""
        fields = editable_fields("reimbursement")
        self.assertIn("is_taxable", fields)
        self.assertNotIn("is_pretax", fields)

    def test_a_deduction_offers_pretax_not_taxability(self):
        fields = editable_fields("loan_repayment")
        self.assertIn("is_pretax", fields)
        self.assertNotIn("is_taxable", fields)

    def test_loss_of_pay_is_not_a_component(self):
        """
        It was one briefly. It is not: the engine works it out from
        attendance, it is never a stored row, and everything about how it
        behaves is already decided per contract — what a day is a share of,
        how many days it is shared between, whether it comes off basic pay
        and whether it is pre-tax. A component holding one of those five and
        the contract holding the rest is worse than either.
        """
        self.assertNotIn("lop", BY_KEY)
        self.assertEqual(editable_fields("lop"), ())

    def test_the_form_shows_only_those(self):
        for key, form_class, model in (
            ("reimbursement", AllowanceForm, Allowance),
            ("loan_repayment", DeductionForm, Deduction),
            ("fine", DeductionForm, Deduction),
        ):
            with self.subTest(key=key):
                template = model.objects.entire().get(system_key=key)
                form = form_class(instance=template)
                self.assertEqual(sorted(form.fields), sorted(editable_fields(key)))

    def test_an_ordinary_component_keeps_its_whole_form(self):
        ordinary = Allowance.objects.create(title="Ordinary", is_fixed=True, amount=1)
        self.assertGreater(len(AllowanceForm(instance=ordinary).fields), 10)


class UndeletableTests(TestCase):
    """
    Three ways to delete a row, and the template has to survive all of them —
    a queryset delete never calls Model.delete(), which is how the loan signal
    clears a repayment schedule.
    """

    def test_the_model_refuses(self):
        template = Deduction.objects.entire().get(system_key="fine")
        template.delete()
        self.assertTrue(Deduction.objects.entire().filter(system_key="fine").exists())

    def test_a_bulk_delete_skips_it(self):
        Deduction.objects.filter(system_key="fine").delete()
        self.assertTrue(Deduction.objects.entire().filter(system_key="fine").exists())

    def test_a_bulk_delete_still_removes_everything_else(self):
        """
        Excluded, not refused: the caller wanted the instalments gone and the
        template was never one of them.
        """
        ordinary = Deduction.objects.create(title="Scratch", is_fixed=True, amount=1)
        Deduction.objects.filter(
            pk__in=[ordinary.pk, Deduction.objects.entire().get(system_key="fine").pk]
        ).delete()

        self.assertFalse(Deduction.objects.entire().filter(pk=ordinary.pk).exists())
        self.assertTrue(Deduction.objects.entire().filter(system_key="fine").exists())

    def test_the_view_refuses_and_says_so(self):
        user = make_user("delsys", is_superuser=True)
        company = make_company("Del Co")
        make_employee(company=company, email="delsys@test.horilla", user=user)
        self.client.force_login(user)

        template = Allowance.objects.entire().get(system_key="reimbursement")
        self.client.get(
            reverse("delete-allowance", kwargs={"allowance_id": template.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertTrue(
            Allowance.objects.entire().filter(system_key="reimbursement").exists()
        )

    def test_an_ordinary_component_still_deletes(self):
        ordinary = Allowance.objects.create(title="Throwaway", is_fixed=True, amount=1)
        pk = ordinary.pk
        ordinary.delete()
        self.assertFalse(Allowance.objects.entire().filter(pk=pk).exists())


class NotPayableTests(TestCase):
    """
    A template says how its kind behaves. If it were ever itself eligible, a
    zero-amount row would appear on everybody's payslip.
    """

    def setUp(self):
        self.company = make_company("Pay Co")
        self.employee = make_employee(company=self.company, email="pay@test.horilla")

    def test_no_template_is_eligible_for_anyone(self):
        from payroll.methods.component_engine import eligible_allowances
        from payroll.tests.factories_payroll import PERIOD_END, PERIOD_START

        eligible = eligible_allowances(self.employee, PERIOD_START, PERIOD_END)
        self.assertFalse(any(item.is_system for item in eligible))

    def test_no_template_can_be_put_in_a_structure(self):
        from payroll.forms.component_forms import SalaryStructureForm

        form = SalaryStructureForm()
        self.assertFalse(
            any(item.is_system for item in form.fields["allowances"].queryset)
        )
        self.assertFalse(
            any(item.is_system for item in form.fields["deductions"].queryset)
        )

    def test_no_template_is_offered_as_a_formula_target(self):
        """A percentage of a template would be a percentage of nothing."""
        from payroll.views.component_formula_views import available_codes

        keys = {entry["key"] for entry in SYSTEM_COMPONENTS}
        titles = {BY_KEY[key]["title"] for key in keys}
        offered = {row["label"] for row in available_codes()}
        self.assertFalse(titles & offered)

    def test_no_template_is_in_the_structure_picker(self):
        from payroll.forms.component_layout import component_picker_rows

        self.assertFalse(
            any(
                row["title"] in {entry["title"] for entry in SYSTEM_COMPONENTS}
                for row in component_picker_rows()
            )
        )


class GeneratorsReadTheTemplateTests(TestCase):
    """
    The point of the whole feature: the rows a loan generates take their tax
    treatment from the template rather than from model defaults.
    """

    def setUp(self):
        self.company = make_company("Gen Co")
        self.employee = make_employee(company=self.company, email="gen@test.horilla")

    def _loan(self, **kwargs):
        from datetime import date

        defaults = dict(
            employee_id=self.employee,
            title="Test Loan",
            loan_amount=12000,
            provided_date=date(2026, 4, 1),
            installments=2,
            installment_start_date=date(2026, 5, 1),
            type="loan",
        )
        defaults.update(kwargs)
        return LoanAccount.objects.create(**defaults)

    def test_a_repayment_follows_the_template(self):
        template = Deduction.objects.entire().get(system_key="loan_repayment")
        template.is_pretax = False
        template.save()

        loan = self._loan()
        instalments = list(loan.deduction_ids.all())

        self.assertTrue(instalments)
        for instalment in instalments:
            self.assertFalse(instalment.is_pretax)

    def test_a_payout_follows_the_template(self):
        template = Allowance.objects.entire().get(system_key="loan_payout")
        template.is_taxable = False
        template.save()

        loan = self._loan()
        self.assertIsNotNone(loan.allowance_id)
        self.assertFalse(loan.allowance_id.is_taxable)

    def test_an_advance_and_a_loan_can_differ(self):
        """
        They share one model and one generator, so before this they were
        necessarily treated the same.
        """
        Deduction.objects.entire().filter(system_key="loan_repayment").update(
            is_pretax=True
        )
        Deduction.objects.entire().filter(system_key="advance_repayment").update(
            is_pretax=False
        )

        loan = self._loan(title="A Loan")
        advance = self._loan(title="An Advance", type="advanced_salary")

        self.assertTrue(all(d.is_pretax for d in loan.deduction_ids.all()))
        self.assertFalse(any(d.is_pretax for d in advance.deduction_ids.all()))

    def test_policy_fields_falls_back_when_nothing_is_seeded(self):
        """
        A database that predates the templates keeps working: the fallback is
        the same behaviour it had before.
        """
        Deduction.objects.entire().filter(system_key="fine").update(system_key="")
        self.assertEqual(policy_fields("fine"), dict(BY_KEY["fine"]["defaults"]))


class NoAmountBlockTests(TestCase):
    """
    A standard pay item has no amount to set.

    Its figure comes from the event that raised it — the loan schedule, the
    attendance record, the approved expense — so the Amount step was offering
    a ceiling and a proration basis for something that is already an exact
    number. Nothing to prorate means nothing to divide by a shorter period,
    which is exactly why inheriting calendar-day proration was wrong.
    """

    def test_no_kind_offers_an_amount_or_a_ceiling(self):
        for entry in SYSTEM_COMPONENTS:
            with self.subTest(key=entry["key"]):
                fields = editable_fields(entry["key"])
                for unwanted in ("amount", "maximum_amount", "has_max_limit"):
                    self.assertNotIn(unwanted, fields)

    def test_no_kind_offers_a_proration_basis(self):
        for entry in SYSTEM_COMPONENTS:
            with self.subTest(key=entry["key"]):
                self.assertNotIn("maximum_unit", editable_fields(entry["key"]))

    def test_each_kind_offers_exactly_its_tax_treatment(self):
        for entry in SYSTEM_COMPONENTS:
            with self.subTest(key=entry["key"]):
                expected = (
                    ("is_taxable",) if entry["kind"] == "allowance" else ("is_pretax",)
                )
                self.assertEqual(editable_fields(entry["key"]), expected)

    def test_the_proration_default_is_still_applied_to_generated_rows(self):
        """
        Removing the SETTING must not remove the behaviour: these rows are
        flat, and without this they would fall back to the model default of
        calendar-day proration that the whole feature exists to override.
        """
        for entry in SYSTEM_COMPONENTS:
            if entry["key"] == "lop":
                continue  # never a stored row
            with self.subTest(key=entry["key"]):
                self.assertEqual(
                    policy_fields(entry["key"])["maximum_unit"], "full_period"
                )

    def test_the_form_has_a_single_step(self):
        """With one field left there is nothing for a second step to hold."""
        from payroll.forms.component_layout import steps_for

        template = Deduction.objects.entire().get(system_key="fine")
        self.assertEqual(len(steps_for(DeductionForm(instance=template))), 1)


class LossOfPayReachesTheEngineTests(TestCase):
    """
    The Loss of pay component's one setting, doing something.

    Loss of pay is not a Deduction row — the engine computes it from
    attendance — so it was in neither the pre-tax nor the post-tax total that
    calculate_taxable_gross_pay subtracts. A contract that deducts it
    separately therefore taxed the employee on pay they did not receive.

    That is also what the "Is Pretax" setting on the template now controls. It
    controlled nothing when it was added.
    """

    def setUp(self):
        from payroll.models.models import Contract

        company = make_company("LOP Engine Co")
        self.employee = make_employee(company=company, email="lopengine@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        self.contract = None

    def setUpContract(self, **kwargs):
        from payroll.tests.factories_payroll import make_active_contract

        return make_active_contract(self.employee, **kwargs)

    def _taxable_gross(self, loss_of_pay_amount):
        from payroll.methods.payslip_calc import calculate_taxable_gross_pay

        return calculate_taxable_gross_pay(
            employee=self.employee,
            # Real dates: calculate_gross_pay reaches
            # update_compensation_deduction, which builds a queryset from
            # them, so None is not a stand-in for "no period".
            start_date=PERIOD_START,
            end_date=PERIOD_END,
            basic_pay=50000.0,
            total_allowance=0.0,
            allowances={"allowances": []},
            day_dict=[],
            loss_of_pay_amount=loss_of_pay_amount,
        )["taxable_gross_pay"]

    def test_a_separately_deducted_loss_of_pay_lowers_the_tax_base(self):
        with_lop = self._taxable_gross(5000.0)
        without = self._taxable_gross(0)
        self.assertAlmostEqual(without - with_lop, 5000.0, places=2)

    def test_turning_the_contract_setting_off_leaves_it_in_the_tax_base(self):
        """
        The setting is the whole of what that toggle does, so it has to be
        observable from the figure.
        """
        self.setUpContract(loss_of_pay_is_pretax=False)
        self.assertAlmostEqual(
            self._taxable_gross(5000.0), self._taxable_gross(0), places=2
        )

    def test_it_is_pre_tax_by_default(self):
        self.setUpContract()
        self.assertAlmostEqual(
            self._taxable_gross(0) - self._taxable_gross(5000.0), 5000.0, places=2
        )

    def test_nothing_is_subtracted_when_it_came_off_basic_pay(self):
        """
        With the contract taking it off basic, loss_of_pay_amount is zero and
        the days are already out of gross. Subtracting again would take them
        off twice.
        """
        self.assertAlmostEqual(self._taxable_gross(0), 50000.0, places=2)
