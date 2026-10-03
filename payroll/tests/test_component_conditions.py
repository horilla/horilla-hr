"""
Condition-based components.

The eligibility check existed in three divergent copies, one per gatherer, and
each carried its own defects. They are now one typed evaluator
(component_engine.component_applies_to); these tests pin the behaviours that
were wrong.

This is the one intentionally drifting change in the payroll rework: a
condition that could never match before may now match. That is the fix, not a
side effect — but it means a tenant relying on a broken condition silently
doing nothing will see it start applying.
"""

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from payroll.methods.component_engine import component_applies_to, condition_holds
from payroll.models.models import Allowance, MultipleCondition


class ConditionEvaluatorTests(TestCase):
    def setUp(self):
        company = make_company("Cond Co")
        self.employee = make_employee(company=company, email="cond@test.horilla")
        self.employee.gender = "male"
        self.employee.country = "United States"
        self.employee.marital_status = "single"
        self.employee.children = 2
        self.employee.save()

    def _component(self, field, condition, value, **kw):
        return Allowance.objects.create(
            title="Conditional",
            is_condition_based=True,
            field=field,
            condition=condition,
            value=value,
            **kw
        )

    # -- the multi-word value bug ----------------------------------------

    def test_multi_word_value_matches(self):
        """
        The old code did value.lower().replace(" ", "_"), turning "United
        States" into "united_states" — which could never equal the stored
        value. Every multi-word country, state or department condition
        silently failed.
        """
        self.assertTrue(
            component_applies_to(
                self._component("country", "equal", "United States"), self.employee
            )
        )

    def test_multi_word_value_still_rejects_a_mismatch(self):
        self.assertFalse(
            component_applies_to(
                self._component("country", "equal", "United Kingdom"), self.employee
            )
        )

    # -- casing ------------------------------------------------------------

    def test_value_comparison_is_case_insensitive(self):
        self.assertTrue(
            component_applies_to(
                self._component("gender", "equal", "Male"), self.employee
            )
        )

    def test_icontains_is_actually_case_insensitive(self):
        """
        The legacy operator map routed "icontains" to operator.contains, which
        is case-SENSITIVE — so an operator labelled "Contains" did not behave
        as labelled.
        """
        self.assertTrue(
            component_applies_to(
                self._component("country", "icontains", "STATES"), self.employee
            )
        )

    # -- the blind cast ----------------------------------------------------

    def test_unparseable_number_fails_the_condition_instead_of_crashing(self):
        """
        type(actual)(raw) raised ValueError out of the middle of payslip
        generation. A condition that cannot be evaluated does not hold; it
        does not take the payslip down with it.
        """
        component = self._component("children", "gt", "not-a-number")
        self.assertFalse(component_applies_to(component, self.employee))

    def test_numeric_comparison_works(self):
        self.assertTrue(
            component_applies_to(self._component("children", "gt", "1"), self.employee)
        )
        self.assertFalse(
            component_applies_to(self._component("children", "gt", "5"), self.employee)
        )

    def test_boolean_false_is_not_read_as_true(self):
        """bool("false") is True in Python — the old cast made a false
        condition read as satisfied."""
        self.assertFalse(condition_holds(self.employee, "is_active", "equal", "false"))
        self.assertTrue(condition_holds(self.employee, "is_active", "equal", "true"))

    # -- all conditions must hold -----------------------------------------

    def test_every_extra_condition_must_hold(self):
        component = self._component("gender", "equal", "male")
        extra = MultipleCondition.objects.create(
            field="country", condition="equal", value="Canada"
        )
        component.other_conditions.add(extra)
        # gender matches, country does not -> the component must not apply
        self.assertFalse(component_applies_to(component, self.employee))

    def test_all_matching_conditions_apply(self):
        component = self._component("gender", "equal", "male")
        extra = MultipleCondition.objects.create(
            field="country", condition="equal", value="United States"
        )
        component.other_conditions.add(extra)
        self.assertTrue(component_applies_to(component, self.employee))

    def test_extra_conditions_use_the_same_rules_as_the_primary(self):
        """
        The old code mangled the primary condition's value but read
        other_conditions raw, so the two sources behaved differently on the
        same input.
        """
        component = self._component("gender", "equal", "male")
        extra = MultipleCondition.objects.create(
            field="country", condition="equal", value="UNITED STATES"
        )
        component.other_conditions.add(extra)
        self.assertTrue(component_applies_to(component, self.employee))

    # -- non-conditional components ---------------------------------------

    def test_a_component_without_conditions_always_applies(self):
        self.assertTrue(
            component_applies_to(
                Allowance.objects.create(title="Plain", is_condition_based=False),
                self.employee,
            )
        )

    def test_a_missing_attribute_fails_the_condition(self):
        self.assertFalse(
            condition_holds(self.employee, "no_such_field", "equal", "anything")
        )
