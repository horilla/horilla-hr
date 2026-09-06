"""Approving a reimbursement must not rewrite what was claimed.

GHSA-56x4-6268-vg4f reported that the approve/reject endpoint had no
authorization beyond "is the caller logged in", so any employee could approve
any claim and set the payout to any value. The permission gate was added
separately; these tests cover the two defence-in-depth points from the same
report that were not:

  - the approval request could still overwrite the claimed amount, so an
    approved claim need not resemble the submitted one and nothing records the
    original figure. That turns a privilege-escalation bug into an insider
    fraud and audit-integrity one.
  - `status` was written straight through `queryset.update()`, which skips
    model validation, so any string could land in the status column.

Encashments are the deliberate exception: their payout is computed at approval
time rather than claimed up front, matching what the web flow in
payroll.views.component_views.approve_reimbursements already does.
"""

from datetime import date

from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.models import Reimbursement

ENDPOINT = "/api/payroll/reimbusement-approve-reject/{}"


class ReimbursementApprovalIntegrityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        company = make_company("Reimb Co")
        self.approver_user = make_user("reimb_approver", password="secret123")
        self.approver = make_employee(
            company=company,
            email="reimb_approver@test.horilla",
            user=self.approver_user,
        )
        self.claimant = make_employee(
            company=company, email="reimb_claimant@test.horilla"
        )
        self.approver_user.user_permissions.add(
            Permission.objects.get(codename="change_reimbursement")
        )
        self.client.force_authenticate(
            user=type(self.approver_user).objects.get(pk=self.approver_user.pk)
        )

    def _claim(self, claim_type="reimbursement", amount=100):
        # Reimbursement.save() reads the thread-local request to decide whether
        # to re-bind employee_id to the caller, so creating a claim outside a
        # request raises AttributeError. Stand one in with an approver, which
        # is the case where save() leaves employee_id alone.
        from django.test import RequestFactory

        from horilla.horilla_middlewares import _thread_locals

        request = RequestFactory().post("/")
        request.user = type(self.approver_user).objects.get(pk=self.approver_user.pk)
        _thread_locals.request = request
        self.addCleanup(setattr, _thread_locals, "request", None)

        return Reimbursement.objects.create(
            title="Taxi fare",
            type=claim_type,
            employee_id=self.claimant,
            amount=amount,
            status="requested",
            attachment="claims/receipt.pdf",
            allowance_on=date.today(),
        )

    def test_approval_cannot_rewrite_the_claimed_amount(self):
        """The reported fraud: approve at an amount nobody claimed."""
        claim = self._claim(amount=100)
        response = self.client.post(
            ENDPOINT.format(claim.id),
            {"status": "approved", "amount": "900001"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        claim.refresh_from_db()
        self.assertEqual(claim.status, "approved")
        self.assertEqual(float(claim.amount), 100.0)

    def test_encashment_amount_is_still_settable(self):
        """The legitimate exception -- an encashment payout is computed at
        approval time, not claimed. Removing this would break the feature."""
        claim = self._claim(claim_type="bonus_encashment", amount=0)
        response = self.client.post(
            ENDPOINT.format(claim.id),
            {"status": "approved", "amount": "250"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        claim.refresh_from_db()
        self.assertEqual(float(claim.amount), 250.0)

    def test_invalid_status_is_rejected(self):
        """queryset.update() skipped model validation, so any string stored."""
        claim = self._claim()
        response = self.client.post(
            ENDPOINT.format(claim.id),
            {"status": "totally-made-up"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        claim.refresh_from_db()
        self.assertEqual(claim.status, "requested")

    def test_valid_statuses_are_accepted(self):
        """A validator that rejects everything would pass the test above."""
        for status in ("approved", "rejected", "requested"):
            with self.subTest(status=status):
                claim = self._claim()
                response = self.client.post(
                    ENDPOINT.format(claim.id),
                    {"status": status},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                claim.refresh_from_db()
                self.assertEqual(claim.status, status)

    def test_missing_reimbursement_is_404_not_500(self):
        """Previously .first() on an empty queryset raised AttributeError."""
        response = self.client.post(
            ENDPOINT.format(999999),
            {"status": "approved"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_non_numeric_amount_is_400_not_500(self):
        """eval_validate is ast.literal_eval, which raises on junk input."""
        claim = self._claim(claim_type="bonus_encashment")
        response = self.client.post(
            ENDPOINT.format(claim.id),
            {"status": "approved", "amount": "abc"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_employee_without_permission_still_blocked(self):
        """The original finding -- pinned so the gate cannot be lost again."""
        plain = make_user("reimb_plain", password="secret123")
        make_employee(
            company=make_company("Other Co"),
            email="reimb_plain@test.horilla",
            user=plain,
        )
        claim = self._claim()
        client = APIClient()
        client.force_authenticate(user=plain)
        response = client.post(
            ENDPOINT.format(claim.id),
            {"status": "approved", "amount": "900001"},
            format="json",
        )
        self.assertNotEqual(response.status_code, 200)
        claim.refresh_from_db()
        self.assertEqual(claim.status, "requested")
        self.assertEqual(float(claim.amount), 100.0)
