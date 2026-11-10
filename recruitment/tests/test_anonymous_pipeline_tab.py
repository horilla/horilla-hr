"""
Tab views are constructed before dispatch() runs the login check, so their
__init__ must cope with an anonymous request. It used to read
request.session.session_key (None) and raise a TypeError, a 500 instead of the
login redirect.
"""

from django.test import TestCase
from django.urls import reverse


class AnonymousTabViewTests(TestCase):
    def assert_sent_to_login(self, url_name):
        url = reverse(url_name)
        login = reverse("login")

        # Plain browser request: a normal redirect.
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302, url_name)
        self.assertIn(login, response["Location"])

        # HTMX request: the login decorator answers 204 with HX-Refresh, so
        # the page reloads and the browser lands on the login screen.
        response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 204, url_name)
        self.assertEqual(response["HX-Refresh"], "true", url_name)

    def test_recruitment_pipeline_tab_sends_anonymous_users_to_login(self):
        self.assert_sent_to_login("cbv-pipeline-tab")

    def test_project_time_sheet_tab_sends_anonymous_users_to_login(self):
        self.assert_sent_to_login("time-sheet-tab-view")
