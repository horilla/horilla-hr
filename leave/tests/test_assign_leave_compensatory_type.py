"""Assign Leave and the Leave Balances leave type filter offer the Compensatory
Leave Type only while compensatory leave is enabled, as the Leave Types list
already does."""

from django.test import TestCase

from leave.filters import AssignedLeaveFilter
from leave.forms import AssignLeaveForm
from leave.models import LeaveGeneralSetting, LeaveType


class CompensatoryTypeChoicesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.paid = LeaveType.objects.create(name="Paid Leave", payment="paid")
        cls.compensatory = LeaveType.objects.create(
            name="Compensatory Leave Type", payment="paid", is_compensatory_leave=True
        )

    def assign_choices(self):
        return set(AssignLeaveForm().fields["leave_type_id"].queryset)

    def filter_choices(self):
        queryset_fn = AssignedLeaveFilter.ajax_fields["leave_type_id"]["queryset_fn"]
        return set(queryset_fn(None))

    def test_hidden_while_compensatory_leave_is_not_set_up(self):
        self.assertEqual(self.assign_choices(), {self.paid})
        self.assertEqual(self.filter_choices(), {self.paid})

    def test_hidden_when_compensatory_leave_is_disabled(self):
        LeaveGeneralSetting.objects.create(compensatory_leave=False)

        self.assertEqual(self.assign_choices(), {self.paid})
        self.assertEqual(self.filter_choices(), {self.paid})

    def test_offered_when_compensatory_leave_is_enabled(self):
        LeaveGeneralSetting.objects.create(compensatory_leave=True)

        self.assertEqual(self.assign_choices(), {self.paid, self.compensatory})
        self.assertEqual(self.filter_choices(), {self.paid, self.compensatory})
