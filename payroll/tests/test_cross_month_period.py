"""A pay period may start on any day and run into the next month."""

from datetime import date

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from horilla.testkit.factories import make_payslip
from payroll.methods import batch_run
from payroll.methods.methods import compute_salary_on_period, months_between_range
from payroll.models.models import Contract
from payroll.tests.factories_payroll import make_active_contract

START = date(2026, 9, 15)
END = date(2026, 10, 14)


class CrossMonthTests(TestCase):
    def setUp(self):
        company = make_company("Cross Co")
        self.employee = make_employee(company=company, email="cross@test.horilla")
        Contract.objects.filter(employee_id=self.employee).delete()
        make_active_contract(self.employee, wage=30000.0)

    def test_the_period_is_split_by_month_and_each_part_prorated_on_its_own_month(self):
        parts = months_between_range(30000.0, START, END)
        self.assertEqual(
            [(p["month"], p["start_date"], p["end_date"]) for p in parts],
            [
                (9, "2026-09-15", "2026-09-30"),
                (10, "2026-10-01", "2026-10-14"),
            ],
        )
        # Each month is priced against its own working days, not a shared divisor.
        for part in parts:
            self.assertAlmostEqual(
                part["per_day_amount"] * part["working_days_on_month"],
                30000.0,
                places=2,
            )

    def test_basic_pay_across_two_months_is_the_sum_of_the_two_shares(self):
        parts = months_between_range(30000.0, START, END)
        expected = sum(p["working_days_on_period"] * p["per_day_amount"] for p in parts)
        data = compute_salary_on_period(self.employee, START, END)
        self.assertAlmostEqual(data["basic_pay"], expected, places=2)
        # About one month's pay: neither a whole month twice nor a fraction of one.
        self.assertGreater(data["basic_pay"], 30000.0 * 0.9)
        self.assertLess(data["basic_pay"], 30000.0 * 1.1)

    def test_a_payslip_for_an_overlapping_period_blocks_another(self):
        make_payslip(
            employee=self.employee,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 30),
        )
        ok, excluded = batch_run.eligible_employees([self.employee], START, END)
        self.assertEqual(ok, [])
        self.assertEqual([e.pk for e, _reason in excluded], [self.employee.pk])

    def test_a_payslip_for_the_next_period_does_not_block(self):
        make_payslip(
            employee=self.employee,
            start_date=date(2026, 10, 15),
            end_date=date(2026, 11, 14),
        )
        ok, excluded = batch_run.eligible_employees([self.employee], START, END)
        self.assertEqual(ok, [self.employee])


