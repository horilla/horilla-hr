"""Leave cancellation workflow: approved -> cancel_requested -> cancelled/approved."""

from datetime import date, timedelta

from django.test import TestCase

from horilla.testkit import make_company, make_employee, make_user
from leave.methods import decide_leave_cancellation, request_leave_cancellation
from leave.models import AvailableLeave, LeaveRequest, LeaverequestComment, LeaveType


class CancellationWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Cancel Co")
        cls.owner_user = make_user("cancel_owner", password="secret123")
        cls.owner = make_employee(
            company=company, email="cancel_owner@test.horilla", user=cls.owner_user
        )
        cls.manager_user = make_user("cancel_manager", password="secret123")
        cls.manager = make_employee(
            company=company, email="cancel_manager@test.horilla", user=cls.manager_user
        )
        cls.other_user = make_user("cancel_other", password="secret123")
        cls.other = make_employee(
            company=company, email="cancel_other@test.horilla", user=cls.other_user
        )
        work_info = cls.owner.employee_work_info
        work_info.reporting_manager_id = cls.manager
        work_info.save()
        cls.leave_type = LeaveType.objects.create(name="Cancel Leave", total_days=20)

    def setUp(self):
        self.available = AvailableLeave.objects.create(
            employee_id=self.owner,
            leave_type_id=self.leave_type,
            available_days=5,
            carryforward_days=0,
            total_leave_days=5,
        )
        start = date.today() + timedelta(days=3)
        leave = LeaveRequest(
            employee_id=self.owner,
            leave_type_id=self.leave_type,
            start_date=start,
            end_date=start,
            start_date_breakdown="full_day",
            end_date_breakdown="full_day",
            requested_days=1,
            description="cancel flow",
            approved_available_days=0,
            approved_carryforward_days=0,
            status="requested",
        )
        leave.no_approval()
        leave.save()
        self.leave = LeaveRequest.objects.get(pk=leave.pk)

    def _balance(self):
        self.available.refresh_from_db()
        return self.available.available_days

    def test_request_keeps_leave_in_force(self):
        leave, error = request_leave_cancellation(
            self.leave.pk, "plans changed", self.owner
        )
        self.assertIsNone(error)
        self.assertEqual(leave.status, "cancel_requested")
        self.assertEqual(self._balance(), 4)  # nothing refunded yet

    def test_only_approved_can_request_and_no_duplicates(self):
        request_leave_cancellation(self.leave.pk, "x", self.owner)
        _, error = request_leave_cancellation(self.leave.pk, "again", self.owner)
        self.assertIn("already pending", error)
        for status in ("requested", "rejected", "cancelled"):
            LeaveRequest.objects.filter(pk=self.leave.pk).update(status=status)
            _, error = request_leave_cancellation(self.leave.pk, "x", self.owner)
            self.assertIsNotNone(error, status)

    def test_cannot_request_again_after_rejection(self):
        request_leave_cancellation(self.leave.pk, "x", self.owner)
        decide_leave_cancellation(self.leave.pk, False, self.manager)
        self.assertEqual(LeaveRequest.objects.get(pk=self.leave.pk).status, "approved")
        _, error = request_leave_cancellation(self.leave.pk, "again", self.owner)
        self.assertIn("already been requested", error)
        self.assertEqual(LeaveRequest.objects.get(pk=self.leave.pk).status, "approved")

    def test_approve_cancels_and_refunds(self):
        request_leave_cancellation(self.leave.pk, "x", self.owner)
        leave, error = decide_leave_cancellation(self.leave.pk, True, self.manager)
        self.assertIsNone(error)
        self.assertEqual(leave.status, "cancelled")
        self.assertEqual(self._balance(), 5)
        # a second decision is refused, so the refund can't apply twice
        _, error = decide_leave_cancellation(self.leave.pk, True, self.manager)
        self.assertIsNotNone(error)
        self.assertEqual(self._balance(), 5)

    def test_reject_restores_approved_untouched(self):
        before = (
            self.leave.start_date,
            self.leave.end_date,
            self.leave.approved_available_days,
        )
        request_leave_cancellation(self.leave.pk, "x", self.owner)
        leave, error = decide_leave_cancellation(self.leave.pk, False, self.manager)
        self.assertIsNone(error)
        self.assertEqual(leave.status, "approved")
        self.assertEqual(
            (leave.start_date, leave.end_date, leave.approved_available_days), before
        )
        self.assertEqual(self._balance(), 4)

    def test_cannot_decide_without_pending_request(self):
        _, error = decide_leave_cancellation(self.leave.pk, True, self.manager)
        self.assertIsNotNone(error)
        self.assertEqual(self._balance(), 4)

    def test_attendance_record_survives_until_cancellation_approved(self):
        from attendance.models import WorkRecords

        def records():
            return WorkRecords._base_manager.filter(
                is_leave_record=True, employee_id=self.owner, date=self.leave.start_date
            ).count()

        self.assertEqual(records(), 1)
        request_leave_cancellation(self.leave.pk, "x", self.owner)
        self.assertEqual(records(), 1)
        decide_leave_cancellation(self.leave.pk, True, self.manager)
        self.assertEqual(records(), 0)


