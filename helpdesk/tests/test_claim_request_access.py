"""Access-control tests for the claim-request approval view.

These exercise the branch where the caller holds neither
`helpdesk.change_claimrequest` nor `helpdesk.change_ticket` and is not a
department manager for the ticket. That is the only branch the permission
check in `approve_claim_request` actually has to decide -- either permission
short-circuits the `or` chain before it -- so it is also the branch a manual
smoke test with an admin account never reaches.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from helpdesk.models import ClaimRequest, Ticket, TicketType
from horilla.testkit import make_company, make_employee, make_user


class ClaimRequestAccessControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Acme")
        cls.ticket_type = TicketType.objects.create(
            title="IT Support", type="service_request", prefix="ITS"
        )

        cls.owner_user = make_user("claim-owner")
        cls.owner = make_employee(
            company=cls.company,
            email="claim-owner@test.horilla",
            first_name="Olive",
            last_name="Owner",
            user=cls.owner_user,
        )

        cls.claimant_user = make_user("claim-claimant")
        cls.claimant = make_employee(
            company=cls.company,
            email="claim-claimant@test.horilla",
            first_name="Cody",
            last_name="Claimant",
            user=cls.claimant_user,
        )

        # No helpdesk permissions, not a department manager, not assigned to
        # the ticket, and not its owner.
        cls.outsider_user = make_user("claim-outsider")
        cls.outsider = make_employee(
            company=cls.company,
            email="claim-outsider@test.horilla",
            first_name="Ivan",
            last_name="Outsider",
            user=cls.outsider_user,
        )

        cls.ticket = Ticket.objects.create(
            title="Laptop will not boot",
            employee_id=cls.owner,
            ticket_type=cls.ticket_type,
            description="Dead on power-on.",
            priority="medium",
            assigning_type="individual",
            raised_on="1",
        )
        cls.claim = ClaimRequest.objects.create(
            ticket_id=cls.ticket, employee_id=cls.claimant
        )

    def setUp(self):
        self.url = reverse("approve-claim-request", kwargs={"req_id": self.claim.pk})

    def test_unrelated_caller_cannot_approve_a_claim_request(self):
        """Someone with no relationship to the ticket must be refused.

        This is refused by the ``ticket_owner_can_enter`` decorator rather
        than by the view's own check, so it passes even with that check
        broken; it is here to pin the outer guard in place.
        """
        self.client.force_login(self.outsider_user)

        self.client.get(self.url, {"approve": "True"})

        self.assertNotIn(
            self.claimant,
            self.ticket.assigned_to.all(),
            "a caller unrelated to the ticket approved a claim request",
        )

    def test_ticket_owner_without_helpdesk_permission_cannot_approve(self):
        """The reachable case the view's own check exists to decide.

        The ticket's own raiser satisfies ``ticket_owner_can_enter`` (it
        admits ``request.user.employee_get == ticket.employee_id``), so the
        decorator lets them in and the view's permission check is the only
        thing left standing between them and approving a claim. They hold no
        helpdesk permission and are not a department manager, so it must
        refuse -- approving adds the claimant to ``ticket.assigned_to``.
        """
        self.client.force_login(self.owner_user)

        self.client.get(self.url, {"approve": "True"})

        self.assertNotIn(
            self.claimant,
            self.ticket.assigned_to.all(),
            "the ticket owner approved a claim request without permission",
        )

    def test_caller_with_change_ticket_permission_can_approve(self):
        """The check must still let a genuinely authorised caller through."""
        self.outsider_user.user_permissions.add(
            Permission.objects.get(
                codename="change_ticket", content_type__app_label="helpdesk"
            )
        )
        self.client.force_login(self.outsider_user)

        self.client.get(self.url, {"approve": "True"})

        self.assertIn(
            self.claimant,
            self.ticket.assigned_to.all(),
            "an authorised caller was blocked from approving",
        )
