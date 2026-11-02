"""The Review crumb, once a batch has been generated, leads back to that batch's inputs."""

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.payroll_batch import PayrollBatch
from payroll.views.batch_views import SESSION_LAST_BATCH


class ReviewCrumbTests(TestCase):
    def setUp(self):
        user = make_user("inputsadmin", is_superuser=True)
        make_employee(
            company=make_company("Inputs Co"), email="inputs@test.horilla", user=user
        )
        self.client.force_login(user)
        self.batch = PayrollBatch.objects.create(
            batch_name="October 2026",
            period_start="2026-10-01",
            period_end="2026-10-31",
        )

    def _remember(self, batch):
        session = self.client.session
        session[SESSION_LAST_BATCH] = batch.pk
        session.save()

    def test_review_after_a_run_leads_to_that_batch_inputs_not_an_empty_new_batch(self):
        self._remember(self.batch)
        response = self.client.get(reverse("payroll-batch-review"))
        self.assertRedirects(
            response,
            reverse("payroll-batch-inputs", kwargs={"batch_id": self.batch.pk}),
            fetch_redirect_response=False,
        )

    def test_review_with_no_run_behind_it_still_starts_a_new_batch(self):
        response = self.client.get(reverse("payroll-batch-review"))
        self.assertRedirects(
            response, reverse("payroll-batch-scope"), fetch_redirect_response=False
        )

    def test_a_batch_that_moved_on_is_not_offered_for_its_inputs(self):
        self.batch.status = PayrollBatch.APPROVED
        self.batch.save()
        self._remember(self.batch)
        response = self.client.get(reverse("payroll-batch-review"))
        self.assertRedirects(
            response, reverse("payroll-batch-scope"), fetch_redirect_response=False
        )


class InputsPageTests(TestCase):
    def setUp(self):
        user = make_user("inputsadmin2", is_superuser=True)
        make_employee(
            company=make_company("Inputs Co 2"), email="inputs2@test.horilla", user=user
        )
        self.client.force_login(user)
        self.batch = PayrollBatch.objects.create(
            batch_name="October 2026",
            period_start="2026-10-01",
            period_end="2026-10-31",
        )

    def test_it_asks_before_discarding_and_posts_to_the_reopen_view(self):
        html = self.client.get(
            reverse("payroll-batch-inputs", kwargs={"batch_id": self.batch.pk})
        ).content.decode()
        self.assertIn("Go Back To Review", html)
        self.assertIn("Regularize", html)
        self.assertIn("Discards Its Draft Payslips", html)
        self.assertIn(
            reverse("payroll-batch-reopen", kwargs={"batch_id": self.batch.pk}), html
        )

    def test_a_batch_that_moved_on_goes_to_its_detail_page(self):
        self.batch.status = PayrollBatch.APPROVED
        self.batch.save()
        response = self.client.get(
            reverse("payroll-batch-inputs", kwargs={"batch_id": self.batch.pk})
        )
        self.assertRedirects(
            response,
            reverse("payroll-batch-detail", kwargs={"batch_id": self.batch.pk}),
            fetch_redirect_response=False,
        )
