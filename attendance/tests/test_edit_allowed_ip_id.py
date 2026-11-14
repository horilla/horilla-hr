"""
edit_allowed_ips read the id with int(), which raises TypeError for a missing
id, and rendered a form that is only built after the id check, so any invalid
id (missing or out of range) ended in a 500 instead of an error message.
"""

from django.test import TestCase
from django.urls import reverse

from base.models import AttendanceAllowedIP
from horilla.testkit import make_company, make_employee, make_user


class EditAllowedIpTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Acme")
        cls.admin_user = make_user("root", password="pw-not-real", is_superuser=True)
        make_employee(
            company=cls.company, email="root@test.horilla", user=cls.admin_user
        )

    def setUp(self):
        self.client.force_login(self.admin_user)
        self.url = reverse("edit-allowed-ip")
        session = self.client.session
        session["selected_company"] = self.company.pk
        session.save()
        AttendanceAllowedIP.objects.create(
            company_id=self.company,
            is_enabled=True,
            additional_data={"allowed_ips": ["10.0.0.1", "10.0.0.2"]},
        )

    def messages(self, response):
        return [str(m) for m in response.wsgi_request._messages]

    def test_missing_id_is_reported_not_a_500(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)
        self.assertIn("Invalid ID provided.", self.messages(response))

    def test_invalid_ids_are_reported_not_a_500(self):
        for value in ("", "abc", "-1", "5", "1.5"):
            with self.subTest(id=value):
                for method in (self.client.post, self.client.get):
                    response = method(self.url, {"id": value})
                    self.assertEqual(response.status_code, 302)

    def test_a_valid_id_still_opens_the_form(self):
        response = self.client.get(self.url, {"id": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "10.0.0.2")
