"""Tests for the carryforward expiry methods (first expiry date / assignment date)."""

from datetime import date

from django.test import TestCase


class CarryforwardExpiryMethodTests(TestCase):
    def setUp(self):
        from horilla.testkit import make_company, make_employee
        from leave.models import AvailableLeave, LeaveType

        company = make_company("Leave Expiry Co")
        self.emp_a = make_employee(company=company, email="exp_a@test.horilla")
        self.emp_b = make_employee(company=company, email="exp_b@test.horilla")
        self.LeaveType = LeaveType
        self.AvailableLeave = AvailableLeave

    def _type(self, method, **kwargs):
        defaults = dict(
            name=f"Expiry {method}",
            total_days=12,
            reset=True,
            reset_based="yearly",
            reset_month="1",
            reset_day="1",
            carryforward_type="carryforward expire",
            carryforward_max=5,
            carryforward_expire_in=3,
            carryforward_expire_period="month",
            carryforward_expiry_method=method,
        )
        defaults.update(kwargs)
        return self.LeaveType.objects.create(**defaults)

    def _avail(self, lt, employee, assigned, carry=4):
        return self.AvailableLeave.objects.create(
            employee_id=employee,
            leave_type_id=lt,
            available_days=12,
            carryforward_days=carry,
            assigned_date=assigned,
        )

    def test_default_method_keeps_legacy_behaviour(self):
        lt = self.LeaveType.objects.create(
            name="Legacy",
            total_days=5,
            carryforward_type="carryforward expire",
            carryforward_max=5,
            carryforward_expire_in=1,
            carryforward_expire_period="year",
        )
        self.assertEqual(lt.carryforward_expiry_method, "first_expiry_date")
        self.assertIsNotNone(lt.carryforward_expire_date)

    def test_first_expiry_date_applies_to_every_employee(self):
        lt = self._type("first_expiry_date", carryforward_expire_date=date(2027, 3, 31))
        a = self._avail(lt, self.emp_a, date(2026, 1, 10))
        b = self._avail(lt, self.emp_b, date(2026, 6, 20))
        self.assertEqual(a.expired_date, date(2027, 3, 31))
        self.assertEqual(b.expired_date, date(2027, 3, 31))

    def test_editing_first_expiry_date_updates_existing_balances(self):
        lt = self._type("first_expiry_date", carryforward_expire_date=date(2027, 3, 31))
        a = self._avail(lt, self.emp_a, date(2026, 1, 10))
        lt.carryforward_expire_date = date(2027, 6, 30)
        lt.save()
        a.refresh_from_db()
        self.assertEqual(a.expired_date, date(2027, 6, 30))

    def test_assignment_date_is_per_employee_and_clears_shared_date(self):
        lt = self._type("assignment_date", carryforward_expire_date=date(2027, 3, 31))
        self.assertIsNone(lt.carryforward_expire_date)
        a = self._avail(lt, self.emp_a, date(2026, 1, 31))
        b = self._avail(lt, self.emp_b, date(2026, 6, 20))
        self.assertEqual(a.expired_date, date(2026, 4, 30))
        self.assertEqual(b.expired_date, date(2026, 9, 20))

    def test_assignment_date_boundaries_do_not_drift(self):
        lt = self._type("assignment_date", carryforward_expire_in=1)
        anchor = date(2026, 1, 31)
        self.assertEqual(
            lt.assignment_expiry_date(anchor, date(2026, 2, 28)), date(2026, 3, 31)
        )
        self.assertEqual(
            lt.assignment_expiry_date(anchor, date(2026, 3, 31)), date(2026, 4, 30)
        )

    def test_assignment_date_leap_day_year_period(self):
        lt = self._type(
            "assignment_date",
            carryforward_expire_in=1,
            carryforward_expire_period="year",
        )
        self.assertEqual(
            lt.assignment_expiry_date(date(2028, 2, 29)), date(2029, 2, 28)
        )

    def test_expire_carryforward_deducts_once_and_moves_date(self):
        lt = self._type("assignment_date")
        a = self._avail(lt, self.emp_a, date(2026, 1, 15), carry=4)
        self.assertEqual(a.expired_date, date(2026, 4, 15))

        self.assertFalse(a.expire_carryforward(date(2026, 4, 14)))
        self.assertEqual(a.carryforward_days, 4)

        self.assertTrue(a.expire_carryforward(date(2026, 4, 15)))
        a.refresh_from_db()
        self.assertEqual(a.carryforward_days, 0)
        self.assertEqual(a.expired_date, date(2026, 7, 15))

        # Running again the same day must not process it a second time.
        self.assertFalse(a.expire_carryforward(date(2026, 4, 15)))

    def test_missed_runs_skip_to_next_future_boundary(self):
        lt = self._type("assignment_date")
        a = self._avail(lt, self.emp_a, date(2026, 1, 15))
        self.assertTrue(a.expire_carryforward(date(2026, 8, 1)))
        a.refresh_from_db()
        self.assertEqual(a.expired_date, date(2026, 10, 15))

    def test_existing_dates_are_not_recalculated_on_save(self):
        lt = self._type("first_expiry_date", carryforward_expire_date=date(2027, 3, 31))
        a = self._avail(lt, self.emp_a, date(2026, 1, 10))
        a.expired_date = date(2026, 12, 1)
        a.save()
        a.refresh_from_db()
        self.assertEqual(a.expired_date, date(2026, 12, 1))

    def test_non_expiring_type_never_expires(self):
        lt = self._type("assignment_date", carryforward_type="carryforward")
        a = self._avail(lt, self.emp_a, date(2026, 1, 15))
        a.expired_date = date(2026, 2, 1)
        self.assertFalse(a.expire_carryforward(date(2026, 3, 1)))
        self.assertEqual(a.carryforward_days, 4)

    def test_form_requires_first_expiry_date(self):
        from leave.forms import LeaveTypeForm

        form = LeaveTypeForm(
            data={
                "name": "X",
                "reset": "on",
                "carryforward_type": "carryforward expire",
                "carryforward_expiry_method": "first_expiry_date",
                "carryforward_expire_in": 3,
                "carryforward_expire_period": "month",
            }
        )
        form.is_valid()
        self.assertIn("carryforward_expire_date", form.errors)

        form = LeaveTypeForm(
            data={
                "name": "X",
                "reset": "on",
                "carryforward_type": "carryforward expire",
                "carryforward_expiry_method": "assignment_date",
                "carryforward_expire_in": 3,
                "carryforward_expire_period": "month",
            }
        )
        form.is_valid()
        self.assertNotIn("carryforward_expire_date", form.errors)
