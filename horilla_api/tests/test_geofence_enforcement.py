"""
The geo-fence must fail *closed* on the punch endpoints.

``ClockInAPIView``/``ClockOutAPIView`` previously wrapped the whole fence
check in a bare ``except: pass``. A missing company, an absent ``geo_fencing``
relation, or a geopy timeout inside the location check therefore allowed the
punch -- the exact case the fence exists to prevent. These tests pin the
corrected behaviour: an *enabled* fence that cannot be evaluated denies.

Deliberately unit tests over ``geofence_denial`` rather than end-to-end
endpoint tests: the call sites are two lines each, while every branch that
matters lives in the helper, and driving clock-in end to end would drag in
shifts, schedules and work-info fixtures that prove nothing extra here.

Note that ``geofencing`` *is* installed, though not from settings -- it is
appended to INSTALLED_APPS as an import side effect in
``horilla_api/__init__.py``. The enforcement path this covers is live.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from horilla_api.api_views.attendance.views import geofence_denial


class _Req:
    """Minimal stand-in for the DRF request the helper reads."""

    def __init__(self, company):
        self.user = SimpleNamespace(
            id=7,
            employee_get=SimpleNamespace(get_company=lambda: company),
        )


def _company(fence):
    """A company whose fence (its own, else the global one) is ``fence``."""
    return SimpleNamespace(fence=fence)


LOCATION_CHECK = "geofencing.views.GeoFencingEmployeeLocationCheckAPIView.post"


class GeofenceFailClosedTests(SimpleTestCase):
    def setUp(self):
        # geofence_denial asks GeoFencing.for_company(company); resolve it from the stand-in
        # company instead of the database
        patcher = patch(
            "geofencing.models.GeoFencing.for_company",
            side_effect=lambda company: company.fence,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_enabled_fence_denies_when_check_raises(self):
        """The regression: an erroring check must NOT allow the punch."""
        req = _Req(_company(SimpleNamespace(start=True)))
        with patch(LOCATION_CHECK, side_effect=RuntimeError("geopy timeout")):
            denial = geofence_denial(req)
        self.assertIsNotNone(denial, "an unevaluable fence must deny the punch")
        self.assertEqual(denial.status_code, 503)

    def test_enabled_fence_denies_when_outside(self):
        req = _Req(_company(SimpleNamespace(start=True)))
        outside = SimpleNamespace(status_code=400)
        with patch(LOCATION_CHECK, return_value=outside):
            self.assertIs(geofence_denial(req), outside)

    def test_enabled_fence_allows_when_inside(self):
        req = _Req(_company(SimpleNamespace(start=True)))
        with patch(LOCATION_CHECK, return_value=SimpleNamespace(status_code=200)):
            self.assertIsNone(geofence_denial(req))

    def test_disabled_fence_skips_the_check_entirely(self):
        """start=False means the feature is off -- no location call at all."""
        req = _Req(_company(SimpleNamespace(start=False)))
        with patch(LOCATION_CHECK) as location_check:
            self.assertIsNone(geofence_denial(req))
        location_check.assert_not_called()

    def test_unconfigured_fence_allows(self):
        """Installs with no GeoFencing row must keep punching normally."""
        self.assertIsNone(geofence_denial(_Req(_company(None))))

    def test_no_company_allows(self):
        """No company means no fence to enforce; not a denial."""
        self.assertIsNone(geofence_denial(_Req(None)))
