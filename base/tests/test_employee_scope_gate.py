"""
A form that names an employee must not act on one the caller may not.

The employee dropdown on these forms was narrowed to the caller's reports only
when the form was rendered, and a submitted ``employee_id`` was never checked.
``manager_can_enter`` admits anyone who manages anybody, so a manager of one
person could write for every employee. EmployeeScopeMixin checks the submitted
ids before the form is bound.

For every protected view: a reporting manager is refused for an employee who is
not their report, and allowed for their own report; a holder of the add
permission is allowed for anyone; and the caller themselves is allowed exactly
where the form's own dropdown offers them.
"""

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from employee.models import EmployeeWorkInformation
from horilla.testkit import make_company, make_employee, make_user

HX = {"HTTP_HX_REQUEST": "true"}
DENIED = "decorator_404.html"

# (label, url name, url kwargs, "app.codename" that allows anyone, caller may name themselves)
VIEWS = [
    (
        "leave allocation request",
        "leave-allocation-request-create",
        {},
        "leave.add_leaveallocationrequest",
        True,
    ),
    ("work type request", "work-type-request", {}, "base.add_worktyperequest", True),
    (
        "work type request duplicate",
        "work-type-request-duplicate",
        {"pk": 999999},
        "base.add_worktyperequest",
        True,
    ),
    ("shift request", "shift-request", {}, "base.add_shiftrequest", True),
    (
        "shift swap request",
        "shift-request-reallocate",
        {},
        "base.add_shiftrequest",
        True,
    ),
    (
        "shift request duplicate",
        "shift-request-duplicate",
        {"pk": 999999},
        "base.add_shiftrequest",
        True,
    ),
    (
        "rotating shift assign",
        "rotating-shift-assign-add",
        {},
        "base.add_rotatingshiftassign",
        False,
    ),
    ("attendance create", "attendance-create", {}, "attendance.add_attendance", False),
    (
        "overtime create",
        "attendance-overtime-create",
        {},
        "attendance.add_attendanceovertime",
        False,
    ),
    (
        "attendance request",
        "request-new-attendance",
        {},
        "attendance.change_attendance",
        True,
    ),
    ("leave request", "request-creation", {}, "leave.add_leaverequest", True),
    (
        "document request",
        "document-request-create",
        {},
        "horilla_documents.add_documentrequest",
        False,
    ),
]


def _grant(user, dotted):
    app_label, codename = dotted.split(".")
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )


class EmployeeScopeGateTests(TestCase):
    def setUp(self):
        self.client.raise_request_exception = False
        company = make_company("Scope Co")
        self.manager_user = make_user("scopemanager")
        self.manager = make_employee(
            company=company, email="scopemanager@test.horilla", user=self.manager_user
        )
        self.report = make_employee(company=company, email="report@test.horilla")
        self.stranger = make_employee(company=company, email="stranger@test.horilla")
        EmployeeWorkInformation.objects.filter(employee_id=self.report).update(
            reporting_manager_id=self.manager
        )
        self.client.force_login(self.manager_user)

    def _post(self, url_name, kwargs, employee):
        return self.client.post(
            reverse(url_name, kwargs=kwargs), {"employee_id": [employee.pk]}, **HX
        )

    def test_a_manager_is_refused_for_an_employee_who_is_not_their_report(self):
        for label, url_name, kwargs, _perm, _self in VIEWS:
            with self.subTest(view=label):
                response = self._post(url_name, kwargs, self.stranger)
                self.assertTemplateUsed(response, DENIED)

    def test_a_manager_is_allowed_for_their_own_report(self):
        for label, url_name, kwargs, _perm, _self in VIEWS:
            with self.subTest(view=label):
                response = self._post(url_name, kwargs, self.report)
                self.assertTemplateNotUsed(response, DENIED)

    def test_a_manager_must_not_slip_a_stranger_in_with_their_own_report(self):
        for label, url_name, kwargs, _perm, _self in VIEWS:
            with self.subTest(view=label):
                response = self.client.post(
                    reverse(url_name, kwargs=kwargs),
                    {"employee_id": [self.report.pk, self.stranger.pk]},
                    **HX,
                )
                self.assertTemplateUsed(response, DENIED)

    def test_the_caller_may_name_themselves_only_where_the_dropdown_offers_it(self):
        for label, url_name, kwargs, _perm, self_ok in VIEWS:
            with self.subTest(view=label):
                response = self._post(url_name, kwargs, self.manager)
                if self_ok:
                    self.assertTemplateNotUsed(response, DENIED)
                else:
                    self.assertTemplateUsed(response, DENIED)

    def test_a_holder_of_the_permission_may_name_anyone(self):
        for label, url_name, kwargs, perm, _self in VIEWS:
            with self.subTest(view=label):
                _grant(self.manager_user, perm)
                response = self._post(url_name, kwargs, self.stranger)
                self.assertTemplateNotUsed(response, DENIED)

    def test_a_user_with_no_employee_record_gets_nothing_processed(self):
        """
        The framework's own login check answers 204 for a user who has no
        employee record, before the form is reached, so nothing is saved.
        """
        outsider = make_user("noemployee")
        self.client.force_login(outsider)
        for label, url_name, kwargs, _perm, _self in VIEWS:
            with self.subTest(view=label):
                response = self._post(url_name, kwargs, self.stranger)
                self.assertEqual(response.status_code, 204)


class DocumentCreateScopeTests(TestCase):
    """The document upload route names its employee in the path and the form."""

    def setUp(self):
        self.client.raise_request_exception = False
        company = make_company("Doc Co")
        self.user = make_user("docuser")
        self.me = make_employee(
            company=company, email="docuser@test.horilla", user=self.user
        )
        self.other = make_employee(company=company, email="other@test.horilla")
        self.client.force_login(self.user)

    def _post(self, employee):
        return self.client.post(
            reverse("document-create", kwargs={"emp_id": employee.pk}),
            {"employee_id": [employee.pk]},
            **HX,
        )

    def test_an_employee_may_upload_for_themselves(self):
        self.assertTemplateNotUsed(self._post(self.me), DENIED)

    def test_an_employee_may_not_upload_for_someone_else(self):
        self.assertTemplateUsed(self._post(self.other), DENIED)

    def test_the_posted_employee_is_checked_not_the_one_in_the_path(self):
        response = self.client.post(
            reverse("document-create", kwargs={"emp_id": self.me.pk}),
            {"employee_id": [self.other.pk]},
            **HX,
        )
        self.assertTemplateUsed(response, DENIED)

    def test_a_holder_of_the_add_permission_may_upload_for_anyone(self):
        _grant(self.user, "horilla_documents.add_document")
        self.assertTemplateNotUsed(self._post(self.other), DENIED)
