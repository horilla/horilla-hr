"""The currency shown must be the selected company's, not a leftover "$".

PayrollSettings is per company, but HorillaCompanyManager also lets the row
without a company through. A typical install ends up with two rows:

    id 1  "$"  no company   created by default_currency() on the first page
                            load, before a company was set up or selected
    id 2  "£"  Company A    created when the currency was saved in settings

Most lookups used .objects.first(), which orders by id and so returned the
"$" row: payroll pages and payslips showed "$" although the settings page
showed "£". The currency_symbol_position filter already preferred the
company's row, so the dashboard showed "£" and the two disagreed.
"""

from contextvars import Context
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from base.models import Company
from base.templatetags.horillafilters import currency_symbol_position
from horilla.horilla_middlewares import _thread_locals, set_selected_company
from payroll.context_processors import default_currency
from payroll.models.tax_models import PayrollSettings
from payroll.threadings.mail import MailSendThread
from report.export import _currency_format


class CurrencySettingsTests(TestCase):
    def setUp(self):
        set_selected_company(None)
        self.company = Company.objects.create(company="Company A", hq=True)
        # Created first, so it has the lower id -- as on a real install.
        self.global_row = PayrollSettings.objects.create(
            currency_symbol="$", position="postfix", company_id=None
        )
        self.company_row = PayrollSettings.objects.create(
            currency_symbol="£", position="prefix", company_id=self.company
        )

    def tearDown(self):
        set_selected_company(None)
        _thread_locals.request = None

    def _context(self):
        request = RequestFactory().get("/")
        request.session = {}
        return default_currency(request)

    def test_selected_company_uses_its_own_row(self):
        set_selected_company(str(self.company.id))

        self.assertEqual(PayrollSettings.for_selected_company(), self.company_row)
        self.assertEqual(self._context(), {"currency": "£", "position": "prefix"})
        self.assertEqual(currency_symbol_position("100"), "£ 100")

    def test_no_company_selected_uses_the_row_without_a_company(self):
        self.assertEqual(PayrollSettings.for_selected_company(), self.global_row)
        self.assertEqual(self._context(), {"currency": "$", "position": "postfix"})

    def test_all_companies_uses_the_row_without_a_company(self):
        set_selected_company("all")

        self.assertEqual(PayrollSettings.for_selected_company(), self.global_row)

    def test_no_company_selected_and_no_row_without_a_company(self):
        self.global_row.delete()

        self.assertEqual(PayrollSettings.for_selected_company(), self.company_row)

    def test_no_rows(self):
        PayrollSettings.objects.all().delete()

        self.assertIsNone(PayrollSettings.for_selected_company())

    def test_no_rows_means_dollars(self):
        PayrollSettings.objects.all().delete()

        self.assertEqual(PayrollSettings.currency_for_selected_company(), "$")

    def test_report_exports_use_the_selected_company(self):
        set_selected_company(str(self.company.id))

        self.assertEqual(_currency_format(), ("£", "prefix"))

    def test_emailed_payslips_use_the_selected_company(self):
        """
        MailSendThread renders each payslip PDF in its own thread, which
        starts without the request's selected company. Its run() is called
        here in an empty context -- what a new thread gets -- so it still
        sees this test's rows.
        """
        set_selected_company(str(self.company.id))
        request = RequestFactory().get("/")
        payslip = SimpleNamespace(
            id=1,
            employee_id=MagicMock(),
            get_payslip_title=lambda: "Payslip",
            get_name=lambda: "Employee",
        )
        mail = MailSendThread(request, {1: {"instances": [payslip]}}, [1])
        seen = []

        def payslip_pdf(request, payslip_id):
            seen.append(PayrollSettings.currency_for_selected_company())
            return HttpResponse(b"")

        with patch("payroll.threadings.mail.payslip_pdf", payslip_pdf), patch(
            "payroll.threadings.mail.render_to_string", return_value=""
        ), patch("payroll.threadings.mail.EmailMessage"), patch(
            "payroll.threadings.mail.ConfiguredEmailBackend"
        ):
            Context().run(mail.run)

        self.assertEqual(seen, ["£"])


class RememberedPerRequestTests(TestCase):
    """for_selected_company() is looked up once per request and company."""

    def setUp(self):
        set_selected_company(None)
        self.company = Company.objects.create(company="Company A", hq=True)
        self.company_row = PayrollSettings.objects.create(
            currency_symbol="£", position="prefix", company_id=self.company
        )
        _thread_locals.request = self._request()
        set_selected_company(str(self.company.id))

    def tearDown(self):
        set_selected_company(None)
        _thread_locals.request = None

    @staticmethod
    def _request():
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        return request

    def test_looked_up_once(self):
        # The first call also warms Django's ContentType cache, which the
        # filter's get_horilla_model_class() hits once per process.
        self.assertEqual(currency_symbol_position("100"), "£ 100")
        with self.assertNumQueries(0):
            self.assertEqual(currency_symbol_position("100"), "£ 100")
            self.assertEqual(PayrollSettings.currency_for_selected_company(), "£")

    def test_per_company(self):
        PayrollSettings.for_selected_company()
        set_selected_company(None)
        PayrollSettings.objects.create(currency_symbol="$", company_id=None)

        self.assertEqual(PayrollSettings.currency_for_selected_company(), "$")

    def test_saving_or_deleting_settings_shows_at_once(self):
        PayrollSettings.for_selected_company()
        self.company_row.currency_symbol = "€"
        self.company_row.save()
        self.assertEqual(PayrollSettings.currency_for_selected_company(), "€")

        PayrollSettings.objects.all().delete()  # bulk, as some tests do
        self.assertEqual(PayrollSettings.currency_for_selected_company(), "$")

    def test_not_remembered_between_requests(self):
        PayrollSettings.for_selected_company()
        _thread_locals.request = self._request()
        with self.assertNumQueries(1):
            PayrollSettings.for_selected_company()
