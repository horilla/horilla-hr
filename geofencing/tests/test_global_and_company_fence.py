"""A global geofence and company geofences must work together (issue #1286).

Reported as: after a global fence exists, adding a fence for a company answers "Not valid", and the
global fence is not applied to any company. Both come from the same place:

* the setup page validated a company's new fence before giving it its company, and the model
  allows only one fence without a company - so as soon as a global fence existed, the new one
  (still company-less at that moment) was rejected;
* every lookup asked only for ``company_id=<this company>``, so the global fence was never used.

A company's own fence overrides the global one; a company with none falls back to it.
Nominatim is mocked - the model asks it to reverse-geocode on save.
"""

from unittest.mock import MagicMock, patch

from django.test import RequestFactory, TestCase
from django.urls import reverse

from geofencing.models import GeoFencing
from horilla.testkit import make_company, make_employee, make_user

FENCE = {
    "latitude": "12.97",
    "longitude": "77.59",
    "radius_in_meters": "150",
    "start": "on",
}


def make_fence(company=None, **extra):
    values = {
        "latitude": 12.97,
        "longitude": 77.59,
        "radius_in_meters": 100,
        "start": True,
    }
    values.update(extra)
    return GeoFencing.objects.create(company_id=company, **values)


@patch("geofencing.models.Nominatim")
class FenceForCompanyTests(TestCase):
    def setUp(self):
        self.acme = make_company("Acme")
        self.globex = make_company("Globex", hq=False)

    def test_a_company_without_a_fence_uses_the_global_one(self, nominatim):
        nominatim.return_value.reverse.return_value = MagicMock()
        global_fence = make_fence(None, radius_in_meters=500)
        self.assertEqual(GeoFencing.for_company(self.acme), global_fence)
        self.assertEqual(GeoFencing.for_company(self.globex), global_fence)

    def test_a_companys_own_fence_overrides_the_global_one(self, nominatim):
        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, radius_in_meters=500)
        own = make_fence(self.acme, radius_in_meters=50)
        self.assertEqual(GeoFencing.for_company(self.acme), own)

    def test_no_fence_at_all_is_none(self, nominatim):
        self.assertIsNone(GeoFencing.for_company(self.acme))
        self.assertIsNone(GeoFencing.for_company(None))

    def test_the_web_punch_check_follows_the_global_fence(self, nominatim):
        from attendance.methods.utils import geofence_denial_web

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, radius_in_meters=100)
        far_away = RequestFactory().get("/", {"latitude": "40.0", "longitude": "-74.0"})
        self.assertIsNotNone(geofence_denial_web(far_away, self.acme))
        nearby = RequestFactory().get("/", {"latitude": "12.97", "longitude": "77.59"})
        self.assertIsNone(geofence_denial_web(nearby, self.acme))

    def test_a_switched_off_global_fence_blocks_nobody(self, nominatim):
        from attendance.methods.utils import geofence_denial_web

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, start=False)
        far_away = RequestFactory().get("/", {"latitude": "40.0", "longitude": "-74.0"})
        self.assertIsNone(geofence_denial_web(far_away, self.acme))


