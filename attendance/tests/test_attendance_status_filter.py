"""The Attendances filter's Attendance Status picks days the way the Employees
page's filter and the dashboard count them: late or early when the day has
that record, on time when it has no late arrival record."""

import datetime

from django.test import TestCase

from attendance.filters import AttendanceFilters
from attendance.models import Attendance, AttendanceLateComeEarlyOut
from horilla.testkit import make_company, make_employee
from horilla.testkit.factories import make_attendance

DAY = datetime.date(2026, 11, 24)


class AttendanceStatusFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Status Co")
        cls.days = {}
        for name, types in (
            ("prompt", []),
            ("tardy", ["late_come"]),
            ("leaver", ["early_out"]),
            ("both", ["late_come", "early_out"]),
        ):
            employee = make_employee(company=company, email=f"{name}@test.horilla")
            attendance = make_attendance(employee=employee, attendance_date=DAY)
            for kind in types:
                AttendanceLateComeEarlyOut(attendance_id=attendance, type=kind).save()
            cls.days[name] = attendance.pk

    def picked(self, status):
        filtered = AttendanceFilters(
            {"attendance_status": status}, queryset=Attendance.objects.all()
        ).qs
        names = {pk: name for name, pk in self.days.items()}
        return {names[pk] for pk in filtered.values_list("pk", flat=True)}

    def test_on_time_is_every_day_without_a_late_arrival(self):
        self.assertEqual(self.picked("on_time"), {"prompt", "leaver"})

    def test_late_arrival(self):
        self.assertEqual(self.picked("late_come"), {"tardy", "both"})

    def test_early_departure(self):
        self.assertEqual(self.picked("early_out"), {"leaver", "both"})

    def test_any_status_filters_nothing(self):
        self.assertEqual(self.picked(""), set(self.days))

    def test_same_choices_as_the_employees_filter(self):
        from employee.filters import EmployeeFilter

        attendances = AttendanceFilters().form.fields["attendance_status"]
        employees = EmployeeFilter().form.fields["attendance_status"]
        self.assertEqual(attendances.label, employees.label)
        # The blank "Any" choice is worded per filter.
        self.assertEqual(list(attendances.choices)[1:], list(employees.choices)[1:])
