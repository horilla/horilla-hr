"""Saving an incomplete row must work; a wrong value must still be refused.

`HorillaModel.clean_fields()` runs Django's own field validation on every
save. That pass also reports blank and null values, but code creates
incomplete rows on purpose, and two of them broke a fresh install:

* the post-save signal of `Company` creates the global `AttendanceGeneralSetting`
  row, which has no company, so loading the demo fixture failed at its first
  company and left the database without any company;
* the `default_currency` context processor creates the default
  `PayrollSettings` row, which also has no company, so the login page answered
  500 on an empty database.

Whether a field is required, and which values a field may take beyond its
model `choices`, is for the caller to say. These tests save without a
request, as the fixture loader does, render the login page on a database that
has no rows at all, and check that a value that was given is still validated.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from attendance.models import (
    Attendance,
    AttendanceConflictResolution,
    AttendanceGeneralSetting,
)
from payroll.models.tax_models import PayrollSettings


class IncompleteRowsOnSaveTests(TestCase):
    def test_global_attendance_setting_saves_without_a_company(self):
        setting = AttendanceGeneralSetting(company_id=None)
        setting.save()
        self.assertIsNotNone(setting.pk)

    def test_global_payroll_settings_saves_without_a_company(self):
        settings = PayrollSettings(currency_symbol="$", company_id=None)
        settings.save()
        self.assertIsNotNone(settings.pk)

    def test_a_row_with_every_field_empty_is_not_reported_as_blank(self):
        # clean_fields only, no write: nothing here may name a blank field.
        Attendance().clean_fields()

    def test_a_given_value_is_still_validated(self):
        """The reason for calling Django's pass at all: validators are not inert."""
        with self.assertRaises(ValidationError) as caught:
            Attendance(attendance_overtime="not a time").clean_fields()
        self.assertIn("attendance_overtime", caught.exception.message_dict)


    def test_a_value_outside_the_model_choices_is_not_refused(self):
        """`resolution` takes values such as "split:P+UL" that are not choices."""
        AttendanceConflictResolution(resolution="split:P+UL").clean_fields()


class LoginPageOnEmptyDatabaseTests(TestCase):
    def test_login_page_renders_with_no_company_and_no_settings(self):
        """The first visit to a fresh install must not answer 500."""
        PayrollSettings.objects.all().delete()
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PayrollSettings.objects.filter(company_id=None).count(), 1)
