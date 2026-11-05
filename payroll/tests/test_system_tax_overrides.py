"""Tax treatment of the standard pay items, set per employee."""

from datetime import date

from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from horilla.testkit import make_company, make_employee
from base.models import Department, JobPosition
from payroll.forms.component_forms import AllowanceForm, DeductionForm, EmployeePickWidget
from payroll.models.models import (
    Allowance,
    Deduction,
    LoanAccount,
    Payslip,
    SystemComponentTaxOverride,
)
from payroll.system_components import policy_fields, tax_field


class Fixture(TestCase):
    def setUp(self):
        company = make_company("Tax Override Co")
        self.adam = make_employee(company=company, email="adam-tax@test.horilla")
        self.bea = make_employee(company=company, email="bea-tax@test.horilla")

    def _loan(self, employee):
        return LoanAccount.objects.create(
            employee_id=employee,
            title="Loan",
            loan_amount=12000,
            provided_date=date(2026, 4, 1),
            installments=2,
            installment_start_date=date(2026, 5, 1),
            type="loan",
        )

    def _override(self, key, employee, value):
        return SystemComponentTaxOverride.objects.create(
            system_key=key, employee_id=employee, value=value
        )


class PolicyTests(Fixture):
    def test_the_tax_field_of_each_kind(self):
        self.assertEqual(tax_field("loan_payout"), "is_taxable")
        self.assertEqual(tax_field("loan_repayment"), "is_pretax")

    def test_an_override_wins_for_that_employee_only(self):
        self._override("loan_repayment", self.adam, False)
        self.assertFalse(policy_fields("loan_repayment", employee=self.adam)["is_pretax"])
        self.assertTrue(policy_fields("loan_repayment", employee=self.bea)["is_pretax"])
        self.assertTrue(policy_fields("loan_repayment")["is_pretax"])

    def test_an_override_does_not_touch_the_other_settings(self):
        self._override("loan_repayment", self.adam, False)
        plain = policy_fields("loan_repayment")
        overridden = policy_fields("loan_repayment", employee=self.adam)
        self.assertEqual(
            {k: v for k, v in plain.items() if k != "is_pretax"},
            {k: v for k, v in overridden.items() if k != "is_pretax"},
        )


class GenerationTests(Fixture):
    def test_the_repayments_of_an_overridden_employee_follow_the_override(self):
        self._override("loan_repayment", self.adam, False)
        mine = list(self._loan(self.adam).deduction_ids.all())
        hers = list(self._loan(self.bea).deduction_ids.all())
        self.assertTrue(mine and hers)
        self.assertFalse(any(d.is_pretax for d in mine))
        self.assertTrue(all(d.is_pretax for d in hers))

    def test_the_payout_of_an_overridden_employee_follows_the_override(self):
        self._override("loan_payout", self.adam, False)
        self.assertFalse(self._loan(self.adam).allowance_id.is_taxable)
        self.assertTrue(self._loan(self.bea).allowance_id.is_taxable)


