"""Progress percentages on objectives and key results.

These are the numbers an employee sees against their OKRs, and they are
recomputed on every EmployeeKeyResult.save():

    save() -> update_kr_progress()          this key result's percentage
           -> update_objective_progress()   the average across the objective

Nothing pinned that chain before. These are characterisation tests: they
record what the code does today so a change to the formula shows up as a
failing assertion rather than as silently different numbers on a dashboard.

Two of the behaviours recorded here are questionable rather than obviously
right, and are marked as such below -- whether they should change is a
product decision, not something to settle inside a test.
"""

from datetime import date, timedelta

from django.test import TestCase

from horilla.testkit import make_company, make_employee
from pms.models import EmployeeKeyResult, EmployeeObjective, KeyResult, Objective


class ProgressCalculationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("OKR Test Co")
        cls.employee = make_employee(company=company, email="okr@test.horilla")
        cls.objective = Objective.objects.create(
            title="Ship the thing",
            description="An objective",
            duration=30,
            company_id=company,
        )
        cls.emp_objective = EmployeeObjective.objects.create(
            objective_id=cls.objective,
            employee_id=cls.employee,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

    def _key_result(self, title="KR", target=100, duration=30):
        return KeyResult.objects.create(
            title=title,
            description="A key result",
            target_value=target,
            duration=duration,
        )

    def _employee_kr(self, *, start, current, target, title="KR"):
        return EmployeeKeyResult.objects.create(
            employee_objective_id=self.emp_objective,
            key_result_id=self._key_result(title=title, target=target),
            start_value=start,
            current_value=current,
            target_value=target,
            start_date=date(2026, 1, 1),
        )

    def test_progress_is_current_over_target(self):
        kr = self._employee_kr(start=0, current=5, target=10)
        self.assertEqual(kr.progress_percentage, 50)

    def test_progress_is_truncated_not_rounded(self):
        """progress_percentage is an IntegerField, and update_kr_progress
        assigns a float. 1/3 is stored as 33, not 33.3 and not 34."""
        kr = self._employee_kr(start=0, current=1, target=3)
        kr.refresh_from_db()
        self.assertEqual(kr.progress_percentage, 33)

    def test_start_value_does_not_affect_progress(self):
        """QUESTIONABLE, recorded rather than endorsed.

        A key result that runs from 5 to 10 reports 50% while sitting at its
        own starting value, because the formula is current/target and never
        consults start_value. Measuring progress from the baseline would give
        0% here. Changing it would move every displayed percentage in the
        system, so it is left alone and pinned instead.
        """
        kr = self._employee_kr(start=5, current=5, target=10)
        self.assertEqual(kr.progress_percentage, 50)

    def test_progress_can_exceed_100(self):
        """Overshooting the target is not clamped at the key-result level.

        The objective rollup does clamp -- see
        test_objective_progress_clamps_each_key_result -- which suggests the
        cap was added there once values above 100 showed up.
        """
        kr = self._employee_kr(start=0, current=15, target=10)
        self.assertEqual(kr.progress_percentage, 150)

    def test_zero_target_leaves_progress_untouched(self):
        """update_kr_progress guards target_value != 0, so a zero target
        keeps the field's default rather than raising ZeroDivisionError."""
        kr = self._employee_kr(start=0, current=5, target=0)
        self.assertEqual(kr.progress_percentage, 0)

    def test_objective_progress_averages_its_key_results(self):
        self._employee_kr(start=0, current=2, target=10, title="KR one")
        self._employee_kr(start=0, current=8, target=10, title="KR two")

        self.emp_objective.refresh_from_db()
        self.assertEqual(self.emp_objective.progress_percentage, 50)

    def test_objective_progress_clamps_each_key_result(self):
        """min(kr.progress_percentage, 100) per key result before averaging.

        Without the clamp the 150% below would average to 100 and the
        objective would read as complete while the other key result sits at
        50%.
        """
        self._employee_kr(start=0, current=15, target=10, title="KR over")
        self._employee_kr(start=0, current=5, target=10, title="KR half")

        self.emp_objective.refresh_from_db()
        self.assertEqual(self.emp_objective.progress_percentage, 75)

    def test_objective_with_no_key_results_stays_at_zero(self):
        """update_objective_progress guards len(krs) > 0, so an objective
        with nothing under it does not raise ZeroDivisionError."""
        self.emp_objective.update_objective_progress()
        self.emp_objective.refresh_from_db()
        self.assertEqual(self.emp_objective.progress_percentage, 0)

    def test_current_value_defaults_to_start_value_on_create(self):
        """save() seeds current_value from start_value for a new row."""
        kr = EmployeeKeyResult.objects.create(
            employee_objective_id=self.emp_objective,
            key_result_id=self._key_result(title="KR seed", target=10),
            start_value=4,
            target_value=10,
            start_date=date(2026, 1, 1),
        )
        self.assertEqual(kr.current_value, 4)

    def test_end_date_is_derived_from_key_result_duration(self):
        """save() fills end_date as start_date + the KeyResult's duration."""
        kr = self._employee_kr(start=0, current=1, target=10, title="KR dated")
        self.assertEqual(kr.end_date, date(2026, 1, 1) + timedelta(days=30))
