"""
Bulk "Update" on Leave Balances.

The bulk update form applied its fields with one SQL UPDATE, which never
calls AvailableLeave.save(): total_leave_days kept the old figure, and no
history row was written, so the change was missing from the leave ledger
and the audit log.
"""

from django.http import QueryDict
from django.test import TestCase

from horilla_views.forms import DynamicBulkUpdateForm


class BulkUpdateAvailableLeaveTests(TestCase):
    def setUp(self):
        from horilla.testkit import make_company, make_employee
        from leave.models import AvailableLeave, LeaveType

        company = make_company("Bulk Balance Co")
        leave_type = LeaveType.objects.create(
            name="Bulk Balance Type",
            total_days=5,
            carryforward_type="carryforward",
            carryforward_max=10,
        )
        self.balances = [
            AvailableLeave.objects.create(
                employee_id=make_employee(
                    company=company, email=f"bulk{n}@test.horilla"
                ),
                leave_type_id=leave_type,
                available_days=5,
                carryforward_days=2,
            )
            for n in range(2)
        ]

    def bulk_update(self, **values):
        from leave.cbv.assigned_leave import AssignedleaveList

        data = QueryDict(mutable=True)
        data.update(values)
        form = DynamicBulkUpdateForm(
            data,
            root_model=self.balances[0].__class__,
            bulk_update_fields=AssignedleaveList.bulk_update_fields,
            ids=[balance.pk for balance in self.balances],
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        for balance in self.balances:
            balance.refresh_from_db()

    def test_total_follows_the_new_available_days(self):
        self.bulk_update(available_days="8")

        for balance in self.balances:
            self.assertEqual(balance.available_days, 8)
            self.assertEqual(balance.total_leave_days, 10)

    def test_total_follows_the_new_carryforward_days(self):
        self.bulk_update(carryforward_days="0")

        for balance in self.balances:
            self.assertEqual(balance.total_leave_days, 5)

    def test_the_change_is_in_the_leave_ledger(self):
        self.bulk_update(available_days="8")

        for balance in self.balances:
            self.assertEqual(balance.history.count(), 2)
            row = balance.build_ledger()[0]
            self.assertEqual(row["label"], "Balance updated")
            self.assertEqual(row["credit"], 3)
            self.assertEqual(row["balance"], 10)

    def test_the_change_is_in_the_audit_log(self):
        from auditlog.models import LogEntry

        self.bulk_update(available_days="8")

        for balance in self.balances:
            entry = LogEntry.objects.get_for_object(balance).latest("timestamp")
            old, new = entry.changes_dict["available_days"]
            self.assertEqual((float(old), float(new)), (5, 8))

    def test_several_fields_are_one_change(self):
        self.bulk_update(available_days="8", assigned_date="2026-01-05")

        for balance in self.balances:
            self.assertEqual(balance.history.count(), 2)
            self.assertEqual(str(balance.assigned_date), "2026-01-05")

    def test_total_leave_days_is_not_offered(self):
        """It is worked out from the other two, so a typed value was wrong."""
        from leave.cbv.assigned_leave import AssignedleaveList

        self.assertNotIn("total_leave_days", AssignedleaveList.bulk_update_fields)
