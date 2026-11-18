"""
protected_media must not serve a file just because the requester is signed in.

Before, any authenticated user or JWT holder could read any uploaded file --
a colleague's identity document, a contract, a resume -- straight from its
/media/ URL, although the screens that list those records refuse them. The
file is now served only to someone who may see the record that owns it.
"""

import os
import tempfile
from datetime import date

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from employee.models import EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user
from horilla_documents.models import Document

DOCUMENT_PATH = "horilla_documents/document/document/passport-1a2b3c4d.txt"
CONTRACT_PATH = "payroll/contract/contract_document/contract-1a2b3c4d.txt"
LEAVE_PATH = "leave/leaverequest/attachment/sick-note-1a2b3c4d.txt"
PROFILE_PATH = "employee/employee/employee_profile/face-1a2b3c4d.txt"
POLICY_PATH = "employee/policies/handbook.txt"
ORPHAN_PATH = "horilla_documents/document/document/deleted-9z9z9z9z.txt"
UNOWNED_PATH = "exports/report.txt"


def _write(root, relative, content):
    full = os.path.join(root, *relative.split("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as handle:
        handle.write(content)


def _body(response):
    return b"".join(response.streaming_content)


class ProtectedMediaAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Acme")
        cls.other_company = make_company("Globex")

        def person(username, company):
            user = make_user(username, password="pw-not-real")
            employee = make_employee(
                company=company, email=f"{username}@test.horilla", user=user
            )
            return user, employee

        cls.owner_user, cls.owner = person("owner", cls.company)
        cls.manager_user, cls.manager = person("manager", cls.company)
        cls.peer_user, cls.peer = person("peer", cls.company)
        cls.hr_user, cls.hr = person("hr", cls.company)
        cls.outsider_user, cls.outsider = person("outsider", cls.other_company)
        # An outsider who manages someone in their own company, not the owner.
        cls.report_user, cls.report = person("report", cls.other_company)
        EmployeeWorkInformation.objects.filter(employee_id=cls.report).update(
            reporting_manager_id=cls.outsider
        )
        EmployeeWorkInformation.objects.filter(employee_id=cls.owner).update(
            reporting_manager_id=cls.manager
        )

        cls.hr_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="horilla_documents", codename="view_document"
            )
        )
        cls.superuser = make_user("root", password="pw-not-real", is_superuser=True)
        make_employee(
            company=cls.company, email="root@test.horilla", user=cls.superuser
        )

        cls.document = Document.objects.create(
            title="Passport", employee_id=cls.owner, document=DOCUMENT_PATH
        )

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        for path, body in (
            (DOCUMENT_PATH, "passport-number"),
            (CONTRACT_PATH, "salary-details"),
            (LEAVE_PATH, "medical-details"),
            (PROFILE_PATH, "avatar"),
            (POLICY_PATH, "company-handbook"),
            (ORPHAN_PATH, "orphan"),
            (UNOWNED_PATH, "public-export"),
        ):
            _write(self.media_root, path, body)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

    def get(self, user, path):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)
        return self.client.get(f"/media/{path}")

    def assert_served(self, user, path, body):
        response = self.get(user, path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_body(response), body.encode())

    def assert_denied(self, user, path, secret):
        response = self.get(user, path)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(secret.encode(), response.content)

    # -- the reported case: employee documents --------------------------

    def test_document_owner_and_manager_and_permission_holder_can_read(self):
        for user in (self.owner_user, self.manager_user, self.hr_user, self.superuser):
            with self.subTest(user=user.username):
                self.assert_served(user, DOCUMENT_PATH, "passport-number")

    def test_colleague_in_the_same_company_is_refused(self):
        self.assert_denied(self.peer_user, DOCUMENT_PATH, "passport-number")

    def test_user_and_manager_from_another_company_are_refused(self):
        for user in (self.outsider_user, self.report_user):
            with self.subTest(user=user.username):
                self.assert_denied(user, DOCUMENT_PATH, "passport-number")

    def test_a_bare_jwt_for_another_user_is_refused(self):
        token = str(AccessToken.for_user(self.peer_user))
        response = self.client.get(
            f"/media/{DOCUMENT_PATH}", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"passport-number", response.content)

    def test_a_jwt_for_the_owner_is_served(self):
        token = str(AccessToken.for_user(self.owner_user))
        response = self.client.get(
            f"/media/{DOCUMENT_PATH}", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_body(response), b"passport-number")

    def test_anonymous_request_is_still_redirected_to_login(self):
        response = self.get(None, DOCUMENT_PATH)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    # -- other record types ---------------------------------------------

    def test_contract_document_follows_its_employee(self):
        from payroll.models.models import Contract

        Contract.objects.create(
            contract_name="Owner contract",
            employee_id=self.owner,
            contract_start_date=date(2026, 1, 1),
            wage=1000,
            contract_document=CONTRACT_PATH,
        )
        self.assert_served(self.owner_user, CONTRACT_PATH, "salary-details")
        self.assert_served(self.manager_user, CONTRACT_PATH, "salary-details")
        self.assert_denied(self.peer_user, CONTRACT_PATH, "salary-details")
        self.assert_denied(self.outsider_user, CONTRACT_PATH, "salary-details")

    def test_leave_attachment_follows_its_employee(self):
        from horilla.testkit.factories import make_leave_request, make_leave_type

        leave = make_leave_request(
            employee=self.owner,
            leave_type=make_leave_type(),
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 5),
        )
        type(leave).objects.filter(pk=leave.pk).update(attachment=LEAVE_PATH)
        self.assert_served(self.owner_user, LEAVE_PATH, "medical-details")
        self.assert_served(self.manager_user, LEAVE_PATH, "medical-details")
        self.assert_denied(self.peer_user, LEAVE_PATH, "medical-details")

    # -- what must keep working -----------------------------------------

    def test_profile_pictures_stay_visible_to_every_signed_in_user(self):
        for user in (self.peer_user, self.outsider_user):
            with self.subTest(user=user.username):
                self.assert_served(user, PROFILE_PATH, "avatar")

    def test_company_policy_files_stay_visible_to_every_signed_in_user(self):
        self.assert_served(self.peer_user, POLICY_PATH, "company-handbook")

    def test_files_outside_any_model_upload_directory_are_unchanged(self):
        self.assert_served(self.peer_user, UNOWNED_PATH, "public-export")

    # -- deny by default -------------------------------------------------

    def test_file_under_a_model_directory_with_no_owner_is_refused(self):
        self.assert_denied(self.peer_user, ORPHAN_PATH, "orphan")
        self.assert_denied(self.hr_user, ORPHAN_PATH, "orphan")

    def test_superuser_can_still_read_an_orphan(self):
        self.assert_served(self.superuser, ORPHAN_PATH, "orphan")
