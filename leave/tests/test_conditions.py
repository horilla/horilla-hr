"""Tests for LeaveTypeCondition model and evaluate_leave_type_conditions."""

from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from leave.models import LeaveTypeCondition
from leave.services import evaluate_leave_type_conditions
from leave.tests.helpers import _make_employee, _make_leave_type


class LeaveTypeConditionModelTest(TestCase):
    def test_str_with_value(self):
        cond = LeaveTypeCondition.__new__(LeaveTypeCondition)
        cond.condition_type = "gender"
        cond.value = "female"
        self.assertIn("female", str(cond))
        self.assertIn("Gender", str(cond))

    def test_str_without_value(self):
        cond = LeaveTypeCondition.__new__(LeaveTypeCondition)
        cond.condition_type = "once_per_employment"
        cond.value = None
        self.assertIn("Once Per Employment", str(cond))

    def test_clean_raises_when_value_missing_for_gender(self):
        cond = LeaveTypeCondition.__new__(LeaveTypeCondition)
        cond.pk = None
        cond.condition_type = "gender"
        cond.value = ""
        with self.assertRaises(ValidationError):
            cond.clean()

    def test_clean_passes_for_once_per_employment_without_value(self):
        cond = LeaveTypeCondition.__new__(LeaveTypeCondition)
        cond.pk = None
        cond.condition_type = "once_per_employment"
        cond.value = None
        # Should not raise
        cond.clean()


# ---------------------------------------------------------------------------
# evaluate_leave_type_conditions service tests
# ---------------------------------------------------------------------------


class GenderConditionTest(TestCase):
    def _gender_condition(self, value):
        cond = MagicMock()
        cond.condition_type = "gender"
        cond.value = value
        return cond

    def test_matching_gender_passes(self):
        lt = _make_leave_type()
        lt.conditions.all.return_value = [self._gender_condition("female")]
        employee = _make_employee(gender="female")
        is_eligible, msg = evaluate_leave_type_conditions(lt, employee)
        self.assertTrue(is_eligible)
        self.assertIsNone(msg)

    def test_wrong_gender_fails(self):
        lt = _make_leave_type()
        lt.conditions.all.return_value = [self._gender_condition("female")]
        employee = _make_employee(gender="male")
        is_eligible, msg = evaluate_leave_type_conditions(lt, employee)
        self.assertFalse(is_eligible)
        self.assertIn("female", str(msg))

    def test_case_insensitive_gender_match(self):
        lt = _make_leave_type()
        lt.conditions.all.return_value = [self._gender_condition("Female")]
        employee = _make_employee(gender="female")
        is_eligible, _ = evaluate_leave_type_conditions(lt, employee)
        self.assertTrue(is_eligible)


class OncePerEmploymentConditionTest(TestCase):
    def _once_condition(self):
        cond = MagicMock()
        cond.condition_type = "once_per_employment"
        cond.value = None
        return cond

    @patch("leave.models.AvailableLeave")
    def test_not_yet_assigned_passes(self, MockAL):
        MockAL.objects.filter.return_value.exists.return_value = False
        lt = _make_leave_type()
        lt.conditions.all.return_value = [self._once_condition()]
        employee = _make_employee()
        is_eligible, msg = evaluate_leave_type_conditions(lt, employee)
        self.assertTrue(is_eligible)

    @patch("leave.models.AvailableLeave")
    def test_already_assigned_blocks(self, MockAL):
        MockAL.objects.filter.return_value.exists.return_value = True
        lt = _make_leave_type()
        lt.conditions.all.return_value = [self._once_condition()]
        employee = _make_employee()
        is_eligible, msg = evaluate_leave_type_conditions(lt, employee)
        self.assertFalse(is_eligible)
        self.assertIn("once", str(msg).lower())


class MaritalStatusConditionTest(TestCase):
    def _marital_condition(self, value):
        cond = MagicMock()
        cond.condition_type = "marital_status"
        cond.value = value
        return cond

    def test_matching_marital_passes(self):
        lt = _make_leave_type()
        lt.conditions.all.return_value = [self._marital_condition("married")]
        employee = _make_employee(marital_status="married")
        is_eligible, _ = evaluate_leave_type_conditions(lt, employee)
        self.assertTrue(is_eligible)

    def test_wrong_marital_fails(self):
        lt = _make_leave_type()
        lt.conditions.all.return_value = [self._marital_condition("married")]
        employee = _make_employee(marital_status="single")
        is_eligible, msg = evaluate_leave_type_conditions(lt, employee)
        self.assertFalse(is_eligible)


class NoConditionsTest(TestCase):
    def test_no_conditions_always_eligible(self):
        lt = _make_leave_type()
        lt.conditions.all.return_value = []
        employee = _make_employee()
        is_eligible, msg = evaluate_leave_type_conditions(lt, employee)
        self.assertTrue(is_eligible)
        self.assertIsNone(msg)


class MultipleConditionsTest(TestCase):
    """When multiple conditions are set, all must pass."""

    @patch("leave.models.AvailableLeave")
    def test_all_pass(self, MockAL):
        MockAL.objects.filter.return_value.exists.return_value = False

        gender_cond = MagicMock()
        gender_cond.condition_type = "gender"
        gender_cond.value = "female"

        once_cond = MagicMock()
        once_cond.condition_type = "once_per_employment"
        once_cond.value = None

        lt = _make_leave_type()
        lt.conditions.all.return_value = [gender_cond, once_cond]
        employee = _make_employee(gender="female")

        is_eligible, msg = evaluate_leave_type_conditions(lt, employee)
        self.assertTrue(is_eligible)

    @patch("leave.models.AvailableLeave")
    def test_first_fails_short_circuits(self, MockAL):
        MockAL.objects.filter.return_value.exists.return_value = False

        gender_cond = MagicMock()
        gender_cond.condition_type = "gender"
        gender_cond.value = "female"

        once_cond = MagicMock()
        once_cond.condition_type = "once_per_employment"
        once_cond.value = None

        lt = _make_leave_type()
        lt.conditions.all.return_value = [gender_cond, once_cond]
        employee = _make_employee(gender="male")  # fails gender check

        is_eligible, msg = evaluate_leave_type_conditions(lt, employee)
        self.assertFalse(is_eligible)
        # once_per_employment filter should NOT have been called
        MockAL.objects.filter.assert_not_called()