@patch("geofencing.models.Nominatim")
class WhereTheFenceIsReadTests(TestCase):
    """Every place that reports or enforces the fence must read the same one."""

    LOCATION_CHECK = "geofencing.views.GeoFencingEmployeeLocationCheckAPIView.post"

    def setUp(self):
        self.acme = make_company("Acme")
        self.user = make_user("fence-employee")
        self.employee = make_employee(
            company=self.acme, email="fence-employee@test.horilla", user=self.user
        )

    def request_for(self, company):
        from types import SimpleNamespace

        return SimpleNamespace(
            user=SimpleNamespace(
                id=1, employee_get=SimpleNamespace(get_company=lambda: company)
            ),
            data={},
        )

    def test_the_api_punch_check_enforces_the_global_fence(self, nominatim):
        from types import SimpleNamespace

        from horilla_api.api_views.attendance.views import geofence_denial

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, start=True)
        with patch(self.LOCATION_CHECK) as location_check:
            location_check.return_value = SimpleNamespace(status_code=200)
            geofence_denial(self.request_for(self.acme))
        location_check.assert_called_once()

    def test_no_fence_at_all_lets_the_punch_through(self, nominatim):
        from horilla_api.api_views.attendance.views import geofence_denial

        with patch(self.LOCATION_CHECK) as location_check:
            self.assertIsNone(geofence_denial(self.request_for(self.acme)))
        location_check.assert_not_called()

    def test_the_mobile_config_reports_the_global_fence(self, nominatim):
        from horilla_api.api_views.mobile.views import _geofence_block

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, radius_in_meters=500)
        block = _geofence_block(self.employee)
        self.assertTrue(block["enabled"])
        self.assertEqual(block["radius_in_meters"], 500)

    def test_the_mobile_config_is_off_without_any_fence(self, nominatim):
        from horilla_api.api_views.mobile.views import _geofence_block

        self.assertEqual(_geofence_block(self.employee), {"enabled": False})

    def test_the_login_response_reports_the_global_fence(self, nominatim):
        from rest_framework.test import APIClient

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, start=True)
        self.user.set_password("fence-pass-1")
        self.user.save()
        response = APIClient().post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": "fence-pass-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["geo_fencing"], True)

    def test_the_login_response_is_off_without_any_fence(self, nominatim):
        from rest_framework.test import APIClient

        self.user.set_password("fence-pass-1")
        self.user.save()
        response = APIClient().post(
            "/api/v1/auth/login/",
            {"username": self.user.username, "password": "fence-pass-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["geo_fencing"], False)

    def test_a_switched_off_company_fence_overrides_an_enabled_global_one(
        self, nominatim
    ):
        from attendance.methods.utils import geofence_denial_web
        from horilla_api.api_views.mobile.views import _geofence_block

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, start=True)
        own = make_fence(self.acme, start=False)
        self.assertEqual(GeoFencing.for_company(self.acme), own)
        self.assertEqual(_geofence_block(self.employee), {"enabled": False})
        far_away = RequestFactory().get("/", {"latitude": "40.0", "longitude": "-74.0"})
        self.assertIsNone(geofence_denial_web(far_away, self.acme))


@patch("geofencing.models.Nominatim")
class FenceButtonWithAllCompaniesTests(TestCase):
    """With "all companies" selected the check-in button must still send the location."""

    def setUp(self):
        self.acme = make_company("Acme")
        self.user = make_user("fence-button-user")
        make_employee(
            company=self.acme, email="fence-button@test.horilla", user=self.user
        )
        # reload: the user still holds the employee object created above, whose work information
        # was cached before the company was set
        self.user = type(self.user).objects.get(pk=self.user.pk)

    def request(self, selected):
        request = RequestFactory().get("/")
        request.user = self.user
        request.session = {"selected_company": selected}
        return request

    def test_all_companies_uses_the_employees_own_company(self, nominatim):
        from base.templatetags.horillafilters import is_geofencing_enabled

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, start=True)
        self.assertTrue(is_geofencing_enabled(self.request("all")))

    def test_all_companies_follows_a_switched_off_company_fence(self, nominatim):
        from base.templatetags.horillafilters import is_geofencing_enabled

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, start=True)
        make_fence(self.acme, start=False)
        self.assertFalse(is_geofencing_enabled(self.request("all")))

    def test_a_selected_company_still_uses_that_company(self, nominatim):
        from base.templatetags.horillafilters import is_geofencing_enabled

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, start=True)
        self.assertTrue(is_geofencing_enabled(self.request(str(self.acme.pk))))

    def test_no_fence_means_no_location_is_requested(self, nominatim):
        from base.templatetags.horillafilters import is_geofencing_enabled

        self.assertFalse(is_geofencing_enabled(self.request("all")))


