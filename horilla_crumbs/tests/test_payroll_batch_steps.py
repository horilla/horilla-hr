"""The steps of a new payroll batch in the breadcrumb: readable, remembered, and only walked backwards."""

from types import SimpleNamespace

from django.test import RequestFactory, TestCase

from horilla_crumbs.context_processors import breadcrumbs


class Walk:
    """Visits pages one after another in one session, as a browser would."""

    def __init__(self):
        self.session = {}
        self.factory = RequestFactory()
        self.user = SimpleNamespace(
            is_superuser=True, is_authenticated=True, has_perm=lambda perm: True
        )

    def visit(self, path, referer=None, query=""):
        extra = {"HTTP_REFERER": f"http://testserver{referer}"} if referer else {}
        request = self.factory.get(path + (f"?{query}" if query else ""), **extra)
        request.session = self.session
        request.user = self.user
        request.MENUS = []
        return [crumb["name"] for crumb in breadcrumbs(request)["breadcrumbs"]]


SETTINGS = "/payroll/payroll-settings-view/"
SCOPE = "/payroll/payroll-runs/new/"
REVIEW = "/payroll/payroll-runs/new/review/"


class BatchStepNamesTests(TestCase):
    def setUp(self):
        self.walk = Walk()
        self.walk.visit(SETTINGS)

    def test_the_steps_read_as_words_not_url_segments(self):
        scope = self.walk.visit(SCOPE, referer=SETTINGS)
        review = self.walk.visit(REVIEW, referer=SCOPE)
        self.assertEqual(scope[-1], "New Batch")
        self.assertEqual(review[-2:], ["New Batch", "Review"])
        for raw in ("new", "review", "progress"):
            self.assertNotIn(raw, review)

    def test_the_steps_are_remembered_as_the_batch_is_generated(self):
        self.walk.visit(SCOPE, referer=SETTINGS)
        self.walk.visit(REVIEW, referer=SCOPE)
        progress = self.walk.visit("/payroll/payroll-runs/12/progress/", referer=REVIEW)
        self.assertEqual(progress[-3], "New Batch")
        self.assertEqual(progress[-2], "Review")
        self.assertEqual(progress[-1], "Progress")

    def test_going_back_drops_the_steps_that_came_after(self):
        self.walk.visit(SCOPE, referer=SETTINGS)
        self.walk.visit(REVIEW, referer=SCOPE)
        back = self.walk.visit(SCOPE, referer=REVIEW)
        self.assertEqual(back[-1], "New Batch")
        self.assertNotIn("Review", back)

    def test_clicking_an_earlier_crumb_drops_the_ones_after_it(self):
        self.walk.visit(SCOPE, referer=SETTINGS)
        self.walk.visit(REVIEW, referer=SCOPE)
        clicked = self.walk.visit(SCOPE, referer=REVIEW, query="breadcrumb_nav=true")
        self.assertEqual(clicked[-1], "New Batch")
        self.assertNotIn("Review", clicked)