class PayPeriodCycleTests(TestCase):
    """The pay period setting is one choice: the day a period begins, 1 to 28 or the last day."""

    def _settings(self, day=1):
        from payroll.models.models import PayPeriodSettings

        return PayPeriodSettings(cycle_start_day=day)

    def test_the_first_is_the_calendar_month(self):
        s = self._settings(1)
        self.assertEqual(
            s.period_for(date(2026, 9, 20)), (date(2026, 9, 1), date(2026, 9, 30))
        )
        self.assertEqual(s.summary(), "Calendar month (1st to last day)")

    def test_a_period_contains_the_date_it_is_asked_about(self):
        s = self._settings(15)
        self.assertEqual(
            s.period_for(date(2026, 9, 20)), (date(2026, 9, 15), date(2026, 10, 14))
        )
        self.assertEqual(
            s.period_for(date(2026, 10, 3)), (date(2026, 9, 15), date(2026, 10, 14))
        )
        self.assertEqual(
            s.period_for(date(2026, 9, 15)), (date(2026, 9, 15), date(2026, 10, 14))
        )
        self.assertEqual(
            s.period_for(date(2026, 10, 14)), (date(2026, 9, 15), date(2026, 10, 14))
        )
        self.assertEqual(
            s.period_for(date(2026, 10, 15)), (date(2026, 10, 15), date(2026, 11, 14))
        )

    def test_it_crosses_the_year(self):
        s = self._settings(20)
        self.assertEqual(
            s.period_for(date(2027, 1, 5)), (date(2026, 12, 20), date(2027, 1, 19))
        )

    def test_the_last_day_of_the_month_starts_on_whichever_day_ends_each_month(self):
        s = self._settings(31)
        self.assertEqual(
            s.period_for(date(2026, 11, 10)), (date(2026, 10, 31), date(2026, 11, 29))
        )
        self.assertEqual(
            s.period_for(date(2026, 11, 30)), (date(2026, 11, 30), date(2026, 12, 30))
        )
        self.assertEqual(
            s.period_for(date(2026, 12, 31)), (date(2026, 12, 31), date(2027, 1, 30))
        )
        self.assertEqual(
            s.period_for(date(2027, 2, 10)), (date(2027, 1, 31), date(2027, 2, 27))
        )
        self.assertEqual(
            s.period_for(date(2028, 2, 29)), (date(2028, 2, 29), date(2028, 3, 30))
        )
        self.assertEqual(s.summary(), "Cycle starting on the last day of each month")

    def test_consecutive_periods_leave_no_gap_and_no_overlap_for_every_choice(self):
        from datetime import timedelta

        for day in range(1, 32):
            with self.subTest(day=day):
                s = self._settings(day)
                start, end = s.period_for(date(2026, 1, 30))
                for _n in range(26):
                    next_start, next_end = s.period_for(end + timedelta(days=1))
                    self.assertEqual(next_start, end + timedelta(days=1))
                    self.assertGreaterEqual(next_end, next_start)
                    start, end = next_start, next_end

    def test_a_start_on_the_settings_boundary_ends_where_the_next_begins(self):
        s = self._settings(31)
        self.assertEqual(s.end_for(date(2026, 10, 31)), date(2026, 11, 29))
        self.assertEqual(s.end_for(date(2026, 11, 30)), date(2026, 12, 30))
        # Any other start runs for its own month days.
        self.assertEqual(s.end_for(date(2026, 9, 15)), date(2026, 10, 14))
        self.assertEqual(
            self._settings(15).end_for(date(2026, 9, 15)), date(2026, 10, 14)
        )

    def test_the_last_completed_period_is_the_one_before_the_current(self):
        self.assertEqual(
            self._settings(15).last_completed_period(date(2026, 10, 20)),
            (date(2026, 9, 15), date(2026, 10, 14)),
        )
        self.assertEqual(
            self._settings(1).last_completed_period(date(2026, 10, 20)),
            (date(2026, 9, 1), date(2026, 9, 30)),
        )

    def test_the_summary_says_what_the_rule_is(self):
        self.assertEqual(
            self._settings(15).summary(), "Cycle starting on the 15th of each month"
        )
        self.assertIn("22nd", self._settings(22).summary())
        self.assertIn("3rd", self._settings(3).summary())
        self.assertIn("11th", self._settings(11).summary())

    def test_the_choices_are_the_first_to_the_28th_and_the_last_day(self):
        from payroll.models.models import PayPeriodSettings

        values = [value for value, _label in PayPeriodSettings.START_DAY_CHOICES]
        self.assertEqual(values, list(range(1, 32)))
        labels = dict(PayPeriodSettings.START_DAY_CHOICES)
        self.assertEqual(labels[1], "1st (calendar month)")
        self.assertEqual(labels[2], "2nd")
        self.assertEqual(labels[11], "11th")
        self.assertEqual(labels[29], "29th")
        self.assertEqual(labels[30], "30th")
        self.assertEqual(labels[31], "Last day")

    def test_the_form_has_the_one_choice_and_refuses_anything_else(self):
        from payroll.forms.batch_forms import PayPeriodSettingsForm

        form = PayPeriodSettingsForm()
        self.assertEqual(
            list(form.fields), ["cycle_start_day", "auto_generate", "pay_day"]
        )
        base = {"pay_day": "after:0"}
        for good in (1, 15, 28, 29, 30, 31):
            self.assertTrue(
                PayPeriodSettingsForm({**base, "cycle_start_day": good}).is_valid(),
                good,
            )
        for bad in (0, 32):
            self.assertFalse(
                PayPeriodSettingsForm({**base, "cycle_start_day": bad}).is_valid(), bad
            )

    def test_saving_keeps_the_legacy_boundary_in_step(self):
        from payroll.models.models import PayPeriodSettings

        first = PayPeriodSettings.objects.create(cycle_start_day=1)
        self.assertEqual(first.boundary, "calendar_month")
        first.cycle_start_day = 15
        first.save()
        self.assertEqual(first.boundary, "cycle_day")

    def test_the_29th_and_30th_start_a_period_on_the_last_day_when_the_month_is_shorter(
        self,
    ):
        s = self._settings(30)
        self.assertEqual(
            s.period_for(date(2027, 2, 20)), (date(2027, 1, 30), date(2027, 2, 27))
        )  # Feb: 28th
        self.assertEqual(
            s.period_for(date(2027, 3, 31)), (date(2027, 3, 30), date(2027, 4, 29))
        )
        s29 = self._settings(29)
        self.assertEqual(
            s29.period_for(date(2027, 2, 28)), (date(2027, 2, 28), date(2027, 3, 28))
        )
        self.assertEqual(
            s29.period_for(date(2028, 2, 29)), (date(2028, 2, 29), date(2028, 3, 28))
        )

    def test_pay_day_is_one_list_of_days_of_the_month_like_period_runs(self):
        from payroll.forms.batch_forms import PayPeriodSettingsForm
        from payroll.models.models import PayPeriodSettings

        # A company that has saved a day of the month sees only the list of days.
        form = PayPeriodSettingsForm(instance=PayPeriodSettings(pay_day_of_month=15))
        choices = form.fields["pay_day"].choices
        self.assertEqual(
            [v for v, _l in choices], [f"day:{n}" for n in range(1, 31)] + ["day:31"]
        )
        labels = dict(choices)
        self.assertEqual(labels["day:5"], "5th")
        self.assertEqual(labels["day:22"], "22nd")
        self.assertEqual(labels["day:29"], "29th")
        self.assertEqual(labels["day:30"], "30th")
        self.assertEqual(labels["day:31"], "Last day")
        self.assertEqual(form.fields["pay_day"].initial, "day:15")
        self.assertFalse(
            any(isinstance(options, (list, tuple)) for _v, options in choices)
        )

    def test_a_pay_day_saved_as_days_after_stays_as_its_own_first_option(self):
        from payroll.forms.batch_forms import PayPeriodSettingsForm
        from payroll.models.models import PayPeriodSettings

        form = PayPeriodSettingsForm(instance=PayPeriodSettings(pay_day_offset=5))
        choices = form.fields["pay_day"].choices
        self.assertEqual(choices[0], ("after:5", "5 days after the period ends"))
        self.assertEqual(len(choices), 32)
        self.assertEqual(form.fields["pay_day"].initial, "after:5")
        # Only the value it already has: no other days-after choice is offered.
        self.assertFalse(
            PayPeriodSettingsForm(
                {"cycle_start_day": 1, "pay_day": "after:7"},
                instance=PayPeriodSettings(pay_day_offset=5),
            ).is_valid()
        )
        self.assertTrue(
            PayPeriodSettingsForm(
                {"cycle_start_day": 1, "pay_day": "after:5"},
                instance=PayPeriodSettings(pay_day_offset=5),
            ).is_valid()
        )

    def test_choosing_a_pay_day_stores_it_in_the_right_column(self):
        from payroll.forms.batch_forms import PayPeriodSettingsForm
        from payroll.models.models import PayPeriodSettings

        for value, day in (("after:5", 0), ("day:15", 15), ("day:31", 31)):
            instance = PayPeriodSettings(pay_day_offset=5)
            form = PayPeriodSettingsForm(
                {"cycle_start_day": 1, "pay_day": value}, instance=instance
            )
            self.assertTrue(form.is_valid(), (value, form.errors))
            form.save(commit=False)
            self.assertEqual(instance.pay_day_of_month, day, value)
            self.assertEqual(instance.pay_day_offset, 5)
        self.assertFalse(
            PayPeriodSettingsForm(
                {"cycle_start_day": 1, "pay_day": "day:32"}
            ).is_valid()
        )
        self.assertFalse(
            PayPeriodSettingsForm(
                {"cycle_start_day": 1, "pay_day": "garbage"}
            ).is_valid()
        )

    def test_the_pay_date_for_days_after(self):
        s = self._settings(1)
        s.pay_day_offset = 30
        self.assertEqual(s.pay_date_for(date(2027, 2, 28)), date(2027, 3, 30))
        s.pay_day_offset = 0
        self.assertEqual(s.pay_date_for(date(2027, 2, 28)), date(2027, 2, 28))

    def test_the_pay_date_for_a_day_of_the_month_is_the_first_such_day_after_the_period(
        self,
    ):
        s = self._settings(1)
        for day, period_end, expected in (
            (5, date(2026, 10, 31), date(2026, 11, 5)),
            (
                20,
                date(2026, 11, 14),
                date(2026, 11, 20),
            ),  # after a cycle ending mid-month: this month
            (
                10,
                date(2026, 11, 14),
                date(2026, 12, 10),
            ),  # day already passed: next month
            (
                30,
                date(2027, 2, 28),
                date(2027, 3, 30),
            ),  # February has no 30th, and the 28th is not after the period
            (
                30,
                date(2027, 1, 31),
                date(2027, 2, 28),
            ),  # 30th falls back to February's last day
            (29, date(2027, 1, 31), date(2027, 2, 28)),
            (29, date(2028, 1, 31), date(2028, 2, 29)),  # leap year
            (31, date(2026, 10, 31), date(2026, 11, 30)),  # last day of the next month
            (31, date(2026, 11, 30), date(2026, 12, 31)),
            (5, date(2026, 12, 31), date(2027, 1, 5)),  # across the year
        ):
            with self.subTest(day=day, period_end=period_end):
                s.pay_day_of_month = day
                self.assertEqual(s.pay_date_for(period_end), expected)
                self.assertGreater(s.pay_date_for(period_end), period_end)

    def test_choosing_a_day_replaces_a_days_after_pay_day(self):
        from payroll.forms.batch_forms import PayPeriodSettingsForm
        from payroll.models.models import PayPeriodSettings

        instance = PayPeriodSettings(pay_day_offset=45)
        form = PayPeriodSettingsForm(
            {"cycle_start_day": 1, "pay_day": "day:10"}, instance=instance
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save(commit=False)
        self.assertEqual(instance.pay_day_of_month, 10)
        # And once a day is chosen, the days-after option is no longer offered.
        again = PayPeriodSettingsForm(instance=instance)
        self.assertEqual(len(again.fields["pay_day"].choices), 31)
