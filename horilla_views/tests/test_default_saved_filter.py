"""
A saved filter marked "Is default" is applied when its list or card view
first loads with no filter of its own, with every value of a multi-value
field. "Clear all" still shows everything.
"""

import django_filters
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.http import QueryDict
from django.test import RequestFactory, TestCase

from horilla.filters import FilterSet
from horilla.horilla_middlewares import _thread_locals
from horilla_views.cbv_methods import apply_default_saved_filter
from horilla_views.generic.cbv.views import HorillaCardView, HorillaListView
from horilla_views.models import SavedFilter

PATH = "/saved-filter-default-test/"
FIRST_LOAD = "default_filter=on&filter_applied=on&search=&color="


class ColourFilter(FilterSet):
    color = django_filters.AllValuesMultipleFilter()

    class Meta:
        model = SavedFilter
        fields = ["color"]


class ColourCardView(HorillaCardView):
    model = SavedFilter
    filter_class = ColourFilter


class ColourListView(HorillaListView):
    model = SavedFilter
    filter_class = ColourFilter


class DefaultSavedFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("defaultfilter", password="x")
        self.request = self.make_request()
        # Rows for the views to list; the default filter below picks two.
        for colour in ("red", "green", "blue"):
            self.make_filter(title=colour, color=colour, path="/elsewhere/")

    def make_request(self, query=""):
        request = RequestFactory().get(PATH + query)
        request.user = self.user
        request.session = SessionStore()
        request.session.create()
        _thread_locals.request = request
        self.addCleanup(setattr, _thread_locals, "request", None)
        return request

    def make_filter(self, **fields):
        saved = SavedFilter(created_by=self.user, **{"filter": "{}", **fields})
        saved.save()
        return saved

    def make_default(self):
        # As the Save button stores it: path and referrer ride along.
        self.make_filter(
            title="Warm and cool",
            path=PATH,
            is_default=True,
            filter="{'path': '/x/', 'referrer': '', 'color': 'red'}",
            urlencode="path=%2Fx%2F&referrer=&color=red&color=blue",
        )

    def listed(self, view_class):
        view = view_class()
        view.request = self.request
        return set(view.get_queryset().values_list("title", flat=True))

    def default_for(self, query):
        return apply_default_saved_filter(self.request, QueryDict(query), ColourFilter)

    def colours(self, query):
        return self.default_for(query).getlist("color")

    def test_without_a_default_the_request_is_unchanged(self):
        self.assertEqual(self.colours(FIRST_LOAD), [""])

    def test_default_keeps_every_value_and_leaves_path_and_referrer(self):
        self.make_default()
        query = self.default_for("")
        self.assertEqual(query.getlist("color"), ["red", "blue"])
        self.assertNotIn("path", query)
        self.assertNotIn("referrer", query)

    def test_nav_first_load_gets_the_default(self):
        # The nav bar's blank form, flagged as its first load.
        self.make_default()
        query = self.default_for(FIRST_LOAD + "&nav_url=%2Fnav%2F")
        self.assertEqual(query.getlist("color"), ["red", "blue"])
        self.assertEqual(query["nav_url"], "/nav/")
        # The flag isn't a filter: no tag, not in page links.
        self.assertNotIn("default_filter", query)

    def test_clear_all_shows_everything(self):
        # The same blank form without the first-load flag.
        self.make_default()
        self.assertEqual(
            self.colours(FIRST_LOAD.replace("default_filter=on&", "")), [""]
        )

    def test_a_first_load_that_filters_keeps_its_filter(self):
        self.make_default()
        self.assertEqual(self.colours(FIRST_LOAD + "&color=green"), ["", "green"])

    def test_default_saved_before_urlencode_falls_back_to_filter(self):
        self.make_filter(
            title="Old", path=PATH, is_default=True, filter="{'color': 'green'}"
        )
        self.assertEqual(self.colours(""), ["green"])

    def test_views_apply_the_default_on_first_load(self):
        self.make_default()
        self.request = self.make_request("?" + FIRST_LOAD)
        for view_class in (ColourCardView, ColourListView):
            with self.subTest(view=view_class.__name__):
                self.assertEqual(self.listed(view_class), {"red", "blue"})

    def test_a_filter_in_the_request_wins_over_the_default(self):
        self.make_default()
        self.request = self.make_request("?filter_applied=on&color=green")
        for view_class in (ColourCardView, ColourListView):
            with self.subTest(view=view_class.__name__):
                self.assertEqual(self.listed(view_class), {"green"})
