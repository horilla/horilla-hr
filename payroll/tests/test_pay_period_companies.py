"""One pay period per company, listed in the Payroll Settings "Payslip Auto Generation" tab."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from base.models import Company
from horilla.testkit import make_company, make_employee, make_user
from payroll.forms.batch_forms import PayPeriodSettingsForm
from payroll.models.models import PayPeriodSettings


class Fixture(TestCase):
    def setUp(self):
        self.company_a = make_company("Alpha Co")
        self.company_b = make_company("Beta Co")
        self.user = make_user("pp-admin", is_superuser=True)
        make_employee(
            company=self.company_a, email="pp-admin@test.horilla", user=self.user
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["selected_company"] = "all"
        session.save()

    def post_modal(self, url, data):
        return self.client.post(url, data, HTTP_HX_REQUEST="true")


class OnePerCompanyTests(Fixture):
    def test_a_company_cannot_have_two(self):
        PayPeriodSettings.objects.create(company_id=self.company_a, cycle_start_day=15)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PayPeriodSettings.objects.create(
                company_id=self.company_a, cycle_start_day=20
            )

    def test_only_one_row_for_all_companies(self):
        PayPeriodSettings.objects.create(cycle_start_day=1)
        second = PayPeriodSettings(cycle_start_day=15)
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_editing_the_all_companies_row_is_not_blocked_by_itself(self):
        row = PayPeriodSettings.objects.create(cycle_start_day=1)
        row.cycle_start_day = 15
        row.full_clean()

    def test_a_company_without_its_own_uses_the_all_companies_one(self):
        PayPeriodSettings.objects.create(cycle_start_day=10)
        PayPeriodSettings.objects.create(company_id=self.company_a, cycle_start_day=20)
        self.assertEqual(PayPeriodSettings.for_company(self.company_a).start_day, 20)
        self.assertEqual(PayPeriodSettings.for_company(self.company_b).start_day, 10)

    def test_companies_with_a_pay_period_stay_listed_but_cannot_be_picked(self):
        PayPeriodSettings.objects.create(company_id=self.company_a, cycle_start_day=15)
        form = PayPeriodSettingsForm(with_company=True)
        self.assertEqual(form.taken_company_ids, {self.company_a.pk})
        self.assertTrue(form.has_free_company)
        html = str(form["company_id"])
        self.assertIn("Alpha Co (already has a pay period)", html)
        self.assertRegex(html, r'<option value="%d"[^>]*disabled' % self.company_a.pk)
        bad = PayPeriodSettingsForm(
            {
                "company_id": self.company_a.pk,
                "cycle_start_day": "1",
                "pay_day": "day:5",
            },
            with_company=True,
        )
        self.assertFalse(bad.is_valid())
        self.assertIn("company_id", bad.errors)

    def test_a_rows_own_company_is_not_taken_when_editing(self):
        row = PayPeriodSettings.objects.create(
            company_id=self.company_a, cycle_start_day=15
        )
        form = PayPeriodSettingsForm(instance=row, with_company=True)
        self.assertNotIn(self.company_a.pk, form.taken_company_ids)

    def test_a_company_must_be_chosen(self):
        form = PayPeriodSettingsForm(with_company=True)
        self.assertTrue(form.fields["company_id"].required)
        bad = PayPeriodSettingsForm(
            {"cycle_start_day": "15", "pay_day": "day:5"}, with_company=True
        )
        self.assertFalse(bad.is_valid())
        self.assertIn("company_id", bad.errors)


class SettingsListTests(Fixture):
    def setUp(self):
        super().setUp()
        PayPeriodSettings.objects.create(
            company_id=self.company_a, cycle_start_day=15, pay_day_of_month=5
        )
        PayPeriodSettings.objects.create(
            company_id=self.company_b,
            cycle_start_day=31,
            pay_day_of_month=0,
            pay_day_offset=3,
        )

    def test_the_auto_generation_tab_hosts_the_pay_period_list(self):
        html = self.client.get(
            reverse("payroll-settings-auto-payslip-tab"), HTTP_HX_REQUEST="true"
        ).content.decode()
        self.assertIn('id="payPeriodListContainer"', html)
        self.assertIn(reverse("pay-period-nav"), html)
        self.assertIn(reverse("pay-period-list"), html)
        # The payslip automation under it is hidden for now.
        self.assertNotIn('id="payslipAutoGenerationListContainer"', html)

    def test_the_list_shows_one_row_per_company_with_its_period_and_pay_day(self):
        html = self.client.get(
            reverse("pay-period-list"), HTTP_HX_REQUEST="true"
        ).content.decode()
        self.assertIn("Alpha Co", html)
        self.assertIn("Beta Co", html)
        self.assertIn("15th", html)
        self.assertIn("Last day", html)
        self.assertIn("3 days after the period ends", html)

    def test_the_nav_offers_create(self):
        html = self.client.get(
            reverse("pay-period-nav"), HTTP_HX_REQUEST="true"
        ).content.decode()
        self.assertIn("then=list&new=1", html)


class SettingsFormTests(Fixture):
    def test_creating_for_a_company_stores_its_own_row(self):
        url = reverse("pay-period-settings") + "?modal=1&then=list&new=1"
        response = self.post_modal(
            url,
            {
                "company_id": self.company_b.pk,
                "cycle_start_day": "15",
                "pay_day": "day:5",
            },
        )
        self.assertContains(response, "pay-period-list")
        row = PayPeriodSettings.objects.entire().get(company_id=self.company_b)
        self.assertEqual((row.cycle_start_day, row.pay_day_of_month), (15, 5))

    def test_a_second_row_for_the_same_company_is_refused(self):
        PayPeriodSettings.objects.create(company_id=self.company_b, cycle_start_day=1)
        url = reverse("pay-period-settings") + "?modal=1&then=list&new=1"
        response = self.post_modal(
            url,
            {
                "company_id": self.company_b.pk,
                "cycle_start_day": "15",
                "pay_day": "day:5",
            },
        )
        self.assertNotContains(response, "pay-period-list")
        self.assertEqual(
            PayPeriodSettings.objects.entire()
            .filter(company_id=self.company_b)
            .count(),
            1,
        )

    def test_editing_a_row_from_the_list(self):
        row = PayPeriodSettings.objects.create(
            company_id=self.company_a, cycle_start_day=1
        )
        url = reverse("pay-period-update", kwargs={"pk": row.pk}) + "?modal=1&then=list"
        page = self.client.get(url, HTTP_HX_REQUEST="true").content.decode()
        self.assertIn("Company", page)
        self.post_modal(
            url,
            {
                "company_id": self.company_a.pk,
                "cycle_start_day": "20",
                "pay_day": "day:1",
            },
        )
        row.refresh_from_db()
        self.assertEqual(row.cycle_start_day, 20)

    def test_the_wizards_dialog_makes_the_users_own_company_a_row_not_the_shared_one(
        self,
    ):
        shared = PayPeriodSettings.objects.create(cycle_start_day=10)
        url = reverse("pay-period-settings") + "?modal=1"
        self.post_modal(url, {"cycle_start_day": "25", "pay_day": "day:1"})
        shared.refresh_from_db()
        self.assertEqual(shared.cycle_start_day, 10)
        own = PayPeriodSettings.objects.entire().get(company_id=self.company_a)
        self.assertEqual(own.cycle_start_day, 25)

    def test_opening_the_wizards_dialog_starts_from_the_setting_in_force(self):
        PayPeriodSettings.objects.create(cycle_start_day=10, pay_day_of_month=7)
        html = self.client.get(
            reverse("pay-period-settings") + "?modal=1", HTTP_HX_REQUEST="true"
        ).content.decode()
        # whitespace inside the tag is template formatting, not behaviour: match the attributes, not the spacing
        self.assertRegex(html, r'<option value="10"\s+selected\s*>')
        self.assertRegex(html, r'<option value="day:7"\s+selected\s*>')
        self.assertFalse(
            PayPeriodSettings.objects.entire()
            .filter(company_id=self.company_a)
            .exists()
        )

    def test_the_wizards_dialog_has_no_company_choice(self):
        html = self.client.get(
            reverse("pay-period-settings") + "?modal=1", HTTP_HX_REQUEST="true"
        ).content.decode()
        self.assertNotIn('name="company_id"', html)


class DeleteTests(Fixture):
    def test_deleting_a_row_removes_it_and_the_company_falls_back(self):
        PayPeriodSettings.objects.create(cycle_start_day=10)
        row = PayPeriodSettings.objects.create(
            company_id=self.company_a, cycle_start_day=20
        )
        self.client.post(
            reverse("pay-period-delete", kwargs={"pk": row.pk}), HTTP_HX_REQUEST="true"
        )
        self.assertFalse(PayPeriodSettings.objects.entire().filter(pk=row.pk).exists())
        self.assertEqual(PayPeriodSettings.for_company(self.company_a).start_day, 10)

    def test_a_get_does_not_delete(self):
        row = PayPeriodSettings.objects.create(
            company_id=self.company_a, cycle_start_day=20
        )
        self.client.get(
            reverse("pay-period-delete", kwargs={"pk": row.pk}), HTTP_HX_REQUEST="true"
        )
        self.assertTrue(PayPeriodSettings.objects.entire().filter(pk=row.pk).exists())


class AutoGenerateTests(Fixture):
    def test_the_form_saves_the_auto_generate_choice(self):
        url = reverse("pay-period-settings") + "?modal=1&then=list&new=1"
        self.post_modal(
            url,
            {
                "company_id": self.company_b.pk,
                "cycle_start_day": "1",
                "pay_day": "day:5",
                "auto_generate": "on",
            },
        )
        self.assertTrue(
            PayPeriodSettings.objects.entire()
            .get(company_id=self.company_b)
            .auto_generate
        )

    def test_the_job_generates_for_a_company_the_day_after_its_period_ends(self):
        from datetime import date
        from unittest.mock import patch

        from payroll import scheduler

        PayPeriodSettings.objects.create(
            company_id=self.company_a, cycle_start_day=1, auto_generate=True
        )
        PayPeriodSettings.objects.create(
            company_id=self.company_b, cycle_start_day=1, auto_generate=False
        )
        with patch.object(scheduler, "generate_payslips") as run:
            scheduler.generate_pay_period_payslips(date(2026, 11, 1))
            self.assertEqual(run.call_count, 1)
            self.assertEqual(
                run.call_args.args[1:], (date(2026, 10, 1), date(2026, 10, 31))
            )
            run.reset_mock()
            scheduler.generate_pay_period_payslips(date(2026, 11, 2))
            run.assert_not_called()

    def test_the_job_is_registered_and_one_company_failing_does_not_stop_the_rest(self):
        from datetime import date
        from unittest.mock import patch

        from horilla.scheduling import get_registered_jobs
        from payroll import scheduler

        self.assertIn(
            "payroll.scheduler.generate_pay_period_payslips",
            [j.job_id for j in get_registered_jobs()],
        )
        self.assertNotIn(
            "payroll.scheduler.auto_payslip_generate",
            [j.job_id for j in get_registered_jobs()],
        )
        PayPeriodSettings.objects.create(
            company_id=self.company_a, cycle_start_day=1, auto_generate=True
        )
        PayPeriodSettings.objects.create(
            company_id=self.company_b, cycle_start_day=1, auto_generate=True
        )
        with patch.object(
            scheduler, "generate_payslips", side_effect=[RuntimeError("boom"), None]
        ) as run:
            scheduler.generate_pay_period_payslips(date(2026, 11, 1))
        self.assertEqual(run.call_count, 2)


class NoDuplicateRunTests(Fixture):
    def setUp(self):
        super().setUp()
        self.row = PayPeriodSettings.objects.create(
            company_id=self.company_a, cycle_start_day=1, auto_generate=True
        )

    def test_a_period_is_generated_once_however_often_the_job_runs(self):
        from datetime import date
        from unittest.mock import patch

        from payroll import scheduler

        with patch.object(scheduler, "generate_payslips", return_value=2) as run:
            for _ in range(3):
                scheduler.generate_pay_period_payslips(date(2026, 11, 1))
        self.assertEqual(run.call_count, 1)
        self.row.refresh_from_db()
        self.assertEqual(self.row.last_generated_end, date(2026, 10, 31))

    def test_a_failed_run_releases_the_claim_so_the_next_one_retries(self):
        from datetime import date
        from unittest.mock import patch

        from payroll import scheduler

        with patch.object(
            scheduler, "generate_payslips", side_effect=[RuntimeError("x"), 1]
        ) as run:
            scheduler.generate_pay_period_payslips(date(2026, 11, 1))
            self.row.refresh_from_db()
            self.assertIsNone(self.row.last_generated_end)
            scheduler.generate_pay_period_payslips(date(2026, 11, 1))
        self.assertEqual(run.call_count, 2)

    def test_the_manual_run_generates_the_last_completed_period(self):
        from datetime import date
        from unittest.mock import patch

        from payroll import scheduler

        with patch.object(scheduler, "generate_payslips", return_value=3) as run:
            response = self.client.post(
                reverse("pay-period-generate", kwargs={"pk": self.row.pk}),
                HTTP_HX_REQUEST="true",
            )
        self.assertEqual(response.status_code, 200)
        start, end = self.row.last_completed_period(date.today())
        self.assertEqual(run.call_args.args[1:], (start, end))

    def test_a_get_does_not_run_it(self):
        from unittest.mock import patch

        from payroll import scheduler

        with patch.object(scheduler, "generate_payslips") as run:
            self.client.get(
                reverse("pay-period-generate", kwargs={"pk": self.row.pk}),
                HTTP_HX_REQUEST="true",
            )
        run.assert_not_called()

    def test_the_list_shows_which_period_each_run_will_cover(self):
        html = self.client.get(
            reverse("pay-period-list"), HTTP_HX_REQUEST="true"
        ).content.decode()
        self.assertIn("pp-tip__body", html)
        self.assertIn("Generates payslips for", html)
        self.assertIn("Generate payslips now for", html)
        self.assertIn(reverse("pay-period-generate", kwargs={"pk": self.row.pk}), html)
