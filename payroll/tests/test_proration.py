"""
Scaling monthly figures to the pay period.

A ceiling of 1,500 means 1,500 a month. The form has offered "For working days
on month" since the field existed, but the arithmetic in ``compute_limit`` was
commented out, so the number was applied flat: a ten-day period was allowed a
whole month's ceiling.

The important property is that turning it on does not move a full month. The
period's working days and the month's working days are the same figure then, so
the factor is exactly 1 and a whole-month payroll caps where it always did.
Only partial and multi-month periods change, which is the point of the field.
"""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.methods.limits import compute_limit
from payroll.methods.proration import (
    FULL_PERIOD,
    MONTH_CALENDAR_DAYS,
    MONTH_WORKING_DAYS,
    PER_WORKING_DAY,
    period_factor,
)

FULL_MONTH = [
    {
        "days": 30,
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
        "working_days_on_period": 22,
        "working_days_on_month": 22,
    }
]
TEN_DAYS = [
    {
        "days": 30,
        "start_date": "2026-04-01",
        "end_date": "2026-04-10",
        "working_days_on_period": 8,
        "working_days_on_month": 22,
    }
]
SPANNING_TWO_MONTHS = [
    {
        "days": 30,
        "start_date": "2026-04-16",
        "end_date": "2026-04-30",
        "working_days_on_period": 11,
        "working_days_on_month": 22,
    },
    {
        "days": 31,
        "start_date": "2026-05-01",
        "end_date": "2026-05-15",
        "working_days_on_period": 11,
        "working_days_on_month": 21,
    },
]
# What the pay calculation itself reads, and all the golden fixtures build.
WITHOUT_MONTH_COUNTS = [{"working_days_on_period": 22, "per_day_amount": 1000}]


class Component:
    """Only the three attributes compute_limit looks at."""

    def __init__(
        self, maximum_amount=1500.0, maximum_unit=MONTH_WORKING_DAYS, has_max_limit=True
    ):
        self.maximum_amount = maximum_amount
        self.maximum_unit = maximum_unit
        self.has_max_limit = has_max_limit


class PeriodFactorTests(SimpleTestCase):
    def test_a_whole_month_does_not_scale(self):
        """
        The property that makes this safe to switch on: an existing ceiling on
        a normal monthly payroll caps exactly where it did before.
        """
        for basis in (MONTH_WORKING_DAYS, MONTH_CALENDAR_DAYS, FULL_PERIOD):
            with self.subTest(basis=basis):
                self.assertAlmostEqual(period_factor(FULL_MONTH, basis), 1.0)

    def test_a_part_month_scales_by_its_share(self):
        self.assertAlmostEqual(
            period_factor(TEN_DAYS, MONTH_WORKING_DAYS), 8 / 22, places=6
        )
        self.assertAlmostEqual(
            period_factor(TEN_DAYS, MONTH_CALENDAR_DAYS), 10 / 30, places=6
        )

    def test_a_flat_amount_never_scales(self):
        for day_dict in (FULL_MONTH, TEN_DAYS, SPANNING_TWO_MONTHS):
            with self.subTest(days=len(day_dict)):
                self.assertEqual(period_factor(day_dict, FULL_PERIOD), 1.0)

    def test_a_daily_amount_multiplies_by_the_working_days(self):
        self.assertEqual(period_factor(TEN_DAYS, PER_WORKING_DAY), 8.0)
        self.assertEqual(period_factor(FULL_MONTH, PER_WORKING_DAY), 22.0)

    def test_a_period_over_more_than_one_month_goes_above_one(self):
        """Two months of a monthly ceiling is two ceilings, not one."""
        self.assertAlmostEqual(
            period_factor(SPANNING_TWO_MONTHS, MONTH_WORKING_DAYS),
            11 / 22 + 11 / 21,
            places=6,
        )
        self.assertGreater(period_factor(SPANNING_TWO_MONTHS, MONTH_WORKING_DAYS), 1.0)

    def test_a_missing_day_count_leaves_the_figure_alone(self):
        """
        Scaling by a count that is not there would shrink the ceiling for a
        reason nobody could see. Leaving it as configured is the safer read,
        and it is what keeps the existing fixtures meaningful.
        """
        for basis in (MONTH_WORKING_DAYS, MONTH_CALENDAR_DAYS):
            with self.subTest(basis=basis):
                self.assertEqual(period_factor(WITHOUT_MONTH_COUNTS, basis), 1.0)

    def test_an_empty_or_unknown_basis_leaves_the_figure_alone(self):
        self.assertEqual(period_factor(FULL_MONTH, None), 1.0)
        self.assertEqual(period_factor(FULL_MONTH, ""), 1.0)
        self.assertEqual(period_factor(FULL_MONTH, "something_else"), 1.0)
        self.assertEqual(period_factor([], MONTH_WORKING_DAYS), 1.0)


