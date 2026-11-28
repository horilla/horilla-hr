"""Leave balance screens leave out carry forward figures when nothing uses them.

With no leave type carrying leave forward, carryforward_days is always 0 and
total_leave_days always equals available_days, so both are left out.
"""

from django.test import Client, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from leave.forms import AvailableLeaveColumnExportForm, AvailableLeaveUpdateForm
from leave.models import AvailableLeave, LeaveType


class CarryforwardInUseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Carry Forward Co")
        cls.admin = make_user("cf_admin", password="secret123", is_superuser=True)
        cls.admin_employee = make_employee(
            company=company, email="cf_admin@test.horilla", user=cls.admin
        )
        cls.employee = make_employee(company=company, email="cf_emp@test.horilla")
        cls.leave_type = LeaveType.objects.create(
            name="Annual Leave", total_days=20, carryforward_type="no carryforward"
        )
        cls.balance = AvailableLeave.objects.create(
            employee_id=cls.employee,
            leave_type_id=cls.leave_type,
            available_days=20,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def _use_carryforward(self):
        LeaveType.objects.create(
            name="Carried Leave",
            total_days=5,
            carryforward_type="carryforward",
            carryforward_max=5,
        )

    def _get(self, name, **kwargs):
        return self.client.get(
            reverse(name, kwargs=kwargs or None), HTTP_HX_REQUEST="true"
        )

    def test_not_in_use_without_carryforward_types_or_balances(self):
        self.assertFalse(LeaveType.carryforward_in_use())

    def test_in_use_when_a_leave_type_carries_forward(self):
        self._use_carryforward()
        self.assertTrue(LeaveType.carryforward_in_use())

    def test_in_use_while_a_balance_still_holds_carried_days(self):
        # e.g. a leave type switched to "no carryforward" before its next reset
        AvailableLeave.objects.filter(pk=self.balance.pk).update(carryforward_days=3)
        self.assertTrue(LeaveType.carryforward_in_use())

    def test_list_columns(self):
        response = self._get("assign-filter")
        self.assertContains(response, "Available Days")
        self.assertNotContains(response, "Carryforward Days")
        self.assertNotContains(response, "Total Leave Days")

        self._use_carryforward()
        response = self._get("assign-filter")
        self.assertContains(response, "Carryforward Days")
        self.assertContains(response, "Total Leave Days")

    def test_detail_view(self):
        response = self._get("available-leave-single-view", pk=self.balance.pk)
        self.assertContains(response, "Available Days")
        self.assertNotContains(response, "Carryforward Days")
        self.assertNotContains(response, "Total Leave Days")

        self._use_carryforward()
        response = self._get("available-leave-single-view", pk=self.balance.pk)
        self.assertContains(response, "Carryforward Days")

    def test_filter_panel_and_group_by(self):
        response = self._get("assigned-leave-nav")
        self.assertContains(response, "Available Days Greater or Equal")
        self.assertNotContains(response, "Carryforward Days")
        self.assertNotContains(response, "Total Leave Days")

        self._use_carryforward()
        response = self._get("assigned-leave-nav")
        self.assertContains(response, "Carryforward Days Greater or Equal")
        self.assertContains(response, "Total Leave Days Greater or Equal")

    def test_export_dialog(self):
        response = self._get("assigned-leave-nav-export")
        self.assertContains(response, "Available Days Greater or Equal")
        self.assertNotContains(response, "Carryforward Days")
        self.assertNotContains(response, "Total Leave Days")

        self._use_carryforward()
        response = self._get("assigned-leave-nav-export")
        self.assertContains(response, "Carryforward Days Greater or Equal")

    def test_export_columns(self):
        field = AvailableLeaveColumnExportForm().fields["selected_fields"]
        choices = [value for value, _label in field.choices]
        self.assertIn("available_days", choices)
        self.assertNotIn("carryforward_days", choices)
        self.assertNotIn("total_leave_days", choices)
        self.assertNotIn("carryforward_days", field.initial)

        self._use_carryforward()
        field = AvailableLeaveColumnExportForm().fields["selected_fields"]
        choices = [value for value, _label in field.choices]
        self.assertIn("carryforward_days", choices)
        self.assertIn("total_leave_days", field.initial)

    def test_update_form_keeps_carried_days_when_hidden(self):
        form = AvailableLeaveUpdateForm({"available_days": 18}, instance=self.balance)
        self.assertNotIn("carryforward_days", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.available_days, 18)
        self.assertEqual(self.balance.total_leave_days, 18)

        self._use_carryforward()
        self.assertIn("carryforward_days", AvailableLeaveUpdateForm().fields)

    def test_update_dialog(self):
        response = self._get("available-leave-update", id=self.balance.pk)
        self.assertContains(response, 'name="available_days"')
        self.assertNotContains(response, 'name="carryforward_days"')

    def test_employee_leave_tab(self):
        response = self._get("leave-tab", pk=self.employee.pk)
        self.assertContains(response, "Annual Leave")
        self.assertNotContains(response, "Carryforward Leave Days")

        self._use_carryforward()
        response = self._get("leave-tab", pk=self.employee.pk)
        self.assertContains(response, "Carryforward Leave Days")

    def test_my_leave_cards(self):
        AvailableLeave.objects.create(
            employee_id=self.admin_employee,
            leave_type_id=self.leave_type,
            available_days=20,
        )
        response = self._get("user-leave-filter")
        self.assertContains(response, "Annual Leave")
        self.assertNotContains(response, "Carryforward Leave Days")

        self._use_carryforward()
        response = self._get("user-leave-filter")
        self.assertContains(response, "Carryforward Leave Days")
