"""Clicking a section crumb that redirects (Employee goes to its dashboard) steps the trail back."""

from django.test import TestCase

from horilla_crumbs.context_processors import _employee_redirect
from horilla_crumbs.tests.test_payroll_batch_steps import Walk

LIST = "/employee/employee-view/"
RECORD = "/employee/employee-view-update/9/"
DASHBOARD = "/employee/dashboard/"


class RedirectingCrumbTests(TestCase):
    def setUp(self):
        self.walk = Walk()
        self.walk.visit(LIST)
        self.walk.visit(RECORD, referer=LIST)

    def test_the_section_redirect_keeps_the_crumb_flag(self):
        request = self.walk.factory.get("/employee/?breadcrumb_nav=true")
        request.user = self.walk.user
        response = _employee_redirect(request)
        self.assertEqual(response.url, f"{DASHBOARD}?breadcrumb_nav=true")

    def test_landing_on_the_redirect_target_drops_the_record(self):
        before = self.walk.visit(RECORD, referer=LIST)
        crumbs = self.walk.visit(DASHBOARD, referer=RECORD, query="breadcrumb_nav=true")
        self.assertNotIn(before[-1], crumbs)
        self.assertEqual(crumbs, ["Horilla", "employee"])

    def test_an_earlier_crumb_still_in_the_trail_is_walked_back_to(self):
        crumbs = self.walk.visit(LIST, referer=RECORD, query="breadcrumb_nav=true")
        self.assertEqual(crumbs, ["Horilla", "employee", "employee-view"])


class EveryCrumbLinkIsACrumbClickTests(TestCase):
    """Only the last crumb's stored URL carries the flag; the bar adds it to the rest."""

    def test_the_filter_adds_the_flag_once(self):
        from base.templatetags.basefilters import crumb_url

        self.assertEqual(crumb_url("/employee/"), "/employee/?breadcrumb_nav=true")
        self.assertEqual(crumb_url("/a/?x=1"), "/a/?x=1&breadcrumb_nav=true")
        self.assertEqual(crumb_url("/?breadcrumb_nav=true"), "/?breadcrumb_nav=true")

    def test_the_bar_links_a_section_crumb_with_the_flag(self):
        from django.template.loader import render_to_string

        walk = Walk()
        walk.visit(LIST)
        walk.visit(RECORD, referer=LIST)
        request = walk.factory.get(RECORD)
        request.user = walk.user
        html = render_to_string(
            "base/navbar_components/breadcrumbs_view.html",
            {"breadcrumbs": walk.session["breadcrumbs"], "request": request},
        )
        self.assertIn('href="http://testserver/employee/?breadcrumb_nav=true"', html)


class FragmentWithTheFlagTests(TestCase):
    """The Employees page loads its list as a fragment that repeats the page's query."""

    def test_the_list_fragment_does_not_become_a_crumb(self):
        walk = Walk()
        walk.visit(LIST)
        walk.visit(RECORD, referer=LIST)
        walk.visit(LIST, referer=RECORD, query="breadcrumb_nav=true")
        request = walk.factory.get(
            "/employee/employees-list/?breadcrumb_nav=true&referrer=%2Femployee%2Femployee-view%2F",
            HTTP_HX_REQUEST="true",
        )
        request.session = walk.session
        request.user = walk.user
        request.MENUS = []
        from horilla_crumbs.context_processors import breadcrumbs

        breadcrumbs(request)
        names = [crumb["name"] for crumb in walk.session["breadcrumbs"]]
        self.assertEqual(names, ["Horilla", "employee", "employee-view"])

    def test_the_bar_refresh_keeps_its_query_out_of_the_crumb(self):
        from django.urls import reverse

        walk = Walk()
        walk.user.is_active = True
        walk.visit(LIST)
        request = walk.factory.get(reverse("breadcrumbs-fragment"), {"path": RECORD})
        request.session = walk.session
        request.user = walk.user
        request.MENUS = []
        from horilla_crumbs.views import breadcrumbs_fragment

        breadcrumbs_fragment(request)
        self.assertNotIn("path=", walk.session["breadcrumbs"][-1]["url"])
