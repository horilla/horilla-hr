"""
The rest of the missing-check findings: the leave allocation bulk form and its
approve switch, permission-group assignment, comment uploads and the
compensatory comment views, and the roster planner.
"""

from datetime import date, timedelta

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from base.models import Department, EmployeeShift, Roster
from employee.models import Employee, EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user
from leave.models import (
    AvailableLeave,
    CompensatoryLeaveRequest,
    CompensatoryLeaverequestComment,
    LeaveAllocationRequest,
    LeaveGeneralSetting,
    LeaveType,
)

HX = {"HTTP_HX_REQUEST": "true"}
DENIED = "decorator_404.html"


def _grant(user, dotted):
    app_label, codename = dotted.split(".")
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )


class Base(TestCase):
    def setUp(self):
        self.client.raise_request_exception = False
        company = make_company("Remaining Co")
        self.manager_user = make_user("remmanager")
        self.manager = make_employee(
            company=company, email="remmanager@test.horilla", user=self.manager_user
        )
        self.report = make_employee(company=company, email="remreport@test.horilla")
        self.stranger = make_employee(company=company, email="remstranger@test.horilla")
        EmployeeWorkInformation.objects.filter(employee_id=self.report).update(
            reporting_manager_id=self.manager
        )
        self.client.force_login(self.manager_user)

    def assertDenied(self, response):
        names = [t.name for t in response.templates]
        self.assertTrue(
            response.status_code == 403 or DENIED in names,
            f"expected a refusal, got {response.status_code} {names}",
        )

    def assertAllowed(self, response):
        names = [t.name for t in response.templates]
        self.assertNotEqual(response.status_code, 403)
        self.assertNotIn(DENIED, names)


class LeaveAllocationBulkTests(Base):
    def setUp(self):
        super().setUp()
        self.leave_type = LeaveType.objects.create(name="Annual", payment="paid")
        self.url = reverse("leave-allocation-request-bulk-create")

    def _post(self, employees, approve=False):
        data = {
            "leave_type_id": self.leave_type.pk,
            "employee_id": [e.pk for e in employees],
            "requested_days": "5",
            "description": "probe",
        }
        if approve:
            data["is_approved"] = "on"
        return self.client.post(self.url, data, **HX)

    def test_a_manager_is_refused_for_a_stranger(self):
        self.assertDenied(self._post([self.stranger]))
        self.assertEqual(LeaveAllocationRequest.objects.count(), 0)

    def test_a_manager_may_allocate_for_a_report(self):
        self._post([self.report])
        self.assertEqual(LeaveAllocationRequest.objects.count(), 1)

    def test_a_manager_may_approve_for_a_report(self):
        self._post([self.report], approve=True)
        self.assertEqual(
            AvailableLeave.objects.get(employee_id=self.report).available_days, 5
        )

    def test_the_add_permission_alone_cannot_approve_for_a_stranger(self):
        _grant(self.manager_user, "leave.add_leaveallocationrequest")
        self._post([self.stranger], approve=True)
        self.assertEqual(AvailableLeave.objects.count(), 0)
        self.assertEqual(LeaveAllocationRequest.objects.count(), 0)

    def test_the_add_permission_may_request_for_a_stranger_without_approval(self):
        _grant(self.manager_user, "leave.add_leaveallocationrequest")
        self._post([self.stranger])
        self.assertEqual(LeaveAllocationRequest.objects.count(), 1)
        self.assertEqual(AvailableLeave.objects.count(), 0)

    def test_the_approve_permission_may_approve_for_anyone(self):
        _grant(self.manager_user, "leave.add_leaveallocationrequest")
        _grant(self.manager_user, "leave.delete_leaveallocationrequest")
        self._post([self.stranger], approve=True)
        self.assertEqual(
            AvailableLeave.objects.get(employee_id=self.stranger).available_days, 5
        )


class GroupAssignTests(Base):
    def _get(self):
        return self.client.get(
            reverse("allocation-assign-group-user"),
            {"instance_id": self.stranger.pk, "employee": self.stranger.pk},
            **HX,
        )

    def test_a_recruitment_manager_cannot_assign_permission_groups(self):
        _grant(self.manager_user, "recruitment.view_recruitment")
        self.assertDenied(self._get())

    def test_a_superuser_can(self):
        self.manager_user.is_superuser = True
        self.manager_user.save()
        self.assertAllowed(self._get())


