from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import TestCase


class StatusCellTests(TestCase):
    """The status cell of the payslip list."""

    def _render(self, **fields):
        values = dict(
            id=1,
            status_locked=False,
            status_lock_message="",
            get_status_display="Paid",
            status="paid",
            status_choices=[],
        )
        values.update(fields)
        instance = SimpleNamespace(**values)
        return render_to_string(
            "cbv/payslip/payslip_status_col.html", {"instance": instance}
        )

    def test_a_locked_status_is_plain_text_not_a_second_table_cell(self):
        html = self._render(status_locked=True, status_lock_message="Batch paid")
        self.assertIn("Paid", html)
        self.assertNotIn("oh-sticky-table__td", html)
        self.assertIn('title="Batch paid"', html)


class PayrollListHeightTests(TestCase):
    """The payroll lists keep a fixed height and scroll inside, like the Employees list."""

    def _page(self, name, **kwargs):
        from django.urls import reverse

        from horilla.testkit import make_company, make_employee, make_user

        user = make_user("heightadmin", is_superuser=True)
        make_employee(
            company=make_company("Height Co"), email="height@test.horilla", user=user
        )
        self.client.force_login(user)
        return self.client.get(reverse(name, kwargs=kwargs)).content.decode()

    def test_the_payslips_page_restores_the_cap_the_tab_rule_removes(self):
        html = self._page("view-payslip")
        self.assertIn("#payslip-div .heightContainer", html)
        self.assertIn("#payroll-batch-div .heightContainer", html)
        self.assertIn("max-height: calc(100vh - 260px) !important", html)

    def test_a_batch_page_carries_the_same_cap_for_its_payslips(self):
        from payroll.models.payroll_batch import PayrollBatch

        batch = PayrollBatch.objects.create(
            batch_name="Height Batch",
            period_start="2026-10-01",
            period_end="2026-10-31",
        )
        html = self._page("payroll-batch-detail", batch_id=batch.pk)
        self.assertIn("#payslip-div .heightContainer", html)
