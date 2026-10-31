from django.test import SimpleTestCase

from attendance.methods.utils import real_overtime_seconds
from attendance.views.summary import ot_counts


class RealOvertimeTests(SimpleTestCase):
    """Overtime is what was worked beyond the minimum hours, never more than the stored figure."""

    def test_short_day_has_no_overtime_even_if_one_is_stored(self):
        self.assertEqual(real_overtime_seconds(25500, "08:00", 3600), 0)

    def test_overtime_is_held_to_the_hours_beyond_the_minimum(self):
        self.assertEqual(real_overtime_seconds(30000, "08:00", 3600), 1200)

    def test_stored_overtime_is_kept_when_it_is_really_worked(self):
        self.assertEqual(real_overtime_seconds(32400, "08:00", 3600), 3600)

    def test_no_minimum_means_all_worked_hours_are_overtime(self):
        self.assertEqual(real_overtime_seconds(7200, "00:00", 7200), 7200)

    def test_nothing_stored_is_nothing(self):
        self.assertEqual(real_overtime_seconds(32400, "08:00", 0), 0)


class OvertimeCountsTests(SimpleTestCase):
    def test_approved_counts(self):
        self.assertTrue(ot_counts(True, None))

    def test_unapproved_does_not(self):
        self.assertFalse(ot_counts(False, None))

    def test_regularized_or_approved_by_hr_counts(self):
        self.assertTrue(ot_counts(False, "full_present"))
        self.assertTrue(ot_counts(False, "approve_ot"))
