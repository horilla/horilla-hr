"""
Function views and the API that name an employee in the request.

Same rule as the class-based forms: ``manager_can_enter`` (and its API twin)
admit anyone who manages anybody, so the employee named in the request must be
checked on its own. A reporting manager may act for their own report, never for
a stranger; the holder of the permission may act for anyone.
"""

from datetime import date

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from base.models import RotatingShift
from employee.models import Employee, EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user

HX = {"HTTP_HX_REQUEST": "true"}
DENIED = "decorator_404.html"


def _grant(user, dotted):
    app_label, codename = dotted.split(".")
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )


class FunctionScopeBase(TestCase):
    def setUp(self):
        self.client.raise_request_exception = False
        company = make_company("Function Scope Co")
        self.manager_user = make_user("fnmanager")
        self.manager = make_employee(
            company=company, email="fnmanager@test.horilla", user=self.manager_user
        )
        self.report = make_employee(company=company, email="fnreport@test.horilla")
        self.stranger = make_employee(company=company, email="fnstranger@test.horilla")
        EmployeeWorkInformation.objects.filter(employee_id=self.report).update(
            reporting_manager_id=self.manager
        )
        Employee.objects.filter(pk=self.report.pk).update(badge_id="B-REPORT")
        Employee.objects.filter(pk=self.stranger.pk).update(badge_id="B-STRANGER")
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


class LeaveAssignScopeTests(FunctionScopeBase):
    def _post(self, url, employee, **extra):
        data = {"employee_id": [employee.pk], "leave_type_id": ["999999"], **extra}
        return self.client.post(url, data, **HX)

    def test_assign_refuses_a_stranger_and_allows_a_report(self):
        url = reverse("assign")
        self.assertDenied(self._post(url, self.stranger))
        self.assertAllowed(self._post(url, self.report))

    def test_assign_allows_anyone_for_the_permission_holder(self):
        _grant(self.manager_user, "leave.add_availableleave")
        self.assertAllowed(self._post(reverse("assign"), self.stranger))

    def test_assign_refuses_a_stranger_slipped_in_beside_a_report(self):
        response = self.client.post(
            reverse("assign"),
            {"employee_id": [self.report.pk, self.stranger.pk], "leave_type_id": ["1"]},
            **HX,
        )
        self.assertDenied(response)

    def test_the_live_assign_one_form_is_scoped(self):
        _grant(self.manager_user, "leave.view_leavetype")
        url = reverse("assign-one", kwargs={"pk": 999999})
        self.assertDenied(self._post(url, self.stranger))
        self.assertAllowed(self._post(url, self.report))

    def test_the_live_assign_one_form_allows_anyone_for_the_permission_holder(self):
        _grant(self.manager_user, "leave.view_leavetype")
        _grant(self.manager_user, "leave.add_availableleave")
        url = reverse("assign-one", kwargs={"pk": 999999})
        self.assertAllowed(self._post(url, self.stranger))


class RotatingShiftImportScopeTests(FunctionScopeBase):
    def _upload(self, badge):
        csv = (
            "Badge Id,Name,Title,2030-01-01,Day,Night\n"
            f"{badge},Someone,Imported Pattern,x,Day,Night\n"
        )
        upload = SimpleUploadedFile("import.csv", csv.encode(), content_type="text/csv")
        return self.client.post(
            reverse("rotating-shift-assign-info-import"), {"file": upload}, **HX
        )

    def test_an_import_naming_a_stranger_is_refused_before_anything_is_created(self):
        before = RotatingShift.objects.count()
        self.assertDenied(self._upload("B-STRANGER"))
        self.assertEqual(RotatingShift.objects.count(), before)

    def test_an_import_naming_only_reports_gets_past_the_check(self):
        self.assertAllowed(self._upload("B-REPORT"))

    def test_one_stranger_among_reports_refuses_the_whole_import(self):
        csv = (
            "Badge Id,Name,Title,2030-01-01,Day,Night\n"
            "B-REPORT,A,Pattern A,x,Day,Night\n"
            "B-STRANGER,B,Pattern B,x,Day,Night\n"
        )
        upload = SimpleUploadedFile("import.csv", csv.encode(), content_type="text/csv")
        before = RotatingShift.objects.count()
        response = self.client.post(
            reverse("rotating-shift-assign-info-import"), {"file": upload}, **HX
        )
        self.assertDenied(response)
        self.assertEqual(RotatingShift.objects.count(), before)


