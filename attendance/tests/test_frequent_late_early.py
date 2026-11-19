"""
Frequent Late Arrivals and Frequent Early Departures on the attendance
dashboard: days with a late come / early out record, per employee, for the
selected period.
"""

from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from attendance.models import Attendance, AttendanceLateComeEarlyOut
from base.models import EmployeeShift
from horilla.testkit.factories import make_company, make_employee, make_user

MONDAY, FRIDAY = date(2026, 10, 5), date(2026, 10, 9)
WEEK = {"from_date": MONDAY.isoformat(), "to_date": FRIDAY.isoformat()}


def attend(employee, day, *types, shift=True):
    attendance = Attendance.objects.create(
        employee_id=employee,
        shift_id=EmployeeShift.objects.first() if shift else None,
        attendance_date=day,
        attendance_clock_in_date=day,
        attendance_clock_in=time(8, 0),
        attendance_worked_hour="00:00",
        minimum_hour="00:00",
    )
    for kind in types:
        # As Horilla's late_come() does: the model's save() saves twice, so
        # objects.create() (a forced insert) would fail.
        AttendanceLateComeEarlyOut(attendance_id=attendance, type=kind).save()


class TestFrequentLateAndEarly(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = company = make_company("Late Test Ltd")
        EmployeeShift.objects.create(employee_shift="Day").company_id.add(company)
        cls.often = make_employee(
            company=company, email="often@late.test", first_name="Often"
        )
        cls.once = make_employee(
            company=company, email="once@late.test", first_name="Once"
        )
        cls.never = make_employee(
            company=company, email="never@late.test", first_name="Never"
        )
        cls.boss = make_user("boss", is_superuser=True)
        make_employee(company=company, email="boss@late.test", user=cls.boss)

    def get(self, name, **params):
        self.client.force_login(self.boss)
        return self.client.get(reverse(name), params).json()

    def rows(self, name, **params):
        return [
            (row["name"].split()[0], row["days"], row["attended_days"])
            for row in self.get(name, **params)["employees"]
        ]

    def test_late_days_are_counted_out_of_the_days_attended(self):
        attend(self.often, MONDAY, "late_come")
        attend(self.often, date(2026, 10, 6), "late_come", "early_out")
        attend(self.often, date(2026, 10, 7))
        attend(self.once, MONDAY, "late_come")
        attend(self.never, MONDAY)
        self.assertEqual(
            self.rows("attendance-dashboard-frequent-late", **WEEK),
            [("Often", 2, 3), ("Once", 1, 1)],
        )
        self.assertEqual(
            self.rows("attendance-dashboard-frequent-early", **WEEK),
            [("Often", 1, 3)],
        )

    def test_only_the_selected_period_counts(self):
        attend(self.often, date(2026, 9, 30), "late_come")
        attend(self.often, date(2026, 10, 12), "late_come")
        attend(self.once, FRIDAY, "late_come")
        data = self.get("attendance-dashboard-frequent-late", **WEEK)
        self.assertEqual([r["name"].split()[0] for r in data["employees"]], ["Once"])
        self.assertEqual(
            (data["from_date"], data["to_date"]), ("2026-10-05", "2026-10-09")
        )

    def test_a_day_without_a_shift_is_not_counted(self):
        # The Late Come / Early Out list leaves such records out, and each
        # name opens that list.
        attend(self.often, MONDAY, "late_come", shift=False)
        attend(self.once, MONDAY, "late_come")
        self.assertEqual(
            self.rows("attendance-dashboard-frequent-late", **WEEK),
            [("Once", 1, 1)],
        )

    def test_someone_who_cannot_see_attendance_sees_nobody_else(self):
        attend(self.often, MONDAY, "late_come")
        clerk = make_user("clerk")
        make_employee(
            company=self.company,
            email="clerk@late.test",
            user=clerk,
        )
        self.client.force_login(clerk)
        data = self.client.get(
            reverse("attendance-dashboard-frequent-late"), WEEK
        ).json()
        self.assertEqual(data["employees"], [])

    def test_the_dashboard_has_both_cards(self):
        self.client.force_login(self.boss)
        page = self.client.get(reverse("attendance-dashboard"))
        self.assertContains(page, "Frequent Late Arrivals")
        self.assertContains(page, "Frequent Early Departures")
        self.assertContains(page, reverse("attendance-dashboard-frequent-late"))
        self.assertContains(page, reverse("attendance-dashboard-frequent-early"))
