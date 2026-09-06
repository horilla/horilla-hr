"""Regression tests for the automation mail thread's re-read of its instance.

send_mail runs on a worker thread with its own DB connection, so the row it
was handed can legitimately be absent by the time it reads it back: a save
inside an open transaction is not visible to another connection, and an
object can be deleted between the save and the read. Both used to raise
DoesNotExist out of a bare thread.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from horilla_automations.signals import send_mail
from leave.models import LeaveRequest, LeaveType


class SendMailMissingInstanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Automation Race Co")
        cls.employee = make_employee(
            company=company, email="automation-race@test.horilla"
        )
        cls.leave_type = LeaveType.objects.create(
            name="Casual Automation Race", total_days=5
        )

    def _automation(self):
        """A stand-in for MailAutomation.

        send_mail only reaches automation.method_title before the early
        return under test, so a stub keeps the test focused on the re-read
        rather than on building a valid automation row.
        """
        automation = MagicMock()
        automation.method_title = "race_probe"
        return automation

    def test_deleted_instance_returns_quietly(self):
        """A row that vanished before the thread read it must not raise."""
        request = LeaveRequest.objects.create(
            employee_id=self.employee,
            leave_type_id=self.leave_type,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 5),
            requested_days=1,
            description="race probe",
        )
        stale = LeaveRequest.objects.get(pk=request.pk)
        LeaveRequest.objects.filter(pk=request.pk).delete()

        # Before the fix this raised LeaveRequest.DoesNotExist.
        send_mail(None, self._automation(), stale)

    def test_unsaved_instance_skips_the_re_read(self):
        """An instance with no pk must not be re-read at all.

        Asserted by patching the manager: the guarded branch is keyed on
        instance.pk, so an unsaved instance should never reach the query.
        Only the re-read is pinned here -- send_mail goes on to resolve
        automation.model, which a stub cannot satisfy, so the call is not
        run to completion.
        """
        unsaved = LeaveRequest(
            employee_id=self.employee,
            leave_type_id=self.leave_type,
            start_date=date(2026, 1, 6),
            end_date=date(2026, 1, 6),
            requested_days=1,
        )
        self.assertIsNone(unsaved.pk)

        with patch.object(
            LeaveRequest.objects, "filter", side_effect=AssertionError("re-read ran")
        ):
            with self.assertRaises(Exception) as ctx:
                send_mail(None, self._automation(), unsaved)

        self.assertNotIsInstance(
            ctx.exception, AssertionError, "send_mail re-read an instance with no pk"
        )