class FormTests(Fixture):
    def _template(self, model, key):
        return model.objects.entire().get(system_key=key)

    @staticmethod
    def _post(**fields):
        """A form post: every value a list, as a browser sends them."""
        return MultiValueDict(
            {name: value if isinstance(value, list) else [value] for name, value in fields.items()}
        )

    def _save(self, key, model, form_class, **fields):
        form = form_class(data=self._post(**fields), instance=self._template(model, key))
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

    def _stored(self, key):
        return {
            o.employee_id_id: o.value for o in SystemComponentTaxOverride.objects.filter(system_key=key)
        }

    def test_a_standard_component_form_has_one_employee_exceptions_field(self):
        for model, form_class, key in (
            (Allowance, AllowanceForm, "loan_payout"),
            (Deduction, DeductionForm, "fine"),
        ):
            form = form_class(instance=self._template(model, key))
            self.assertIn("tax_exception_employees", form.fields, key)
            self.assertEqual(str(form.fields["tax_exception_employees"].label), "Tax Treatment By Employee")
            self.assertNotIn(tax_field(key), form.fields)

    def test_an_ordinary_component_has_no_such_field(self):
        ordinary = Allowance.objects.create(title="Ordinary", is_fixed=True, amount=1)
        self.assertNotIn("tax_exception_employees", AllowanceForm(instance=ordinary).fields)

    def test_a_ticked_employee_gets_the_opposite_of_a_deduction_default(self):
        self._save(
            "loan_repayment", Deduction, DeductionForm,
            tax_exception_employees=[self.adam.pk],
        )
        self.assertEqual(self._stored("loan_repayment"), {self.adam.pk: False})

    def test_a_ticked_employee_gets_the_opposite_of_an_earning_default(self):
        self._save(
            "loan_payout", Allowance, AllowanceForm,
            tax_exception_employees=[self.adam.pk],
        )
        self.assertEqual(self._stored("loan_payout"), {self.adam.pk: False})

    def test_an_exception_is_the_opposite_of_the_standard_setting_as_it_stands(self):
        template = self._template(Deduction, "loan_repayment")
        template.is_pretax = False
        template.save()
        self._save("loan_repayment", Deduction, DeductionForm, tax_exception_employees=[self.adam.pk])
        self.assertEqual(self._stored("loan_repayment"), {self.adam.pk: True})

    def test_saving_leaves_the_standard_setting_alone(self):
        self._save("loan_repayment", Deduction, DeductionForm, tax_exception_employees=[self.adam.pk])
        self.assertTrue(self._template(Deduction, "loan_repayment").is_pretax)

    def test_saving_replaces_what_was_stored_and_shows_it_again(self):
        self._override("fine", self.adam, False)
        self._save("fine", Deduction, DeductionForm, tax_exception_employees=[self.bea.pk])
        self.assertEqual(self._stored("fine"), {self.bea.pk: False})
        again = DeductionForm(instance=self._template(Deduction, "fine"))
        self.assertEqual(again.fields["tax_exception_employees"].initial, [self.bea.pk])

    def test_no_one_ticked_clears_the_exceptions(self):
        self._override("fine", self.adam, False)
        self._save("fine", Deduction, DeductionForm, is_pretax="on")
        self.assertEqual(self._stored("fine"), {})

    def test_saving_reaches_the_employees_unpaid_lines_but_not_paid_ones(self):
        loan = self._loan(self.adam)
        paid, unpaid = list(loan.deduction_ids.all())[:2]
        payslip = Payslip.objects.create(
            employee_id=self.adam,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            pay_head_data={},
        )
        payslip.installment_ids.add(paid)

        self._save(
            "loan_repayment", Deduction, DeductionForm,
            tax_exception_employees=[self.adam.pk],
        )

        paid.refresh_from_db()
        unpaid.refresh_from_db()
        self.assertTrue(paid.is_pretax)
        self.assertFalse(unpaid.is_pretax)


