"""
Saving a leave type closes the modal and reloads the open list once.

The list reloads itself (HorillaFormView.HttpResponse clicks its
.reload-record button), keeping its search and filters. The response used to
send an HX-Trigger as well, whose handler replaced the whole list container
at the same time: the list's own reload then had nowhere to land
(htmx:swapError) and the list lost its search.
"""

from django.test import TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from leave.models import LeaveType

HTMX = {"HTTP_HX_REQUEST": "true"}


class LeaveTypeSaveResponseTest(TestCase):
    def setUp(self):
        user = make_user("leave_type_admin", password="secret123", is_superuser=True)
        make_employee(
            company=make_company("Leave Type Co"),
            email="leave_type_admin@test.horilla",
            user=user,
        )
        self.client.force_login(user)

    def data(self, name):
        return {
            "name": name,
            "payment_type": "unpaid",
            "payment": "unpaid",
            "count": "1",
            "period_in": "day",
            "total_days": "1",
            "limit_leave": "on",
            "reset": "",
            "carryforward_type": "no carryforward",
            "carryforward_expiry_method": "first_expiry_date",
            "require_approval": "yes",
            "require_attachment": "no",
            "exclude_company_leave": "no",
            "exclude_holiday": "no",
            "is_compensatory_leave": "",
        }

    def assertReloadsListOnce(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)
        body = response.content.decode()
        self.assertIn("$('.reload-record').click();", body)
        self.assertIn("removeClass('oh-modal--show')", body)

    def test_create(self):
        response = self.client.post(
            reverse("type-creation"), self.data("Study Leave"), **HTMX
        )
        self.assertTrue(LeaveType.objects.filter(name="Study Leave").exists())
        self.assertReloadsListOnce(response)

    def test_update(self):
        leave_type = LeaveType.objects.create(name="Old Name", total_days=1)
        response = self.client.post(
            reverse("type-update", args=[leave_type.pk]),
            self.data("New Name"),
            **HTMX,
        )
        leave_type.refresh_from_db()
        self.assertEqual(leave_type.name, "New Name")
        self.assertReloadsListOnce(response)
