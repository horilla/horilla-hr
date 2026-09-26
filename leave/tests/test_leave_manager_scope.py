"""Manager-only leave views must check that the manager manages *this* employee.

``manager_can_enter`` and ``is_reportingmanager`` only ask whether the user
manages anybody. The web views trusted that alone, so any line manager could
approve, reject, edit or delete any employee's leave request by id, and read
any request (reason included) and its comments. The API had the same hole,
fixed in GHSA-97wm-28fj-g4pj; these are the web views. The file deleters also
deleted any LeaverequestFile by id, not only the comment's own.

Each attack test is paired with the legitimate manager doing the same thing,
so a fix that denies everyone fails.
"""

import json
from datetime import date, timedelta
from unittest import mock

from django.test import Client, TestCase
from django.urls import NoReverseMatch, reverse

from employee.models import EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user
from leave.models import (
    AvailableLeave,
    LeaveRequest,
    LeaverequestComment,
    LeaverequestFile,
    LeaveType,
)

HX = {"HTTP_HX_REQUEST": "true"}


class LeaveManagerScopeTests(TestCase):
    def setUp(self):
        company = make_company("Scope Co")

        def person(name):
            user = make_user(name, password="secret123")
            emp = make_employee(
                company=company, email=f"{name}@test.horilla", user=user
            )
            return user, emp

        self.owner_user, self.owner = person("scope_owner")
        self.manager_user, self.manager = person("scope_manager")
        # Manages someone else, so manager_can_enter lets them in.
        self.other_manager_user, self.other_manager = person("scope_outsider")
        _unused, self.other_report = person("scope_other_report")
        EmployeeWorkInformation.objects.filter(employee_id=self.owner).update(
            reporting_manager_id=self.manager
        )
        EmployeeWorkInformation.objects.filter(employee_id=self.other_report).update(
            reporting_manager_id=self.other_manager
        )
        self.leave_type = LeaveType.objects.create(name="Scope Leave", total_days=10)
        AvailableLeave.objects.create(
            employee_id=self.owner,
            leave_type_id=self.leave_type,
            available_days=10,
            total_leave_days=10,
        )
        day = date.today() + timedelta(days=7)
        self.leave = LeaveRequest.objects.create(
            employee_id=self.owner,
            leave_type_id=self.leave_type,
            start_date=day,
            end_date=day,
            requested_days=1,
            description="Hospital appointment",
            status="requested",
        )

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def refreshed_status(self):
        return LeaveRequest.objects.get(pk=self.leave.pk).status

    # -- approve ---------------------------------------------------------

    def test_other_manager_cannot_approve(self):
        response = self.client_for(self.other_manager_user).post(
            reverse("request-approve", args=[self.leave.pk]), **HX
        )
        self.assertEqual(self.refreshed_status(), "requested")
        message = json.loads(response["HX-Trigger"])["horillaMessage"]
        self.assertEqual(message["level"], "error")

    def test_other_manager_cannot_approve_from_the_address_bar(self):
        self.client_for(self.other_manager_user).get(
            reverse("request-approve", args=[self.leave.pk])
        )
        self.assertEqual(self.refreshed_status(), "requested")

    def test_own_manager_can_approve(self):
        with mock.patch("leave.views.LeaveMailSendThread"):
            self.client_for(self.manager_user).post(
                reverse("request-approve", args=[self.leave.pk]), **HX
            )
        self.assertEqual(self.refreshed_status(), "approved")

    # -- reject ----------------------------------------------------------

    def test_other_manager_cannot_reject(self):
        self.client_for(self.other_manager_user).post(
            reverse("request-cancel", args=[self.leave.pk]),
            {"reason": "not mine"},
            **HX,
        )
        self.assertEqual(self.refreshed_status(), "requested")

    def test_own_manager_can_reject(self):
        with mock.patch("leave.views.LeaveMailSendThread"):
            self.client_for(self.manager_user).post(
                reverse("request-cancel", args=[self.leave.pk]),
                {"reason": "clash"},
                **HX,
            )
        self.assertEqual(self.refreshed_status(), "rejected")

    # -- edit / delete ---------------------------------------------------

    def test_other_manager_cannot_open_the_edit_form(self):
        url = reverse("request-update", args=[self.leave.pk])
        denied = self.client_for(self.other_manager_user).get(url, **HX)
        self.assertNotIn("Hospital appointment", denied.content.decode())
        allowed = self.client_for(self.manager_user).get(url, **HX)
        self.assertContains(allowed, "Hospital appointment")

    def test_other_manager_cannot_save_the_edit_form(self):
        self.client_for(self.other_manager_user).post(
            reverse("request-update", args=[self.leave.pk]),
            {"description": "edited by an outsider"},
            **HX,
        )
        self.assertEqual(
            LeaveRequest.objects.get(pk=self.leave.pk).description,
            "Hospital appointment",
        )

    def test_other_manager_cannot_delete(self):
        self.client_for(self.other_manager_user).get(
            reverse("request-delete", args=[self.leave.pk]), **HX
        )
        self.assertTrue(LeaveRequest.objects.filter(pk=self.leave.pk).exists())

    def test_own_manager_can_delete(self):
        self.client_for(self.manager_user).get(
            reverse("request-delete", args=[self.leave.pk]), **HX
        )
        self.assertFalse(LeaveRequest.objects.filter(pk=self.leave.pk).exists())

    # -- reading ---------------------------------------------------------

    def test_other_manager_cannot_read_the_request(self):
        url = reverse("user-request-one", args=[self.leave.pk])
        url += f"?instances_ids=[{self.leave.pk}]"
        denied = self.client_for(self.other_manager_user).get(url, **HX)
        self.assertNotContains(denied, "Hospital appointment")
        allowed = self.client_for(self.manager_user).get(url, **HX)
        self.assertContains(allowed, "Hospital appointment")

    def test_other_manager_cannot_read_comments(self):
        LeaverequestComment.objects.create(
            request_id=self.leave, employee_id=self.manager, comment="Needs cover"
        )
        url = reverse("leave-request-view-comment", args=[self.leave.pk])
        denied = self.client_for(self.other_manager_user).get(url, **HX)
        self.assertNotContains(denied, "Needs cover")
        allowed = self.client_for(self.manager_user).get(url, **HX)
        self.assertContains(allowed, "Needs cover")

    # -- comment files ---------------------------------------------------

    def test_file_delete_only_touches_the_comments_own_files(self):
        """The comment's author deleting "their" attachment by id must not be
        able to name another request's file."""
        own = LeaverequestComment.objects.create(
            request_id=self.leave, employee_id=self.owner, comment="mine"
        )
        someone_elses = LeaverequestFile.objects.create(file="leave/other.pdf")
        LeaverequestComment.objects.create(
            request_id=self.leave, employee_id=self.manager, comment="theirs"
        ).files.add(someone_elses)
        self.client_for(self.owner_user).get(
            reverse("delete-leave-comment-file"),
            {
                "ids": [someone_elses.pk],
                "leave_id": self.leave.pk,
                "comment_id": own.pk,
            },
        )
        self.assertTrue(LeaverequestFile.objects.filter(pk=someone_elses.pk).exists())

    def test_compensatory_file_delete_needs_a_comment_you_may_delete(self):
        """It had no check at all: any logged-in user, any file id."""
        try:
            url = reverse("delete-compensatory-comment-file")
        except NoReverseMatch:
            self.skipTest("compensatory leave is switched off")
        attachment = LeaverequestFile.objects.create(file="leave/medical.pdf")
        self.client_for(self.other_manager_user).get(
            url, {"ids": [attachment.pk], "leave_id": 1}
        )
        self.assertTrue(LeaverequestFile.objects.filter(pk=attachment.pk).exists())
