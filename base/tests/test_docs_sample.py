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
