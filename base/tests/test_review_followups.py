"""
Gaps found in the pre-release review, next to the routes the advisory listed.

The same rule as the rest of the release applies: ``manager_can_enter`` admits
anyone who manages anybody, so each route now checks the employee the record
belongs to. A manager may act for their own reports, never for a stranger.
"""

import io
from datetime import date, timedelta

import openpyxl
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from base.models import Department, EmployeeShift, Roster
from employee.models import (
    Employee,
    EmployeeBankDetails,
    EmployeeNote,
    EmployeeWorkInformation,
    NoteFiles,
)
from horilla.testkit import make_company, make_employee, make_user
from leave.models import (
    LeaveAllocationRequest,
    LeaveallocationrequestComment,
    LeaveRequest,
    LeaveRequestConditionApproval,
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
        self.company = make_company("Followup Co")
        self.manager_user = make_user("fumanager")
        self.manager = make_employee(
            company=self.company, email="fumanager@test.horilla", user=self.manager_user
        )
        self.report = make_employee(company=self.company, email="fureport@test.horilla")
        self.stranger = make_employee(
            company=self.company, email="fustranger@test.horilla"
        )
        self._manage(self.manager, self.report)
        self.client.force_login(self.manager_user)

    @staticmethod
    def _manage(manager, employee):
        EmployeeWorkInformation.objects.filter(employee_id=employee).update(
            reporting_manager_id=manager
        )

    def assertDenied(self, response):
        names = [t.name for t in response.templates]
        self.assertTrue(
            response.status_code in (302, 403) or DENIED in names,
            f"expected a refusal, got {response.status_code} {names}",
        )

    def assertAllowed(self, response):
        names = [t.name for t in response.templates]
        self.assertNotEqual(response.status_code, 403)
        self.assertNotIn(DENIED, names)


class BankDetailsUpdateTests(Base):
    def _bank(self, employee, number="111"):
        return EmployeeBankDetails.objects.create(
            employee_id=employee, account_number=number, bank_name="Bank"
        )

    def test_a_strangers_account_number_cannot_be_overwritten(self):
        bank = self._bank(self.stranger)
        for url in (
            reverse("employee-bank-details-view-update", kwargs={"obj_id": bank.pk}),
            reverse(
                "employee-update-bank-details", kwargs={"obj_id": self.stranger.pk}
            ),
        ):
            with self.subTest(url=url):
                response = self.client.post(
                    url, {"account_number": "999", "bank_name": "X"}, **HX
                )
                self.assertDenied(response)
                bank.refresh_from_db()
                self.assertEqual(bank.account_number, "111")

    def test_a_report_and_oneself_get_past_the_check(self):
        for employee in (self.report, self.manager):
            with self.subTest(employee=employee.pk):
                bank = self._bank(employee, number=f"5{employee.pk}")
                url = reverse(
                    "employee-bank-details-view-update", kwargs={"obj_id": bank.pk}
                )
                self.assertAllowed(self.client.post(url, {}, **HX))


class WorkInfoTests(Base):
    def test_a_strangers_work_info_cannot_be_changed(self):
        work = EmployeeWorkInformation.objects.get(employee_id=self.stranger)
        for url in (
            reverse("employee-update-work-info", kwargs={"obj_id": self.stranger.pk}),
            reverse("employee-work-info-view-update", kwargs={"obj_id": work.pk}),
            reverse(
                "employee-work-info-view-create", kwargs={"obj_id": self.stranger.pk}
            ),
        ):
            with self.subTest(url=url):
                self.assertDenied(self.client.post(url, {}, **HX))

    def test_a_reports_work_info_gets_past_the_check(self):
        work = EmployeeWorkInformation.objects.get(employee_id=self.report)
        url = reverse("employee-work-info-view-update", kwargs={"obj_id": work.pk})
        self.assertAllowed(self.client.post(url, {}, **HX))

    def test_nobody_changes_their_own_work_info_without_the_permission(self):
        """It holds the reporting manager and pay."""
        work = EmployeeWorkInformation.objects.get(employee_id=self.manager)
        url = reverse("employee-work-info-view-update", kwargs={"obj_id": work.pk})
        self.assertDenied(self.client.post(url, {}, **HX))


class EmployeeEditPageTests(Base):
    def test_a_strangers_edit_page_is_refused(self):
        url = reverse("employee-view-update", kwargs={"obj_id": self.stranger.pk})
        self.assertDenied(self.client.get(url, **HX))

    def test_a_reports_edit_page_opens(self):
        url = reverse("employee-view-update", kwargs={"obj_id": self.report.pk})
        self.assertAllowed(self.client.get(url, **HX))


class NoteTests(Base):
    def _note(self, employee):
        return EmployeeNote.objects.create(
            employee_id=employee, description="n", updated_by=self.manager
        )

    def test_notes_on_a_stranger_cannot_be_changed_or_deleted(self):
        note = self._note(self.stranger)
        file = NoteFiles.objects.create()
        note.note_files.add(file)
        for method, url in (
            ("post", reverse("employee-note-update", kwargs={"note_id": note.pk})),
            ("post", reverse("add-more-files-employee", kwargs={"note_id": note.pk})),
            (
                "post",
                reverse("delete-employee-note-file", kwargs={"note_file_id": file.pk}),
            ),
            ("post", reverse("employee-note-delete", kwargs={"note_id": note.pk})),
        ):
            with self.subTest(url=url):
                self.assertDenied(getattr(self.client, method)(url, {}, **HX))
        self.assertTrue(EmployeeNote.objects.filter(pk=note.pk).exists())
        self.assertTrue(NoteFiles.objects.filter(pk=file.pk).exists())

    def test_a_note_on_a_report_can_be_deleted(self):
        note = self._note(self.report)
        self.client.post(
            reverse("employee-note-delete", kwargs={"note_id": note.pk}), {}, **HX
        )
        self.assertFalse(EmployeeNote.objects.filter(pk=note.pk).exists())


class AllocationCommentTests(Base):
    def _request(self, employee):
        return LeaveAllocationRequest.objects.create(
            employee_id=employee,
            leave_type_id=LeaveType.objects.create(name="Annual", payment="paid"),
            requested_days=1,
            description="x",
        )

    def test_a_stranger_cannot_comment_on_someone_elses_allocation_request(self):
        request = self._request(self.stranger)
        url = reverse("allocation-request-add-comment", kwargs={"leave_id": request.pk})
        response = self.client.post(url, {"comment": "hi"}, **HX)
        self.assertDenied(response)
        self.assertFalse(LeaveallocationrequestComment.objects.exists())

    def test_the_owner_and_their_manager_can_open_the_form(self):
        for employee in (self.report, self.manager):
            with self.subTest(employee=employee.pk):
                request = self._request(employee)
                url = reverse(
                    "allocation-request-add-comment", kwargs={"leave_id": request.pk}
                )
                self.assertAllowed(self.client.get(url, **HX))


class MonthlySummaryReadTests(Base):
    def setUp(self):
        super().setUp()
        self.plain_user = make_user("fuplain")
        self.plain = make_employee(
            company=self.company, email="fuplain@test.horilla", user=self.plain_user
        )
        self.client.force_login(self.plain_user)

    def test_someone_elses_attendance_is_refused(self):
        for name in (
            "attendance-monthly-summary-detail",
            "attendance-monthly-summary-calendar",
        ):
            with self.subTest(view=name):
                response = self.client.get(
                    reverse(name),
                    {"employee_id": self.stranger.pk, "date": "2026-01-05"},
                    **HX,
                )
                self.assertDenied(response)

    def test_ones_own_attendance_opens(self):
        for name in (
            "attendance-monthly-summary-detail",
            "attendance-monthly-summary-calendar",
        ):
            with self.subTest(view=name):
                response = self.client.get(
                    reverse(name),
                    {"employee_id": self.plain.pk, "date": "2026-01-05"},
                    **HX,
                )
                self.assertAllowed(response)


class RosterTemplateTests(Base):
    def test_the_template_lists_only_the_managers_reports(self):
        Department.objects.create(department="Planning")
        response = self.client.get(reverse("roster-template-download"))
        book = openpyxl.load_workbook(io.BytesIO(response.content))
        listed = {
            str(cell.value)
            for sheet in book.worksheets
            for row in sheet.iter_rows()
            for cell in row
            if cell.value is not None
        }
        self.assertIn(str(self.report.pk), listed)
        self.assertNotIn(str(self.stranger.pk), listed)


class RotatingImportNestedTests(Base):
    @override_settings(NESTED_SUBORDINATE_VISIBILITY=True)
    def test_a_report_of_a_report_is_in_scope(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        grandchild = make_employee(company=self.company, email="fugrand@test.horilla")
        self._manage(self.report, grandchild)
        Employee.objects.filter(pk=grandchild.pk).update(badge_id="B-GRAND")
        csv = (
            "Badge Id,Name,Title,2030-01-01,Day,Night\nB-GRAND,G,Pattern,x,Day,Night\n"
        )
        upload = SimpleUploadedFile("i.csv", csv.encode(), content_type="text/csv")
        response = self.client.post(
            reverse("rotating-shift-assign-info-import"), {"file": upload}, **HX
        )
        self.assertAllowed(response)


class LoginToggleNoAccountTests(Base):
    def test_an_employee_without_a_login_is_refused_not_an_error(self):
        response = self.client.post(
            reverse("toggle-user-dashboard-access") + f"?instance_id={self.report.pk}",
            **HX,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.status_code, 500)


class ApiBodyShapeTests(Base):
    def test_a_list_body_is_refused_not_an_error(self):
        api = APIClient()
        api.force_authenticate(user=self.manager_user)
        response = api.post("/api/v1/leave/request/", [1, 2], format="json")
        self.assertIn(response.status_code, (400, 403))


class LeaveRequestApproverTests(Base):
    def _leave(self, employee):
        return LeaveRequest.objects.create(
            employee_id=employee,
            leave_type_id=LeaveType.objects.create(name="Casual", payment="paid"),
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=10),
            requested_days=1,
            description="x",
        )

    def test_a_nominated_approver_can_open_the_edit_form(self):
        """Approvers named by a multiple-approval condition are let in by the view."""
        leave = self._leave(self.stranger)
        LeaveRequestConditionApproval.objects.create(
            sequence=1, leave_request_id=leave, manager_id=self.manager
        )
        url = reverse("request-update", kwargs={"pk": leave.pk})
        self.assertAllowed(self.client.get(url, **HX))

    def test_a_manager_who_is_not_an_approver_is_still_refused(self):
        leave = self._leave(self.stranger)
        url = reverse("request-update", kwargs={"pk": leave.pk})
        self.assertDenied(self.client.get(url, **HX))

    def test_an_approver_cannot_move_the_request_to_someone_outside_their_team(self):
        leave = self._leave(self.stranger)
        LeaveRequestConditionApproval.objects.create(
            sequence=1, leave_request_id=leave, manager_id=self.manager
        )
        other = make_employee(company=self.company, email="fuother@test.horilla")
        url = reverse("request-update", kwargs={"pk": leave.pk})
        response = self.client.post(url, {"employee_id": [other.pk]}, **HX)
        self.assertDenied(response)