class CancellationViewPermissionTests(CancellationWorkflowTests):
    def _post(self, user, name, **kw):
        self.client.force_login(user)
        from django.urls import reverse

        return self.client.post(
            reverse(name, kwargs={"id": self.leave.pk}), HTTP_HX_REQUEST="true", **kw
        )

    def _status(self):
        return LeaveRequest.objects.get(pk=self.leave.pk).status

    def test_reject_form_loads_for_manager_only(self):
        from django.urls import reverse

        self._post(self.owner_user, "user-request-cancel", data={"reason": "x"})
        url = reverse("leave-cancellation-reject", kwargs={"id": self.leave.pk})
        self.client.force_login(self.manager_user)
        # The form is recognised by its reason field. The visible label was removed from the modal (the modal
        # title carries it), so the textarea gets its accessible name from aria-label.
        response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertContains(response, 'name="reason"')
        self.assertContains(response, 'aria-label="Rejection Reason"')
        self.assertNotContains(response, "<label")
        self.client.force_login(self.other_user)
        self.assertNotContains(
            self.client.get(url, HTTP_HX_REQUEST="true"), 'name="reason"'
        )

    def test_non_owner_cannot_request(self):
        self._post(self.other_user, "user-request-cancel", data={"reason": "x"})
        self.assertEqual(self._status(), "approved")

    def test_owner_requests_then_unrelated_user_cannot_decide(self):
        self._post(self.owner_user, "user-request-cancel", data={"reason": "need to"})
        self.assertEqual(self._status(), "cancel_requested")
        self._post(self.other_user, "leave-cancellation-approve")
        self.assertEqual(self._status(), "cancel_requested")

    def test_owner_cannot_approve_own_cancellation(self):
        self._post(self.owner_user, "user-request-cancel", data={"reason": "need to"})
        self._post(self.owner_user, "leave-cancellation-approve")
        self.assertEqual(self._status(), "cancel_requested")

    def test_manager_decides(self):
        self._post(self.owner_user, "user-request-cancel", data={"reason": "need to"})
        self._post(self.manager_user, "leave-cancellation-reject")  # no reason: refused
        self.assertEqual(self._status(), "cancel_requested")
        self._post(
            self.manager_user, "leave-cancellation-reject", data={"reason": "Busy week"}
        )
        self.assertEqual(self._status(), "approved")
        self.assertTrue(
            LeaverequestComment.objects.filter(
                request_id=self.leave.pk, comment__contains="Busy week"
            ).exists()
        )
        self._post(self.owner_user, "user-request-cancel", data={"reason": "again"})
        self.assertEqual(self._status(), "approved")  # one request per leave

    def test_approve_view_refuses_cancel_requested(self):
        """Re-approving would deduct the days twice."""
        self._post(self.owner_user, "user-request-cancel", data={"reason": "x"})
        self.client.force_login(self.manager_user)
        from django.urls import reverse

        self.client.get(
            reverse("request-approve", kwargs={"id": self.leave.pk}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(self._status(), "cancel_requested")
        self.available.refresh_from_db()
        self.assertEqual(self.available.available_days, 4)
