"""FAQ questions reach the page as JSON data, never as inline script source."""

from django.test import TestCase
from django.urls import reverse

from base.models import Company
from helpdesk.models import FAQ, FAQCategory
from horilla.testkit import make_employee, make_user


class FAQViewEscapesQuestionsTests(TestCase):
    def setUp(self):
        company = Company.objects.create(company="Acme", hq=True)
        user = make_user("emp", password="pw-not-real")
        make_employee(company=company, email="emp@test.horilla", user=user)
        self.client.force_login(user)
        category = FAQCategory.objects.create(title="General", description="d")
        FAQ.objects.create(
            question="'];alert(document.cookie);//</script>",
            answer="a",
            category=category,
        )

    def test_question_is_json_encoded_not_inlined(self):
        response = self.client.get(reverse("faq-category-view"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('id="faq-list"', body)
        self.assertNotIn("alert(document.cookie);//</script>", body)
        self.assertIn("\\u003C/script\\u003E", body)
