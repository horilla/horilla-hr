"""
A company without a logo must not put "/404/" in an <img src>.

FieldFile.url answers "/404/" for an empty field (horilla/models.py). The company
session entry, the company switcher list and the sidebar used to print it, so a
workspace whose company has no icon showed a broken image next to its name.
"""

import re

from django.test import TestCase
from django.urls import reverse

from base.context_processors import company_icon_url
from horilla.testkit.factories import make_company, make_employee, make_user

BROKEN = re.compile(r'<img[^>]*src="/404/"')


class CompanyIconUrlTests(TestCase):
    def test_company_without_icon_gives_empty_string(self):
        company = make_company("No Logo Ltd")
        self.assertEqual(company_icon_url(company), "")

    def test_company_with_icon_gives_its_url(self):
        company = make_company("Logo Ltd")
        company.icon.name = "company/logo.png"
        self.assertTrue(company_icon_url(company).endswith("company/logo.png"))


class SidebarWithoutCompanyIconTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("No Logo Ltd")
        cls.user = make_user("boss", is_superuser=True)
        make_employee(company=cls.company, email="boss@logo.test", user=cls.user)

    def test_dashboard_has_no_broken_company_image(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home-page"), follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("No Logo Ltd", html)
        self.assertIsNone(
            BROKEN.search(html), "the sidebar still prints /404/ as the company logo"
        )
        self.assertEqual(self.client.session["selected_company_instance"]["icon"], "")

    def test_a_session_saved_before_the_fix_still_renders(self):
        self.client.force_login(self.user)
        self.client.get(reverse("home-page"), follow=True)
        session = self.client.session
        session["selected_company_instance"] = {
            **session["selected_company_instance"],
            "icon": "/404/",
        }
        session.save()
        html = self.client.get(reverse("home-page"), follow=True).content.decode()
        self.assertIsNone(BROKEN.search(html))