class PickerTests(Fixture):
    def setUp(self):
        super().setUp()
        from django.urls import reverse

        from horilla.testkit import make_user

        self.reverse = reverse
        user = make_user("pickadmin", is_superuser=True)
        make_employee(company=self.adam.employee_work_info.company_id, email="pickadmin@test.horilla", user=user)
        self.client.force_login(user)

    def test_the_rows_endpoint_lists_active_employees_with_a_next_page_marker(self):
        response = self.client.get(self.reverse("employee-pick-rows"))
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-pick-row', body)
        self.assertIn(self.adam.get_full_name(), body)
        self.assertIn("X-Next-Page", response)

    def test_a_search_narrows_the_rows(self):
        self.bea.employee_last_name = "Zzyzx"
        self.bea.save()
        body = self.client.get(self.reverse("employee-pick-rows"), {"q": "Zzyzx"}).content.decode()
        self.assertIn(f'data-pk="{self.bea.pk}"', body)
        self.assertNotIn(f'data-pk="{self.adam.pk}"', body)

    def test_the_group_filters_narrow_the_rows_and_the_ids(self):
        work = self.bea.employee_work_info
        department = work.department_id or Department.objects.create(department="Pick Dept")
        work.department_id = department
        work.save()
        self.adam.employee_work_info.department_id = None
        self.adam.employee_work_info.save()
        rows = self.client.get(self.reverse("employee-pick-rows"), {"department": department.pk})
        body = rows.content.decode()
        self.assertIn(f'data-pk="{self.bea.pk}"', body)
        self.assertNotIn(f'data-pk="{self.adam.pk}"', body)
        self.assertEqual(rows["X-Column"], "department")
        ids = self.client.get(
            self.reverse("employee-pick-rows"), {"ids": "1", "department": department.pk}
        ).json()["ids"]
        self.assertIn(str(self.bea.pk), ids)
        self.assertNotIn(str(self.adam.pk), ids)

    def test_a_position_filter_swaps_the_group_column(self):
        department, _ = Department.objects.get_or_create(department="Pick Dept")
        position = JobPosition.objects.create(job_position="Pick Position", department_id=department)
        work = self.bea.employee_work_info
        work.job_position_id = position
        work.save()
        rows = self.client.get(self.reverse("employee-pick-rows"), {"job_position": position.pk})
        self.assertEqual(rows["X-Column"], "job_position")
        self.assertIn("Pick Position", rows.content.decode())

    def test_the_edit_page_says_whether_it_is_an_earning_or_a_deduction(self):
        loan = Allowance.objects.entire().get(system_key="loan_payout")
        fine = Deduction.objects.entire().get(system_key="fine")
        earning = self.client.get(self.reverse("update-allowance", args=[loan.pk]), HTTP_HX_REQUEST="true").content.decode()
        deduction = self.client.get(self.reverse("update-deduction", args=[fine.pk]), HTTP_HX_REQUEST="true").content.decode()
        self.assertIn("oh-pick__chip--earning", earning)
        self.assertIn(">Earning<", earning)
        self.assertIn("Standard: Taxable", earning)
        self.assertIn("oh-pick__chip--deduction", deduction)
        self.assertIn(">Pre-Tax Deduction<", deduction)
        self.assertIn("Standard: Pre-Tax", deduction)

    def test_a_one_step_form_hides_the_step_rail_and_the_lone_heading(self):
        loan = Allowance.objects.entire().get(system_key="loan_payout")
        html = self.client.get(
            self.reverse("update-allowance", args=[loan.pk]), HTTP_HX_REQUEST="true"
        ).content.decode()
        for name in ("oh-steps--solo", "oh-component-form__section--solo", "oh-step-panel--solo"):
            self.assertRegex(html, r'class="[^"]*' + name, name)

    def test_an_ordinary_component_keeps_its_steps(self):
        plain = Allowance.objects.create(title="Plain Steps", is_fixed=True, amount=1)
        html = self.client.get(
            self.reverse("update-allowance", args=[plain.pk]), HTTP_HX_REQUEST="true"
        ).content.decode()
        for name in ("oh-steps--solo", "oh-component-form__section--solo", "oh-step-panel--solo"):
            self.assertNotRegex(html, r'class="[^"]*' + name, name)

    def test_the_widget_offers_the_three_filters(self):
        Department.objects.get_or_create(department="Pick Dept")
        html = EmployeePickWidget().render("tax_exception_employees", [])
        for param in ("department", "job_position", "job_role"):
            self.assertIn(f'data-pick-filter="{param}"', html)
        self.assertIn("Pick Dept", html)

    def test_the_ids_mode_answers_with_every_match(self):
        response = self.client.get(self.reverse("employee-pick-rows"), {"ids": "1"})
        ids = response.json()["ids"]
        self.assertIn(str(self.adam.pk), ids)
        self.assertIn(str(self.bea.pk), ids)

    def test_the_edit_page_shows_the_picker_with_what_is_stored_ticked(self):
        self._override("loan_payout", self.bea, False)
        loan = Allowance.objects.entire().get(system_key="loan_payout")
        html = self.client.get(
            self.reverse("update-allowance", args=[loan.pk]), HTTP_HX_REQUEST="true"
        ).content.decode()
        self.assertIn("Tax Treatment By Employee", html)
        self.assertIn('data-pick="', html)
        self.assertIn(self.reverse("employee-pick-rows"), html)
        self.assertIn(f"[{self.bea.pk}]", html)


class PenaltyTests(Fixture):
    def test_a_penalty_policy_for_an_overridden_employee_follows_the_override(self):
        self._override("penalty", self.adam, False)
        self.assertFalse(policy_fields("penalty", employee=self.adam)["is_pretax"])
        self.assertTrue(policy_fields("penalty", employee=self.bea)["is_pretax"])