@patch("geofencing.models.Nominatim")
class SetupPageTests(TestCase):
    def setUp(self):
        self.acme = make_company("Acme")
        self.admin = make_user("fence-admin", is_superuser=True)
        make_employee(
            company=self.acme, email="fence-admin@test.horilla", user=self.admin
        )
        self.client.force_login(self.admin)
        self.url = reverse("geo-config")

    def post_for(self, company_id, **extra):
        session = self.client.session
        session["selected_company"] = company_id
        session.save()
        response = self.client.post(self.url, {**FENCE, **extra})
        return response

    def test_a_company_fence_can_be_added_after_a_global_one(self, nominatim):
        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None)
        response = self.post_for(str(self.acme.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(GeoFencing.objects.filter(company_id=self.acme).exists())
        self.assertEqual(GeoFencing.objects.count(), 2)

    def test_the_global_fence_can_still_be_edited(self, nominatim):
        nominatim.return_value.reverse.return_value = MagicMock()
        global_fence = make_fence(None, radius_in_meters=100)
        self.post_for("all", radius_in_meters="250")
        global_fence.refresh_from_db()
        self.assertEqual(global_fence.radius_in_meters, 250)
        self.assertEqual(GeoFencing.objects.count(), 1)

    def test_a_second_global_fence_is_still_refused(self, nominatim):
        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None)
        other = GeoFencing(
            latitude=1, longitude=1, radius_in_meters=10, company_id=None
        )
        with self.assertRaises(Exception):
            other.save()

    def test_editing_a_company_fence_updates_it_in_place(self, nominatim):
        nominatim.return_value.reverse.return_value = MagicMock()
        own = make_fence(self.acme, radius_in_meters=100)
        self.post_for(str(self.acme.pk), radius_in_meters="300")
        own.refresh_from_db()
        self.assertEqual(own.radius_in_meters, 300)
        self.assertEqual(GeoFencing.objects.count(), 1)


@patch("geofencing.models.Nominatim")
class WebPunchWithAllCompaniesTests(TestCase):
    """
    With "all companies" selected the clock-in view has no company of its own. It used to skip
    the geofence check completely, so an employee outside the fence could punch in.
    """

    def setUp(self):
        from attendance.models import AttendanceGeneralSetting

        self.acme = make_company("Acme")
        # only a user who can see several companies is offered "all companies"; for anyone else the
        # middleware puts their own company back in the session
        self.user = make_user("fence-punch-user", is_superuser=True)
        make_employee(
            company=self.acme, email="fence-punch@test.horilla", user=self.user
        )
        self.user = type(self.user).objects.get(pk=self.user.pk)
        # the setting the view reads when "all companies" is selected
        AttendanceGeneralSetting.objects.create(company_id=None, enable_check_in=True)
        self.client.force_login(self.user)

    def punch(self, latitude, longitude):
        from django.contrib.messages import get_messages

        session = self.client.session
        session["selected_company"] = "all"
        session.save()
        response = self.client.get(
            reverse("clock-in"),
            {"latitude": latitude, "longitude": longitude},
            HTTP_HX_REQUEST="true",
        )
        return [str(message) for message in get_messages(response.wsgi_request)]

    def test_a_punch_from_outside_the_fence_is_refused_with_all_selected(
        self, nominatim
    ):
        from attendance.models import AttendanceActivity

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, radius_in_meters=100)
        messages = self.punch("40.0", "-74.0")
        self.assertTrue(
            any("outside the permitted work location" in m for m in messages), messages
        )
        self.assertEqual(AttendanceActivity.objects.count(), 0)

    def test_a_punch_without_a_location_is_refused_with_all_selected(self, nominatim):
        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, radius_in_meters=100)
        messages = self.punch("", "")
        self.assertTrue(any("Could not verify your location" in m for m in messages))

    def test_a_punch_inside_the_fence_is_not_stopped_by_it(self, nominatim):
        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, radius_in_meters=100)
        messages = self.punch("12.97", "77.59")
        self.assertFalse(
            any("permitted work location" in m for m in messages), messages
        )
        self.assertFalse(any("verify your location" in m for m in messages), messages)

    def test_the_helper_uses_the_employees_company_when_the_view_has_none(
        self, nominatim
    ):
        from attendance.methods.utils import geofence_denial_web

        nominatim.return_value.reverse.return_value = MagicMock()
        make_fence(None, radius_in_meters=100)
        request = RequestFactory().get("/", {"latitude": "40.0", "longitude": "-74.0"})
        request.user = self.user
        self.assertIsNotNone(geofence_denial_web(request, None))
