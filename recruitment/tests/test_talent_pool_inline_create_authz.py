"""Creating a talent pool inline takes the permission the Talent Pools page takes."""

from django.contrib.auth.models import Permission
from django.test import Client, TestCase

from horilla.testkit import make_company, make_employee, make_user
from horilla_views.generic.cbv.views import register_dynamic_url
from recruitment.cbv.candidates import TalentPoolDynamicCreateFormView

# The "Add to Talent Pool" modal registers this route per session when it opens;
# the test registers it directly so the view can be reached.
ROUTE = "dynamic-path-skill_zone_ids-talent-pool-authz-test"


class TalentPoolInlineCreateAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        register_dynamic_url(ROUTE, TalentPoolDynamicCreateFormView.as_view(), ROUTE)
        company = make_company("Talent Pool Co")
        cls.plain_user = make_user("tp_plain", password="secret123")
        make_employee(
            company=company, email="tp_plain@test.horilla", user=cls.plain_user
        )
        cls.hr_user = make_user("tp_hr", password="secret123")
        make_employee(company=company, email="tp_hr@test.horilla", user=cls.hr_user)
        cls.hr_user.user_permissions.add(
            Permission.objects.get(codename="add_skillzone")
        )

    def open_form_as(self, user):
        client = Client()
        client.force_login(user)
        return client.get(f"/{ROUTE}", HTTP_HX_REQUEST="true")

    def test_a_user_without_the_permission_is_not_given_the_create_form(self):
        self.assertNotContains(self.open_form_as(self.plain_user), "<form")

    def test_a_user_with_the_permission_is_given_the_create_form(self):
        self.assertContains(self.open_form_as(self.hr_user), "<form")
