"""
Employee-initiated cancellation of resignation letters.

"Requested" letters are cancelled directly; "Approved" ones go through
"Cancellation Requested" and a manager decision. These drive the real views.
"""

from datetime import date, timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from offboarding.models import (
    Offboarding,
    OffboardingEmployee,
    OffboardingGeneralSetting,
    OffboardingStage,
    ResignationLetter,
)


class ResignationCancellationTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = make_company("Cancel Co")
        OffboardingGeneralSetting.objects.create(resignation_request=True)

        self.user = make_user("emp_user")
        self.employee = make_employee(
            company=self.company,
            email="emp@test.horilla",
            first_name="Eve",
            user=self.user,
        )
        self.other_user = make_user("other_user")
        self.other = make_employee(
            company=self.company,
            email="other@test.horilla",
            first_name="Oz",
            user=self.other_user,
        )
        self.manager_user = make_user("mgr_user")
        make_employee(
            company=self.company,
            email="mgr@test.horilla",
            first_name="Max",
            user=self.manager_user,
        )
        self.manager_user.user_permissions.add(
            Permission.objects.get(codename="change_resignationletter"),
            Permission.objects.get(codename="view_resignationletter"),
        )

    def _letter(self, status="requested", employee=None):
        letter = ResignationLetter.objects.create(
            employee_id=employee or self.employee,
            title="Leaving",
            description="x",
            planned_to_leave_on=date.today() + timedelta(days=30),
        )
        if status != "requested":
            ResignationLetter.objects.filter(pk=letter.pk).update(status=status)
            letter.refresh_from_db()
        return letter

    def _cancel(self, letter, user=None, method="post", **data):
        self.client.force_login(user or self.user)
        return getattr(self.client, method)(
            reverse("cancel-resignation-request", args=[letter.pk]),
            data,
            HTTP_HX_REQUEST="true",
        )

    def _decide(self, letter, action, user=None, method="post"):
        self.client.force_login(user or self.manager_user)
        return getattr(self.client, method)(
            reverse("resignation-cancellation-decision", args=[letter.pk, action]),
            HTTP_HX_REQUEST="true",
        )

    def _status(self, letter):
        return ResignationLetter.objects.get(pk=letter.pk).status

    def test_get_shows_reason_modal_and_changes_nothing(self):
        for status in ("requested", "approved"):
            ResignationLetter.objects.filter(employee_id=self.employee).delete()
            letter = self._letter(status)
            response = self._cancel(letter, method="get")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "cancel_reason")
            self.assertEqual(self._status(letter), status)

    def test_requested_is_cancelled_directly(self):
        letter = self._letter("requested")
        self._cancel(letter, cancel_reason="Found a better fit here")
        letter.refresh_from_db()
        self.assertEqual(letter.status, "cancelled")
        self.assertEqual(letter.cancel_reason, "Found a better fit here")

    def test_reason_is_required(self):
        for status in ("requested", "approved"):
            ResignationLetter.objects.filter(employee_id=self.employee).delete()
            letter = self._letter(status)
            self._cancel(letter, cancel_reason="   ")
            self.assertEqual(self._status(letter), status)

    def test_approved_becomes_cancellation_requested(self):
        letter = self._letter("approved")
        self._cancel(letter, cancel_reason="Changed my mind")
        letter.refresh_from_db()
        self.assertEqual(letter.status, "cancellation_requested")
        self.assertEqual(letter.cancel_reason, "Changed my mind")

    def test_duplicate_cancellation_request_is_refused(self):
        letter = self._letter("approved")
        self._cancel(letter, cancel_reason="first")
        self._cancel(letter, cancel_reason="again")
        letter.refresh_from_db()
        self.assertEqual(letter.status, "cancellation_requested")
        self.assertEqual(letter.cancel_reason, "first")

    def test_manager_approves_cancellation(self):
        letter = self._letter("cancellation_requested")
        self.assertEqual(self._decide(letter, "approve", method="get").status_code, 405)
        self.assertEqual(self._status(letter), "cancellation_requested")
        self._decide(letter, "approve")
        self.assertEqual(self._status(letter), "cancelled")

    def test_manager_rejects_cancellation(self):
        letter = self._letter("cancellation_requested")
        self._decide(letter, "reject")
        self.assertEqual(self._status(letter), "approved")

    def test_cannot_cancel_someone_elses_request(self):
        letter = self._letter("requested", employee=self.other)
        self._cancel(letter, cancel_reason="nope")
        self.assertEqual(self._status(letter), "requested")

    def test_cancelled_and_rejected_cannot_be_cancelled(self):
        for status in ("cancelled", "rejected"):
            ResignationLetter.objects.filter(employee_id=self.employee).delete()
            letter = self._letter(status)
            self._cancel(letter, cancel_reason="nope")
            self.assertEqual(self._status(letter), status)

    def test_cancel_and_edit_actions_disabled_when_not_applicable(self):
        for status, shown in (
            ("requested", True),
            ("approved", True),
            ("cancelled", False),
            ("rejected", False),
        ):
            ResignationLetter.objects.filter(employee_id=self.employee).delete()
            letter = self._letter(status)
            self.client.force_login(self.user)
            from django.template.loader import render_to_string

            html = render_to_string(
                "cbv/resignation/options.html",
                {
                    "instance": letter,
                    "show_cancel": True,
                    "request": type("R", (), {"user": self.user})(),
                },
            )
            self.assertEqual(
                f"/cancel-resignation-request/{letter.pk}/" in html, shown, status
            )
            self.assertIn("disabled", html if not shown else "disabled")
            if not shown:
                self.assertIn("can no longer be cancelled", html)
            self.assertEqual(
                f"/resignation-requests-update/{letter.pk}/" in html,
                status == "requested",
                status,
            )

    def test_unauthorized_user_cannot_decide(self):
        letter = self._letter("cancellation_requested")
        self._decide(letter, "approve", user=self.other_user)
        self.assertEqual(self._status(letter), "cancellation_requested")

    def test_requester_cannot_decide_own_cancellation(self):
        self.user.user_permissions.add(
            Permission.objects.get(codename="change_resignationletter")
        )
        letter = self._letter("cancellation_requested")
        self._decide(letter, "approve", user=self.user)
        self.assertEqual(self._status(letter), "cancellation_requested")

    def test_decision_needs_pending_cancellation(self):
        letter = self._letter("approved")
        self._decide(letter, "approve")
        self.assertEqual(self._status(letter), "approved")

    def test_approving_cancellation_removes_offboarding_record(self):
        off = Offboarding.objects.create(
            title="Exits", description="d", company_id=self.company
        )
        stage = OffboardingStage.objects.create(
            title="Notice", type="notice_period", offboarding_id=off
        )
        OffboardingEmployee.objects.create(employee_id=self.employee, stage_id=stage)
        letter = self._letter("cancellation_requested")
        self._decide(letter, "approve")
        self.assertEqual(self._status(letter), "cancelled")
        self.assertFalse(
            OffboardingEmployee.objects.filter(employee_id=self.employee).exists()
        )

    def test_rejecting_cancellation_keeps_offboarding_record(self):
        off = Offboarding.objects.create(
            title="Exits", description="d", company_id=self.company
        )
        stage = OffboardingStage.objects.create(
            title="Notice", type="notice_period", offboarding_id=off
        )
        OffboardingEmployee.objects.create(employee_id=self.employee, stage_id=stage)
        letter = self._letter("cancellation_requested")
        self._decide(letter, "reject")
        self.assertEqual(self._status(letter), "approved")
        self.assertTrue(
            OffboardingEmployee.objects.filter(employee_id=self.employee).exists()
        )

    def test_existing_approve_and_reject_still_work(self):
        off = Offboarding.objects.create(
            title="Exits", description="d", company_id=self.company
        )
        OffboardingStage.objects.create(
            title="Notice", type="notice_period", offboarding_id=off
        )
        self.client.force_login(self.manager_user)
        approve = self._letter("requested")
        self.client.get(
            reverse("update-letter-status"),
            {
                "letter_ids": [approve.pk],
                "status": "approved",
                "offboarding_id": off.pk,
                "notice_period_starts": date.today().isoformat(),
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(self._status(approve), "approved")

        ResignationLetter.objects.all().delete()
        reject = self._letter("requested")
        self.client.get(
            reverse("update-letter-status"),
            {"letter_ids": [reject.pk], "status": "rejected", "reject_reason": "No"},
            HTTP_HX_REQUEST="true",
        )
        reject.refresh_from_db()
        self.assertEqual(reject.status, "rejected")
        self.assertEqual(reject.reject_reason, "No")

    def test_update_status_refuses_pending_cancellation(self):
        letter = self._letter("cancellation_requested")
        self.client.force_login(self.manager_user)
        self.client.get(
            reverse("update-letter-status"),
            {"letter_ids": [letter.pk], "status": "rejected", "reject_reason": "No"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(self._status(letter), "cancellation_requested")

    def test_cancel_button_only_in_employee_tab(self):
        from django.template.loader import render_to_string

        letter = self._letter("requested")
        ctx = {"instance": letter, "request": type("R", (), {"user": self.user})()}
        page = render_to_string("cbv/resignation/options.html", ctx)
        tab = render_to_string(
            "cbv/resignation/options.html", {**ctx, "show_cancel": True}
        )
        url = f"/cancel-resignation-request/{letter.pk}/"
        self.assertNotIn(url, page)
        self.assertIn(url, tab)
