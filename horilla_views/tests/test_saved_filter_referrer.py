"""A saved filter's referrer is the page path, whether it came as a URL or a path."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase

from horilla.horilla_middlewares import _thread_locals
from horilla_views import views
from horilla_views.cbv_methods import referrer_path, saved_filter_path_query
from horilla_views.models import SavedFilter


class ReferrerPathTests(SimpleTestCase):
    def test_a_full_url_keeps_only_its_path_and_query(self):
        self.assertEqual(
            referrer_path("https://hr.example.com/attendance/attendance-view/"),
            "/attendance/attendance-view/",
        )
        self.assertEqual(
            referrer_path("http://hr.example.com/attendance/attendance-view/?a=1"),
            "/attendance/attendance-view/?a=1",
        )
        self.assertEqual(referrer_path("https://hr.example.com"), "/")

    def test_a_path_is_left_as_it_is(self):
        self.assertEqual(
            referrer_path("/attendance/attendance-view/"),
            "/attendance/attendance-view/",
        )
        self.assertEqual(referrer_path(""), "")


class SavedFilterReferrerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "referrer-tester", password="pw"
        )
        self.saved = SavedFilter.objects.create(
            title="Overtime week",
            path="/attendance/ot-attendance-nav/",
            referrer="/attendance/attendance-view/",
            filter={},
            urlencode="",
            created_by=self.user,
        )

    def matches(self, path, referrer):
        request = RequestFactory().get(path, {"referrer": referrer})
        return SavedFilter.objects.filter(saved_filter_path_query(request)).exists()

    def test_a_sibling_tab_of_the_same_page_shows_the_filter(self):
        page = "/attendance/attendance-view/"
        self.assertTrue(self.matches("/attendance/attendance-search/", page))
        self.assertTrue(
            self.matches("/attendance/attendance-search/", "https://hr" + page)
        )

    def test_another_page_of_the_same_app_does_not(self):
        # Pages pass their own path as the referrer; it used to be cut down
        # to "/" here, matching filters whose referrer was cut down the same way.
        SavedFilter.objects.filter(pk=self.saved.pk).update(referrer="/")
        self.assertFalse(
            self.matches(
                "/attendance/late-come-early-out-search/",
                "/attendance/late-come-early-out-view/",
            )
        )

    def test_the_save_form_keeps_a_referrer_given_as_a_path(self):
        request = RequestFactory().get(
            "/saved-filter/",
            {
                "path": "/attendance/ot-attendance-nav/",
                "referrer": "/attendance/attendance-view/",
            },
        )
        request.user = self.user
        # Horilla's views read the request from the middleware's thread local.
        _thread_locals.request = request
        self.addCleanup(setattr, _thread_locals, "request", None)
        view = views.SavedFilter()
        view.setup(request)
        context = view.get_context_data()
        self.assertEqual(context["referrer"], "/attendance/attendance-view/")
