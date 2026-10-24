"""
API clients authenticated by token send no session cookie. Fail2BanMiddleware
used to create a session for every such request. The accessibility checks now
key their cache on the user for such a client
(horilla.methods.get_accessibility_cache_key), so it gets no session at all.
"""

from django.contrib.auth.models import Permission
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sessions.models import Session
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient

from horilla.horilla_middlewares import _thread_locals, set_selected_company
from horilla.testkit import make_company, make_employee, make_user
from horilla_api.api_decorators.employee.decorators import enter_if_accessible


class ApiWithoutSessionTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        company = make_company("No Session Co")
        self.user = make_user("nosession_user")
        self.employee = make_employee(
            company=company, email="nosession@test.horilla", user=self.user
        )
        make_employee(company=company, email="colleague@test.horilla")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_the_employee_filter_works_without_a_session_cookie(self):
        # EmployeeFilter.filter_queryset builds its accessibility cache key
        # from the session key; None + str raised TypeError.
        self.user.user_permissions.add(Permission.objects.get(codename="view_employee"))
        response = self.client.get("/api/v1/attendance/offline-employees/count/")
        self.assertEqual(response.status_code, 200, response.content)

    def test_the_directory_works_without_a_session_cookie(self):
        response = self.client.get("/api/v1/employee/list/employees/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreater(response.data["count"], 1)

    def test_cookieless_calls_create_no_sessions(self):
        self.user.user_permissions.add(Permission.objects.get(codename="view_employee"))
        for _ in range(5):
            self.client.cookies.clear()
            self.client.get("/api/v1/employee/list/employees/")
            self.client.get("/api/v1/attendance/offline-employees/count/")
        self.assertEqual(Session.objects.count(), 0)

    def test_enter_if_accessible_works_without_a_session(self):
        request = RequestFactory().get("/api/v1/anything/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.user = self.user
        self.assertIsNone(request.session.session_key)

        class View:
            @enter_if_accessible(feature="employee_view")
            def get(self, *args, **kwargs):
                return "allowed"

        _thread_locals.request = request
        try:
            # No DefaultAccessibility row: the feature is open to everyone.
            self.assertEqual(View().get(), "allowed")
        finally:
            _thread_locals.request = None
        self.assertIsNone(request.session.session_key)
