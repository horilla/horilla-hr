"""Editing an installment swaps only the rows and reports through the page's own toast."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import LoanAccount


class EditInstallmentAmountTests(TestCase):
    def setUp(self):
        user = make_user("loanadmin", is_superuser=True)
        company = make_company("Loan Co")
        make_employee(company=company, email="loanadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.employee = make_employee(company=company, email="borrower@test.horilla")
        self.loan = LoanAccount.objects.create(
            employee_id=self.employee,
            title="Loan",
            loan_amount=12000,
            provided_date=date(2026, 4, 1),
            installments=4,
            installment_start_date=date(2026, 5, 1),
            type="loan",
        )

    def _edit(self, amount):
        first = self.loan.deduction_ids.order_by("one_time_date").first()
        url = f"{reverse('edit-installment-amount')}?loan_id={self.loan.pk}&ded_id={first.pk}"
        return self.client.post(url, {"amount": amount}, HTTP_HX_REQUEST="true")

    def test_the_response_asks_the_page_to_show_its_message(self):
        self.assertEqual(self._edit("1000").headers.get("HX-Trigger"), "showMessages")

    def test_the_message_is_not_written_into_the_table(self):
        html = self._edit("1000").content.decode()
        self.assertNotIn("updated successfully", html)
        self.assertNotIn("oh-alert", html)

    def test_only_the_rows_are_the_swap_target(self):
        html = self._edit("1000").content.decode()
        self.assertIn('id="installmentRows"', html)
        self.assertIn('hx-target="#installmentRows"', html)
