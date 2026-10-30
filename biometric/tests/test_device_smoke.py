"""Biometric schedule-time validator tests."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from biometric.models import validate_schedule_time_format


class ScheduleTimeFormatTests(TestCase):
    def test_valid_hhmm(self):
        validate_schedule_time_format("01:30")  # no raise

    def test_rejects_zero_duration(self):
        with self.assertRaises(ValidationError):
            validate_schedule_time_format("00:00")

    def test_rejects_bad_format(self):
        with self.assertRaises(ValidationError):
            validate_schedule_time_format("not-a-time")

    def test_rejects_invalid_minute(self):
        with self.assertRaises(ValidationError):
            validate_schedule_time_format("01:60")
