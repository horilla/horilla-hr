"""The sample company of the user guide is complete, consistent and private."""

from datetime import date

from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from base.demo_data.docs_sample import (
    CAST,
    COMPANY,
    DEFAULT_PASSWORD,
    ANCHOR_DATE,
    DOMAIN,
    STAFF,
    seed_docs_sample,
)
from base.models import Company
from employee.models import Employee
from horilla_auth.models import HorillaUser
from leave.models import AvailableLeave, LeaveRequest, LeaveType


def cast_login(first, last):
    return f"{first}.{last}".lower() + "@" + DOMAIN


class DocsSampleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.result = seed_docs_sample(today=date.today())

    def employee(self, last):
        return Employee.objects.get(employee_last_name=last)

    def test_the_company_and_its_people_exist(self):
        company = Company.objects.get(company=COMPANY)
        self.assertEqual(self.result["employees"], len(CAST) + len(STAFF))
        in_company = Employee.objects.filter(employee_work_info__company_id=company)
        self.assertEqual(in_company.count(), len(CAST) + len(STAFF))

    def test_the_cast_signs_in_and_colleagues_do_not(self):
        for first, last, *_ in CAST:
            # through the real backends, which need a request (lockout tracking)
            user = authenticate(
                request=RequestFactory().post("/login/"),
                username=cast_login(first, last),
                password=DEFAULT_PASSWORD,
            )
            self.assertIsNotNone(user, cast_login(first, last))
        colleague = HorillaUser.objects.get(username=f"jonas.weber@{DOMAIN}")
        self.assertFalse(colleague.has_usable_password())

    def test_roles_and_reporting_lines_match_the_cast(self):
        maya = HorillaUser.objects.get(username=cast_login("Maya", "Chen"))
        self.assertTrue(maya.is_superuser)
        for last, group in (("Okafor", "HR Manager"), ("Becker", "Payroll Manager")):
            user = self.employee(last).employee_user_id
            self.assertTrue(
                user.groups.filter(name=group).exists(), f"{last} is not in {group}"
            )
        self.assertTrue(Group.objects.filter(name="HR Manager").exists())
        manager_of = lambda last: self.employee(
            last
        ).employee_work_info.reporting_manager_id
        self.assertEqual(manager_of("Menon").employee_last_name, "Rossi")
        self.assertEqual(manager_of("Rossi").employee_last_name, "Okafor")
        self.assertIsNone(manager_of("Okafor"))

    def test_the_new_hire_joined_recently(self):
        joined = self.employee("Nair").employee_work_info.date_joining
        self.assertLessEqual((date.today() - joined).days, 14)

    def test_leave_types_and_balances(self):
        self.assertEqual(
            set(LeaveType.objects.values_list("name", flat=True)),
            {"Annual Leave", "Sick Leave", "Unpaid Leave"},
        )
        people = len(CAST) + len(STAFF)
        self.assertEqual(AvailableLeave.objects.count(), 2 * people)

    def test_requests_come_in_each_state_and_balances_follow(self):
        states = {}
        for request in LeaveRequest.objects.all():
            states.setdefault(request.status, []).append(request)
        self.assertEqual(
            {k: len(v) for k, v in states.items()},
            {"requested": 2, "approved": 2, "rejected": 1},
        )
        rejected = states["rejected"][0]
        self.assertEqual(rejected.employee_id.employee_last_name, "Becker")
        self.assertEqual(rejected.reject_reason, "Month-end close")

        def balance(last, leave_name):
            return AvailableLeave.objects.get(
                employee_id=self.employee(last), leave_type_id__name=leave_name
            ).available_days

        self.assertEqual(balance("Haddad", "Annual Leave"), 18 - 3)  # three days taken
        self.assertEqual(balance("Fischer", "Sick Leave"), 10 - 1)
        self.assertEqual(
            balance("Menon", "Annual Leave"), 18
        )  # still waiting for approval
        self.assertEqual(
            balance("Becker", "Annual Leave"), 18
        )  # rejected: nothing taken

    def test_no_request_falls_on_a_weekend(self):
        for request in LeaveRequest.objects.all():
            self.assertLess(request.start_date.weekday(), 5, request)
            self.assertLess(request.end_date.weekday(), 5, request)

    def test_seeding_twice_changes_nothing(self):
        before = Employee.objects.count()
        again = seed_docs_sample(today=date.today())
        self.assertIn("skipped", again)
        self.assertEqual(Employee.objects.count(), before)

    def test_the_administrator_sees_the_leave_requests_of_the_cast(self):
        client = Client()
        client.force_login(HorillaUser.objects.get(username=cast_login("Maya", "Chen")))
        page = client.get(reverse("request-filter"), HTTP_HX_REQUEST="true")
        self.assertEqual(page.status_code, 200)
        text = page.content.decode()
        for name in ("Ravi Menon", "Omar Haddad", "Tom Becker"):
            self.assertIn(name, text)


class DocsSampleAttendanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = date.today()
        cls.result = seed_docs_sample(today=cls.today)

    def rows(self, last=None):
        from attendance.models import Attendance

        rows = Attendance._base_manager.all()
        if last:
            rows = rows.filter(employee_id__employee_last_name=last)
        return rows.order_by("attendance_date")

    def test_everyone_has_twenty_working_days_and_none_on_a_weekend(self):
        self.assertEqual(self.result["attendance_rows"], (len(CAST) + len(STAFF)) * 20)
        self.assertEqual(self.rows().count(), self.result["attendance_rows"])
        self.assertTrue(all(r.attendance_date.weekday() < 5 for r in self.rows()))
        self.assertTrue(all(r.attendance_date < self.today for r in self.rows()))

    def test_lena_is_late_three_days_of_the_last_week(self):
        late = [r for r in self.rows("Fischer") if r.attendance_clock_in.minute == 25]
        self.assertEqual(len(late), 3)
        self.assertEqual({r.attendance_date.weekday() for r in late}, {0, 2, 3})

    def test_omar_works_the_evening_shift(self):
        row = self.rows("Haddad").first()
        self.assertEqual(row.shift_id.employee_shift, "Evening Shift")
        self.assertGreaterEqual(row.attendance_clock_in.hour, 13)

    def test_ravi_has_one_pending_correction_request(self):
        from attendance.models import Attendance

        pending = Attendance._base_manager.filter(is_validate_request=True)
        self.assertEqual(pending.count(), 1)
        request = pending.get()
        self.assertEqual(request.employee_id.employee_last_name, "Menon")
        self.assertEqual(request.attendance_clock_out.hour, 14)
        self.assertIn("17:30", request.requested_data)
        self.assertFalse(request.attendance_validated)

    def test_only_the_latest_day_is_waiting_for_validation(self):
        waiting = self.rows().filter(attendance_validated=False)
        self.assertEqual(waiting.count(), len(CAST) + len(STAFF))
        self.assertEqual(len({r.attendance_date for r in waiting}), 1)

    def test_late_and_early_records_match_the_stories(self):
        from attendance.models import AttendanceLateComeEarlyOut as Record

        late = Record._base_manager.filter(type="late_come")
        self.assertEqual(late.count(), 3)
        self.assertEqual({r.employee_id.employee_last_name for r in late}, {"Fischer"})
        early = Record._base_manager.get(type="early_out")
        self.assertEqual(early.employee_id.employee_last_name, "Menon")


class DocsSampleAnchorTests(TestCase):
    """Without a date the seeder uses the fixed anchor, never the day it runs."""

    @classmethod
    def setUpTestData(cls):
        seed_docs_sample()

    def test_the_default_anchor_is_fixed(self):
        from attendance.models import Attendance

        self.assertEqual(ANCHOR_DATE, date(2026, 11, 18))
        latest = Attendance._base_manager.order_by("-attendance_date").first()
        self.assertEqual(latest.attendance_date, date(2026, 11, 17))
        ravi = LeaveRequest.objects.get(employee_id__employee_last_name="Menon")
        self.assertEqual(ravi.start_date, date(2026, 11, 23))

    def test_unpaid_leave_has_a_usable_balance_when_assigned(self):
        unpaid = LeaveType.objects.get(name="Unpaid Leave")
        self.assertEqual(unpaid.total_days, 100000)