class MonthlySummaryScopeTests(FunctionScopeBase):
    def _params(self, employee):
        return {"employee_id": employee.pk, "date": "2026-01-05"}

    def test_conflict_resolve_is_scoped(self):
        url = reverse("attendance-monthly-summary-conflict-resolve")
        self.assertDenied(self.client.get(url, self._params(self.stranger), **HX))
        self.assertAllowed(self.client.get(url, self._params(self.report), **HX))

    def test_conflict_bulk_resolve_is_scoped(self):
        url = reverse("attendance-monthly-summary-conflict-bulk-resolve")
        params = {"employee_id": self.stranger.pk, "dates": ["2026-01-05"]}
        self.assertDenied(self.client.get(url, params, **HX))
        params["employee_id"] = self.report.pk
        self.assertAllowed(self.client.get(url, params, **HX))

    def test_daily_hours_edit_is_scoped(self):
        url = reverse("attendance-monthly-summary-daily-hours-edit")
        self.assertDenied(self.client.get(url, self._params(self.stranger), **HX))
        self.assertAllowed(self.client.get(url, self._params(self.report), **HX))

    def test_bulk_override_refuses_a_stranger_with_a_403(self):
        url = reverse("attendance-monthly-summary-bulk-override")
        data = {
            "employee_ids": [self.stranger.pk],
            "from_date": "2026-01-05",
            "to_date": "2026-01-06",
            "resolution": "full_present",
        }
        response = self.client.post(url, data, **HX)
        self.assertEqual(response.status_code, 403)

    def test_bulk_override_refuses_a_stranger_slipped_in_beside_a_report(self):
        url = reverse("attendance-monthly-summary-bulk-override")
        data = {
            "employee_ids": [self.report.pk, self.stranger.pk],
            "from_date": "2026-01-05",
            "to_date": "2026-01-06",
            "resolution": "full_present",
        }
        self.assertEqual(self.client.post(url, data, **HX).status_code, 403)

    def test_bulk_override_gets_past_the_check_for_a_report(self):
        url = reverse("attendance-monthly-summary-bulk-override")
        data = {
            "employee_ids": [self.report.pk],
            "from_date": "2026-01-05",
            "to_date": "2026-01-06",
            "resolution": "full_present",
        }
        self.assertNotEqual(self.client.post(url, data, **HX).status_code, 403)

    def test_the_change_permission_allows_anyone(self):
        _grant(self.manager_user, "attendance.change_attendance")
        url = reverse("attendance-monthly-summary-bulk-override")
        data = {
            "employee_ids": [self.stranger.pk],
            "from_date": "2026-01-05",
            "to_date": "2026-01-06",
            "resolution": "full_present",
        }
        self.assertNotEqual(self.client.post(url, data, **HX).status_code, 403)


class EmployeeRecordScopeTests(FunctionScopeBase):
    def test_personal_info_of_a_stranger_cannot_be_changed(self):
        url = reverse(
            "employee-update-personal-info", kwargs={"obj_id": self.stranger.pk}
        )
        self.assertDenied(self.client.post(url, {"badge_id": "HACKED"}, **HX))
        self.stranger.refresh_from_db()
        self.assertEqual(self.stranger.badge_id, "B-STRANGER")

    def test_personal_info_of_a_report_and_of_oneself_gets_past_the_check(self):
        for employee in (self.report, self.manager):
            with self.subTest(employee=employee.pk):
                url = reverse(
                    "employee-update-personal-info", kwargs={"obj_id": employee.pk}
                )
                self.assertAllowed(self.client.post(url, {}, **HX))

    def test_creating_an_employee_needs_the_add_permission(self):
        url = reverse("employee-create-personal-info")
        before = Employee.objects.count()
        self.assertDenied(self.client.post(url, {"badge_id": "NEW1"}, **HX))
        self.assertEqual(Employee.objects.count(), before)

    def test_the_add_permission_gets_creation_past_the_check(self):
        _grant(self.manager_user, "employee.add_employee")
        url = reverse("employee-create-personal-info")
        self.assertAllowed(self.client.post(url, {}, **HX))

    def test_bank_details_of_a_stranger_cannot_be_created(self):
        url = reverse(
            "employee-bank-details-view-create", kwargs={"obj_id": self.stranger.pk}
        )
        self.assertDenied(self.client.post(url, {}, **HX))

    def test_bank_details_of_a_report_or_oneself_get_past_the_check(self):
        for employee in (self.report, self.manager):
            with self.subTest(employee=employee.pk):
                url = reverse(
                    "employee-bank-details-view-create", kwargs={"obj_id": employee.pk}
                )
                self.assertAllowed(self.client.post(url, {}, **HX))

    def test_a_note_cannot_be_added_to_a_stranger(self):
        url = reverse("add-employee-note", kwargs={"emp_id": self.stranger.pk})
        self.assertDenied(self.client.post(url, {}, **HX))
        self.assertAllowed(
            self.client.post(
                reverse("add-employee-note", kwargs={"emp_id": self.report.pk}),
                {},
                **HX,
            )
        )


class ApiLeaveRequestScopeTests(FunctionScopeBase):
    def _post(self, employee):
        api = APIClient()
        api.force_authenticate(user=self.manager_user)
        return api.post(
            "/api/v1/leave/request/",
            {
                "employee_id": employee.pk,
                "leave_type_id": 999999,
                "start_date": str(date(2027, 3, 1)),
                "end_date": str(date(2027, 3, 1)),
            },
            format="json",
        )

    def test_a_manager_cannot_file_leave_for_a_stranger(self):
        self.assertEqual(self._post(self.stranger).status_code, 403)

    def test_a_manager_can_file_for_a_report_and_for_themselves(self):
        for employee in (self.report, self.manager):
            with self.subTest(employee=employee.pk):
                self.assertNotEqual(self._post(employee).status_code, 403)

    def test_the_permission_holder_can_file_for_anyone(self):
        _grant(self.manager_user, "leave.add_leaverequest")
        self.assertNotEqual(self._post(self.stranger).status_code, 403)
