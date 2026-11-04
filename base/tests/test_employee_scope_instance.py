"""
Editing an existing record is checked against the employee it belongs to.

The update routes take the record from the URL and used to open it for any
signed-in user (or, behind ``manager_can_enter``, any manager of anybody). The
record's own employee must be one the caller may act on.
"""

from datetime import date

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from attendance.models import AttendanceOverTime
from base.models import WorkType, WorkTypeRequest
from employee.models import EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user

HX = {"HTTP_HX_REQUEST": "true"}
DENIED = "decorator_404.html"


class UpdateByIdScopeTests(TestCase):
    def setUp(self):
        self.client.raise_request_exception = False
        company = make_company("Instance Co")
        self.manager_user = make_user("instmanager")
        self.manager = make_employee(
            company=company, email="instmanager@test.horilla", user=self.manager_user
        )
        self.owner = make_employee(company=company, email="owner@test.horilla")
        self.stranger = make_employee(company=company, email="stranger@test.horilla")
        EmployeeWorkInformation.objects.filter(employee_id=self.owner).update(
            reporting_manager_id=self.manager
        )
        # A second employee the manager manages, so manager_can_enter admits them.
        self.other_report = make_employee(company=company, email="report@test.horilla")
        EmployeeWorkInformation.objects.filter(employee_id=self.other_report).update(
            reporting_manager_id=self.manager
        )
        self.client.force_login(self.manager_user)

    def _grant(self, dotted):
        app_label, codename = dotted.split(".")
        self.manager_user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )

    def _overtime(self, employee):
        return AttendanceOverTime.objects.create(
            employee_id=employee, month="january", year="2026"
        )

    def _work_type_request(self, employee):
        work_type = WorkType.objects.create(work_type="Remote")
        return WorkTypeRequest.objects.create(
            employee_id=employee,
            work_type_id=work_type,
            requested_date=date(2027, 1, 1),
            requested_till=date(2027, 1, 2),
            description="probe",
        )

    def test_overtime_of_someone_who_is_not_a_report_is_refused(self):
        record = self._overtime(self.stranger)
        url = reverse("attendance-overtime-update", kwargs={"pk": record.pk})
        self.assertTemplateUsed(self.client.get(url, **HX), DENIED)

    def test_overtime_of_a_report_is_opened_for_their_manager(self):
        record = self._overtime(self.owner)
        url = reverse("attendance-overtime-update", kwargs={"pk": record.pk})
        self.assertTemplateNotUsed(self.client.get(url, **HX), DENIED)

    def test_overtime_update_by_a_non_report_manager_does_not_write(self):
        record = self._overtime(self.stranger)
        url = reverse("attendance-overtime-update", kwargs={"pk": record.pk})
        self.client.post(url, {"employee_id": [self.owner.pk], "month": "march"}, **HX)
        record.refresh_from_db()
        self.assertEqual(record.employee_id_id, self.stranger.pk)
        self.assertEqual(record.month, "january")

    def test_the_change_permission_opens_any_overtime_record(self):
        record = self._overtime(self.stranger)
        self._grant("attendance.change_attendanceovertime")
        url = reverse("attendance-overtime-update", kwargs={"pk": record.pk})
        self.assertTemplateNotUsed(self.client.get(url, **HX), DENIED)

    def test_someone_elses_work_type_request_is_refused(self):
        request = self._work_type_request(self.stranger)
        url = reverse("work-type-request-update", kwargs={"pk": request.pk})
        self.assertTemplateUsed(self.client.get(url, **HX), DENIED)

    def test_a_reports_work_type_request_is_opened_for_their_manager(self):
        request = self._work_type_request(self.owner)
        url = reverse("work-type-request-update", kwargs={"pk": request.pk})
        self.assertTemplateNotUsed(self.client.get(url, **HX), DENIED)

    def test_the_requester_may_open_their_own_work_type_request(self):
        request = self._work_type_request(self.manager)
        url = reverse("work-type-request-update", kwargs={"pk": request.pk})
        self.assertTemplateNotUsed(self.client.get(url, **HX), DENIED)

    def test_duplicating_someone_elses_work_type_request_is_refused(self):
        request = self._work_type_request(self.stranger)
        url = reverse("work-type-request-duplicate", kwargs={"pk": request.pk})
        self.assertTemplateUsed(self.client.get(url, **HX), DENIED)
