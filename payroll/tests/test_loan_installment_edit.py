"""Editing an installment reports through the page's own toast and re-spreads the balance."""

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

    def test_the_edited_amount_is_saved_and_the_balance_is_spread_over_the_rest(self):
        """The money the borrower still owes must keep adding up to the loan."""
        self._edit("1000")
        amounts = list(
            self.loan.deduction_ids.order_by("one_time_date").values_list(
                "amount", flat=True
            )
        )
        self.assertEqual(amounts[0], 1000)
        self.assertEqual(amounts[1:], [3666.67] * 3)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.installments, 4)
