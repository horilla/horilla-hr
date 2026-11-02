from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from payroll.methods import payslip_calc as calc

TWO_BANDS = [
    SimpleNamespace(from_hours=0, to_hours=2, multiplier=1.25),
    SimpleNamespace(from_hours=2, to_hours=None, multiplier=1.5),
]


class SlabHoursPayTests(SimpleTestCase):
    """Each hour of a day is paid at the band it falls in."""

    def test_inside_the_first_band(self):
        self.assertAlmostEqual(calc.slab_hours_pay(1, TWO_BANDS, 100), 125)

    def test_exactly_on_the_band_edge(self):
        self.assertAlmostEqual(calc.slab_hours_pay(2, TWO_BANDS, 100), 250)

    def test_hours_past_the_edge_use_the_next_band(self):
        self.assertAlmostEqual(calc.slab_hours_pay(3.5, TWO_BANDS, 100), 250 + 225)

    def test_no_overtime_pays_nothing(self):
        self.assertEqual(calc.slab_hours_pay(0, TWO_BANDS, 100), 0)


def _component(overtime_calc, slabs=()):
    slab_set = mock.Mock()
    slab_set.all.return_value = list(slabs)
    return SimpleNamespace(
        pk=7,
        overtime_calc=overtime_calc,
        slabs=slab_set,
        amount_per_one_hr=60.0,
        has_max_limit=False,
    )


class OvertimeAmountTests(SimpleTestCase):
    """The amount of an overtime allowance, flat or by slab."""

    def _kwargs(self, component):
        return {
            "component": component,
            "day_dict": {},
            "employee": 1,
            "component_context": {},
        }

    def test_flat_keeps_paying_the_rate_per_hour(self):
        kwargs = self._kwargs(_component("flat"))
        with mock.patch.object(calc, "compute_limit", lambda c, a, d: a):
            self.assertEqual(calc._overtime_amount(kwargs, {"d1": 3600 * 2}), 120)

    def test_slab_pays_each_day_on_its_own(self):
        kwargs = self._kwargs(_component("slab", TWO_BANDS))
        days = {"d1": 3600, "d2": 3 * 3600}
        with mock.patch.object(
            calc, "_contract_hourly_rate", return_value=100
        ), mock.patch.object(calc, "compute_limit", lambda c, a, d: a):
            self.assertEqual(calc._overtime_amount(kwargs, days), 125 + 250 + 150)

    def test_slab_without_an_hourly_wage_pays_zero_and_says_why(self):
        kwargs = self._kwargs(_component("slab", TWO_BANDS))
        with mock.patch.object(calc, "_contract_hourly_rate", return_value=0):
            self.assertEqual(calc._overtime_amount(kwargs, {"d1": 3600}), 0)
        note = kwargs["component_context"]["_allowance_notes"][7]
        self.assertIn("no hourly wage", note)
