"""
GHSA-23vp-5g5x-mh2x: three /api/attendance/ mail endpoints took the target
``employee_id`` from the request body and were guarded only by
``manager_permission_required``, whose check is "does this caller manage
*anyone at all*" -- never whether they manage the employee_id in the body.
Any low-privileged reporting manager could act against any employee in the
company:

- ``ConvertedMailTemplateConvert.put`` rendered a mail template with that
  employee's data and returned the rendered text (PII disclosure: name,
  personal email, phone, address, ...).
- ``OfflineEmployeeMailsend.post`` sent attacker-controlled HTML, from the
  company's own SMTP identity, to that employee's address.

Both are now gated by ``manager_or_owner_permission_required(Employee, ...)``,
the same instance-scoped decorator GHSA-39gq-9wwx-p8hx introduced for
EmployeeBankDetails: the owner, someone holding the permission directly, or
the reporting manager *of the specific employee named in the body*.

``MailTemplateView.get`` (advisory item 2: any manager could enumerate every
company mail template) now requires ``base.view_horillamailtemplate`` -- the
same permission the web list view uses -- instead of "manages anyone".
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

from base.models import HorillaMailTemplate
from horilla.testkit import make_company, make_employee, make_user

CONVERT_URL = "/api/attendance/converted-mail-template"
MAIL_TEMPLATES_URL = "/api/attendance/mail-templates"


class ConvertedMailTemplateAuthorizationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        company = make_company("Mail Co")

        # attacker manages exactly one, unrelated, person -- the bar the old
        # check required and nothing more.
        self.attacker_user = make_user("mail_attacker", password="secret123")
        self.attacker = make_employee(
            company=company, email="mail_attacker@test.horilla", user=self.attacker_user
        )
        managed_user = make_user("mail_attacker_report", password="secret123")
        make_employee(
            company=company,
            email="mail_attacker_report@test.horilla",
            user=managed_user,
        )
        self._set_manager(managed_user, self.attacker)

        self.target_user = make_user("mail_target", password="secret123")
        self.target = make_employee(
            company=company, email="mail_target@test.horilla", user=self.target_user
        )

        self.manager_user = make_user("mail_manager", password="secret123")
        self.manager = make_employee(
            company=company, email="mail_manager@test.horilla", user=self.manager_user
        )
        self._set_manager(self.target_user, self.manager)

        self.template = HorillaMailTemplate.objects.create(
            title="Converted mail template authz test",
            body="Hello {{ instance.get_full_name }}",
        )

    def _set_manager(self, user, manager_employee):
        from employee.models import EmployeeWorkInformation

        EmployeeWorkInformation.objects.filter(employee_id=user.employee_get).update(
            reporting_manager_id=manager_employee
        )

    def _auth(self, user):
        self.client.force_authenticate(user=type(user).objects.get(pk=user.pk))

    def _convert(self):
        return self.client.put(
            CONVERT_URL,
            {"template_id": self.template.pk, "employee_id": self.target.pk},
        )

    def test_a_manager_of_someone_else_cannot_read_an_unrelated_employees_data(self):
        """The reported attack: manages one person, targets another."""
        self._auth(self.attacker_user)
        response = self._convert()
        self.assertEqual(response.status_code, 403)

    def test_the_employees_actual_manager_can_convert_the_template(self):
        self._auth(self.manager_user)
        response = self._convert()
        self.assertEqual(response.status_code, 200)

    def test_the_employee_themself_can_convert_their_own_template(self):
        self._auth(self.target_user)
        response = self._convert()
        self.assertEqual(response.status_code, 200)


class OfflineEmployeeMailsendAuthorizationTests(TestCase):
    SEND_URL = "/api/attendance/offline-employee-mail-send"

    def setUp(self):
        self.client = APIClient()
        company = make_company("Mail Co 2")

        self.attacker_user = make_user("mailsend_attacker", password="secret123")
        self.attacker = make_employee(
            company=company,
            email="mailsend_attacker@test.horilla",
            user=self.attacker_user,
        )
        managed_user = make_user("mailsend_attacker_report", password="secret123")
        make_employee(
            company=company,
            email="mailsend_attacker_report@test.horilla",
            user=managed_user,
        )
        from employee.models import EmployeeWorkInformation

        EmployeeWorkInformation.objects.filter(
            employee_id=managed_user.employee_get
        ).update(reporting_manager_id=self.attacker)

        self.target_user = make_user("mailsend_target", password="secret123")
        self.target = make_employee(
            company=company, email="mailsend_target@test.horilla", user=self.target_user
        )

    def _auth(self, user):
        self.client.force_authenticate(user=type(user).objects.get(pk=user.pk))

    def test_a_manager_of_someone_else_cannot_email_an_unrelated_employee(self):
        """
        The reported attack: send attacker-controlled HTML, from the
        company's own SMTP identity, to an employee the caller doesn't
        manage. Must be refused before any mail is composed.
        """
        self._auth(self.attacker_user)
        response = self.client.post(
            self.SEND_URL,
            {
                "employee_id": self.target.pk,
                "subject": "phish",
                "body": "<img src=x onerror=alert(1)>",
            },
        )
        self.assertEqual(response.status_code, 403)


class MailTemplateListAuthorizationTests(TestCase):
    """
    Advisory item 2: MailTemplateView.get listed every company mail template
    to any reporting manager. It now requires base.view_horillamailtemplate,
    matching the web list view -- managing someone is no longer enough.
    """

    def setUp(self):
        self.client = APIClient()
        company = make_company("Mail Co 3")

        # A reporting manager who does NOT hold view_horillamailtemplate.
        self.manager_user = make_user("mt_manager", password="secret123")
        self.manager = make_employee(
            company=company, email="mt_manager@test.horilla", user=self.manager_user
        )
        report_user = make_user("mt_report", password="secret123")
        make_employee(company=company, email="mt_report@test.horilla", user=report_user)
        from employee.models import EmployeeWorkInformation

        EmployeeWorkInformation.objects.filter(
            employee_id=report_user.employee_get
        ).update(reporting_manager_id=self.manager)

        HorillaMailTemplate.objects.create(
            title="Secret Template", body="internal", company_id=company
        )

    def _auth(self, user):
        self.client.force_authenticate(user=type(user).objects.get(pk=user.pk))

    def test_a_manager_without_the_permission_cannot_list_templates(self):
        self._auth(self.manager_user)
        response = self.client.get(MAIL_TEMPLATES_URL)
        # 403: authenticated, but lacks base.view_horillamailtemplate. (Being
        # a reporting manager is no longer sufficient -- that was the bug.)
        self.assertEqual(response.status_code, 403)

    def test_the_permission_holder_can_list_templates(self):
        self.manager_user.user_permissions.add(
            Permission.objects.get(codename="view_horillamailtemplate")
        )
        self._auth(self.manager_user)
        response = self.client.get(MAIL_TEMPLATES_URL)
        self.assertEqual(response.status_code, 200)
