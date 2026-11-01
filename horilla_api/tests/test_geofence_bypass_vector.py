"""
The concrete attack the fail-open geo-fence allowed.

EmployeeLocationSerializer is a ModelSerializer over GeoFencing's FloatFields
with no range validators, so a caller may submit any latitude. geopy's
geodesic() raises ValueError outside [-90, 90]. Under the old bare
`except: pass` that exception was swallowed and the punch proceeded -- so an
authenticated employee could clock in from anywhere by sending a nonsense
latitude.

Attacker-controlled and requires only a valid login, which is why this is a
bypass rather than an environmental edge case.
"""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from attendance.models import Attendance
from geofencing.models import GeoFencing
from horilla.horilla_middlewares import set_selected_company
from horilla.testkit import make_company, make_employee, make_user

CLOCK_IN_URL = "/api/v1/attendance/clock-in/"


class GeofenceBypassVectorTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        set_selected_company(None)
        self.company = make_company("Fenced Co")
        self.user = make_user("fenced_user", password="secret123")
        self.employee = make_employee(
            company=self.company,
            email="fenced@test.horilla",
            first_name="Fen",
            user=self.user,
        )
        # bulk_create bypasses GeoFencing.save(), which calls full_clean() ->
        # clean() -> a live Nominatim reverse-geocode. No network in tests.
        GeoFencing.objects.bulk_create(
            [
                GeoFencing(
                    latitude=12.9716,
                    longitude=77.5946,
                    radius_in_meters=100,
                    company_id=self.company,
                    start=True,
                )
            ]
        )
        # A real token, not force_authenticate: TenantScopedJWTAuthentication
        # is what resolves the company ContextVar that company-scoped managers
        # read, and the fence check depends on resolving the company.
        login = self.client.post(
            "/api/v1/auth/login/",
            {"username": "fenced_user", "password": "secret123"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    def _punched(self):
        return Attendance.objects.filter(
            employee_id=self.employee, attendance_date=date.today()
        ).exists()

    def test_out_of_range_latitude_cannot_bypass_the_fence(self):
        """The vector: nonsense coordinates must not become a free punch."""
        response = self.client.post(
            CLOCK_IN_URL, {"latitude": 999, "longitude": 999}, format="json"
        )
        # 503 is the deliberate fail-closed answer, not a crash (that is a 500).
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self._punched(), "no attendance may be recorded")

    def test_genuinely_outside_the_fence_is_refused(self):
        response = self.client.post(
            CLOCK_IN_URL, {"latitude": 48.8566, "longitude": 2.3522}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self._punched())

    def test_missing_coordinates_are_refused(self):
        response = self.client.post(CLOCK_IN_URL, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self._punched())
