"""API manager_permission_required returns 403 (not 401)."""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from attendance.models import Attendance
from horilla.testkit import make_company, make_employee, make_user


class ManagerPermission403Tests(TestCase):
    URL = "/api/attendance/permission-check/attendance"

    def setUp(self):
        self.client = APIClient()
        company = make_company("API 403 Co")
        self.user = make_user("api_mgr403", password="secret123")
        make_employee(
            company=company,
            email="api_mgr403@test.horilla",
            user=self.user,
        )

    def test_missing_manager_perm_returns_403(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 403)
        self.assertIn("error", response.data)

    def test_manager_perm_allows_200(self):
        ct = ContentType.objects.get_for_model(Attendance)
        perm = Permission.objects.get(content_type=ct, codename="view_attendance")
        self.user.user_permissions.add(perm)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