class ComputeLimitTests(SimpleTestCase):
    def test_a_ten_day_period_is_allowed_ten_days_of_the_ceiling(self):
        """
        The reported behaviour: the ceiling was the same for ten days as for a
        whole month, so a part-month joiner could take a month's worth.
        """
        component = Component(maximum_amount=1500.0)
        self.assertAlmostEqual(
            compute_limit(component, 99999.0, TEN_DAYS), 1500 * 8 / 22, places=6
        )

    def test_a_whole_month_still_caps_at_the_figure_configured(self):
        component = Component(maximum_amount=1500.0)
        self.assertAlmostEqual(compute_limit(component, 99999.0, FULL_MONTH), 1500.0)

    def test_an_amount_under_the_ceiling_is_untouched(self):
        component = Component(maximum_amount=1500.0)
        self.assertEqual(compute_limit(component, 200.0, TEN_DAYS), 200.0)

    def test_no_ceiling_means_no_cap(self):
        component = Component(has_max_limit=False)
        self.assertEqual(compute_limit(component, 99999.0, TEN_DAYS), 99999.0)

    def test_a_ceiling_of_none_is_not_a_ceiling_of_zero(self):
        """
        maximum_amount is nullable, so a component can have the box ticked and
        no figure. Treating that as 0 would pay nothing.
        """
        component = Component(maximum_amount=None)
        self.assertEqual(compute_limit(component, 99999.0, TEN_DAYS), 99999.0)

    def test_a_flat_ceiling_ignores_the_period_length(self):
        component = Component(maximum_amount=1500.0, maximum_unit=FULL_PERIOD)
        for day_dict in (FULL_MONTH, TEN_DAYS, SPANNING_TWO_MONTHS):
            with self.subTest(days=len(day_dict)):
                self.assertEqual(compute_limit(component, 99999.0, day_dict), 1500.0)


class DefaultBasisTests(SimpleTestCase):
    """
    A new component prorates by calendar days unless told otherwise, and the
    option is first in the list so it reads from the common case down.
    """

    def test_a_new_component_prorates_by_calendar_days(self):
        from payroll.methods.proration import DEFAULT_BASIS
        from payroll.models.models import Allowance, Deduction

        self.assertEqual(DEFAULT_BASIS, MONTH_CALENDAR_DAYS)
        for model in (Allowance, Deduction):
            with self.subTest(model=model.__name__):
                self.assertEqual(
                    model._meta.get_field("maximum_unit").default, DEFAULT_BASIS
                )

    def test_the_default_is_offered_first(self):
        from payroll.models.models import MAXIMUM_UNIT_CHOICES

        self.assertEqual(MAXIMUM_UNIT_CHOICES[0][0], MONTH_CALENDAR_DAYS)

    def test_the_default_actually_scales_a_part_month(self):
        """
        A prorating default is only worth having if it prorates. Ten calendar
        days of a thirty day month is a third.
        """
        self.assertAlmostEqual(
            period_factor(TEN_DAYS, MONTH_CALENDAR_DAYS), 10 / 30, places=6
        )


class ChoiceWiringTests(SimpleTestCase):
    """
    The options on the form and the arithmetic come from one list, because a
    choice the engine does not implement silently means "do not scale".
    """

    def test_every_offered_basis_is_one_the_engine_handles(self):
        from payroll.methods.proration import BASIS_CHOICES
        from payroll.models.models import MAXIMUM_UNIT_CHOICES

        offered = [value for value, _label in MAXIMUM_UNIT_CHOICES]
        self.assertEqual(offered, [value for value, _label in BASIS_CHOICES])

        # Each one has to move a part-month period differently from a flat
        # amount, or it is a label with no behaviour behind it.
        scaling = {
            basis: period_factor(TEN_DAYS, basis)
            for basis in offered
            if basis != FULL_PERIOD
        }
        for basis, factor in scaling.items():
            with self.subTest(basis=basis):
                self.assertNotEqual(factor, 1.0, f"{basis} does not scale")


class LimitNoteEndpointTests(TestCase):
    """
    The note on the form. Its whole value is that it cannot disagree with a
    payslip, so what is asserted here is agreement with compute_limit rather
    than any particular wording.
    """

    def setUp(self):
        user = make_user("noteadmin", is_superuser=True)
        company = make_company("Note Co")
        make_employee(company=company, email="noteadmin@test.horilla", user=user)
        self.client.force_login(user)
        self.hx = {"HTTP_HX_REQUEST": "true"}

    def _preview(self, amount, unit):
        response = self.client.post(
            reverse("component-limit-preview"),
            {"maximum_amount": amount, "maximum_unit": unit},
            **self.hx,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_the_note_matches_what_the_engine_would_cap_at(self):
        from payroll.views.component_formula_views import SAMPLE_PERIODS

        data = self._preview("1500", MONTH_WORKING_DAYS)
        self.assertTrue(data["ok"])
        component = Component(maximum_amount=1500.0, maximum_unit=MONTH_WORKING_DAYS)

        for row, (_label, day_dict) in zip(data["rows"], SAMPLE_PERIODS):
            with self.subTest(period=row["label"]):
                self.assertAlmostEqual(
                    row["amount"],
                    round(compute_limit(component, 10**9, day_dict), 2),
                    places=2,
                )

    def test_a_whole_month_is_reported_unscaled(self):
        data = self._preview("1500", MONTH_WORKING_DAYS)
        self.assertEqual(data["rows"][0]["amount"], 1500.0)
        self.assertEqual(data["rows"][0]["factor"], 1.0)

    def test_a_part_month_is_reported_scaled_down(self):
        data = self._preview("1500", MONTH_WORKING_DAYS)
        self.assertLess(data["rows"][-1]["amount"], 1500.0)

    def test_a_flat_ceiling_reports_the_same_figure_throughout(self):
        data = self._preview("1500", FULL_PERIOD)
        self.assertTrue(data["flat"])
        self.assertEqual({row["amount"] for row in data["rows"]}, {1500.0})

    def test_a_maximum_that_is_not_a_number_is_refused(self):
        response = self.client.post(
            reverse("component-limit-preview"),
            {"maximum_amount": "abc", "maximum_unit": MONTH_WORKING_DAYS},
            **self.hx,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
