"""
The payroll dashboard builds part of its markup in JavaScript, and the currency
symbol is settings data. It must be escaped wherever it is written into that
markup, and must reach the script as a JS-escaped string.
"""

from django.test import Client, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee, make_user
from payroll.models.tax_models import PayrollSettings

SYMBOL = "<b>\"'"


class DashboardMoneyMarkupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = make_company("Money Markup Co")
        cls.user = make_user("money_admin", password="secret123", is_superuser=True)
        make_employee(company=company, email="money_admin@test.horilla", user=cls.user)
        PayrollSettings.objects.all().delete()
        PayrollSettings.objects.create(
            currency_symbol=SYMBOL, position="prefix", company_id=company
        )

    def page(self):
        client = Client()
        client.force_login(type(self.user).objects.get(pk=self.user.pk))
        response = client.get(reverse("view-payroll-dashboard"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_the_symbol_reaches_the_script_as_an_escaped_string(self):
        body = self.page()
        self.assertIn('const CURRENCY_SYMBOL = "\\u003Cb\\u003E', body)
        self.assertNotIn(SYMBOL, body)

    def test_markup_built_in_the_script_escapes_the_symbol(self):
        body = self.page()
        self.assertIn("const fmtMoneyHtml = v => escHtml(fmtMoney(v));", body)
        self.assertIn("${escHtml(CURRENCY_SYMBOL)}", body)
        # The definition of fmtMoney itself uses the raw symbol; nothing else
        # may put it, or a formatted amount, straight into markup.
        definition = next(
            line for line in body.splitlines() if "const fmtMoney = v =>" in line
        )
        rest = body.replace(definition, "")
        for unsafe in ("${fmtMoney(", "${CURRENCY_SYMBOL}", "+ fmtMoney("):
            with self.subTest(unsafe=unsafe):
                self.assertNotIn(unsafe, rest)
