"""The Leave Dashboard shows the Pending Compensatory Requests card only while
compensatory leave is enabled, as the Compensatory Leave Requests menu item does."""

from django.test import TestCase, override_settings
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from leave.models import LeaveGeneralSetting

CARD = "Pending Compensatory Requests"


@override_settings(SECURE_SSL_REDIRECT=False)
class CompensatoryCardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user("comp_card_admin", is_superuser=True)
        make_employee(
            company=make_company("Comp Card Co"),
            email="comp_card_admin@test.horilla",
            user=cls.user,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def dashboard(self):
        return self.client.get(reverse("leave-dashboard"))

    def test_card_is_hidden_while_compensatory_leave_is_not_set_up(self):
        response = self.dashboard()

        self.assertContains(response, "Pending Leave Requests")
        self.assertNotContains(response, CARD)

    def test_card_is_hidden_when_compensatory_leave_is_disabled(self):
        LeaveGeneralSetting.objects.create(compensatory_leave=False)

        self.assertNotContains(self.dashboard(), CARD)

    def test_card_is_shown_when_compensatory_leave_is_enabled(self):
        LeaveGeneralSetting.objects.create(compensatory_leave=True)

        self.assertContains(self.dashboard(), CARD)