class CompensatoryCommentTests(Base):
    def setUp(self):
        super().setUp()
        LeaveGeneralSetting.objects.create(compensatory_leave=True)
        leave_type = LeaveType.objects.create(
            name="Comp", payment="paid", is_compensatory_leave=True
        )
        self.request_of = {
            employee: CompensatoryLeaveRequest.objects.create(
                employee_id=employee, leave_type_id=leave_type, description="x"
            )
            for employee in (self.stranger, self.report, self.manager)
        }

    def _view(self, employee):
        pk = self.request_of[employee].pk
        return self.client.get(
            reverse("view-compensatory-leave-comment", kwargs={"comp_leave_id": pk}),
            **HX,
        )

    def _create(self, employee):
        pk = self.request_of[employee].pk
        return self.client.get(
            reverse("create-compensatory-leave-comment", kwargs={"comp_leave_id": pk}),
            **HX,
        )

    def test_comments_on_a_strangers_request_are_refused(self):
        self.assertDenied(self._view(self.stranger))
        self.assertDenied(self._create(self.stranger))

    def test_a_manager_and_the_owner_may_use_comments(self):
        for employee in (self.report, self.manager):
            with self.subTest(employee=employee.pk):
                self.assertAllowed(self._view(employee))
                self.assertAllowed(self._create(employee))

    def test_a_file_cannot_be_attached_to_another_requests_comment(self):
        """The comment id must belong to the request named in the path."""
        foreign = CompensatoryLeaverequestComment.objects.create(
            request_id=self.request_of[self.stranger],
            employee_id=self.stranger,
            comment="theirs",
        )
        pk = self.request_of[self.manager].pk
        upload = SimpleUploadedFile("a.txt", b"data")
        self.client.post(
            reverse("view-compensatory-leave-comment", kwargs={"comp_leave_id": pk})
            + f"?comment_id={foreign.pk}",
            {"files": upload},
            **HX,
        )
        self.assertEqual(foreign.files.count(), 0)

    def test_a_file_is_attached_to_a_comment_of_the_same_request(self):
        own = CompensatoryLeaverequestComment.objects.create(
            request_id=self.request_of[self.manager],
            employee_id=self.manager,
            comment="mine",
        )
        pk = self.request_of[self.manager].pk
        upload = SimpleUploadedFile("a.txt", b"data")
        self.client.post(
            reverse("view-compensatory-leave-comment", kwargs={"comp_leave_id": pk})
            + f"?comment_id={own.pk}",
            {"files": upload},
            **HX,
        )
        self.assertEqual(own.files.count(), 1)

    def test_a_missing_or_malformed_comment_id_is_refused_not_a_server_error(self):
        pk = self.request_of[self.manager].pk
        url = reverse("view-compensatory-leave-comment", kwargs={"comp_leave_id": pk})
        for suffix in ("", "?comment_id=abc"):
            with self.subTest(suffix=suffix):
                response = self.client.post(
                    url + suffix, {"files": SimpleUploadedFile("a.txt", b"d")}, **HX
                )
                self.assertDenied(response)


class RosterScopeTests(Base):
    def setUp(self):
        super().setUp()
        self.department = Department.objects.create(department="Planning")
        self.shift = EmployeeShift.objects.create(employee_shift="Day")
        self.day = date.today() + timedelta(days=3)
        self.entries = {
            employee: Roster.objects.create(
                employee=employee,
                date=self.day,
                shift=self.shift,
                department=self.department,
            )
            for employee in (self.report, self.stranger)
        }

    def _cell(self, employee):
        return self.client.post(
            reverse("roster-cell-update"),
            {"employee": employee.pk, "date": str(self.day), "shift": self.shift.pk},
            **HX,
        )

    def test_the_grid_shows_a_manager_only_their_reports(self):
        response = self.client.get(reverse("roster-grid"), **HX)
        shown = {row["employee"].pk for row in response.context["rows"]}
        self.assertEqual(shown, {self.report.pk})

    def test_the_grid_shows_the_permission_holder_everyone(self):
        _grant(self.manager_user, "base.change_roster")
        response = self.client.get(reverse("roster-grid"), **HX)
        shown = {row["employee"].pk for row in response.context["rows"]}
        self.assertEqual(shown, {self.report.pk, self.stranger.pk})

    def test_a_cell_of_a_stranger_cannot_be_edited(self):
        self.assertDenied(self._cell(self.stranger))

    def test_a_cell_of_a_report_gets_past_the_check(self):
        self.assertAllowed(self._cell(self.report))

    def test_bulk_publish_refuses_a_stranger_and_publishes_nothing(self):
        response = self.client.post(
            reverse("roster-employees-publish"),
            {
                "employee_ids": [self.report.pk, self.stranger.pk],
                "from_date": str(self.day),
            },
            **HX,
        )
        self.assertDenied(response)
        self.assertFalse(Roster.objects.filter(is_published=True).exists())

    def test_bulk_publish_works_for_a_report(self):
        self.client.post(
            reverse("roster-employees-publish"),
            {"employee_ids": [self.report.pk], "from_date": str(self.day)},
            **HX,
        )
        self.assertTrue(Roster.objects.get(employee=self.report).is_published)
        self.assertFalse(Roster.objects.get(employee=self.stranger).is_published)

    def test_a_department_publish_only_publishes_the_managers_reports(self):
        self.client.post(
            reverse("roster-publish"),
            {"department": self.department.pk, "from_date": str(self.day)},
            **HX,
        )
        self.assertTrue(Roster.objects.get(employee=self.report).is_published)
        self.assertFalse(Roster.objects.get(employee=self.stranger).is_published)

    def test_the_permission_holder_publishes_the_whole_department(self):
        _grant(self.manager_user, "base.change_roster")
        self.client.post(
            reverse("roster-publish"),
            {"department": self.department.pk, "from_date": str(self.day)},
            **HX,
        )
        self.assertEqual(Roster.objects.filter(is_published=True).count(), 2)
