"""Emailed payslips are marked sent only when they were sent.

Sending payslips marked every selected payslip as sent once any mail went,
including those of employees without an email, who were sent nothing.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from horilla.horilla_middlewares import _thread_locals
from payroll.threadings.mail import MailSendThread


def payslip(payslip_id, mail):
    return SimpleNamespace(
        id=payslip_id,
        employee_id=SimpleNamespace(get_mail=lambda: mail),
        get_payslip_title=lambda: "Payslip",
        get_name=lambda: "Employee",
    )


class PayslipMailMarkingTests(SimpleTestCase):
    def tearDown(self):
        _thread_locals.request = None

    def send(self, result_dict, sent=1):
        request = RequestFactory().get("/")
        request.user = MagicMock()
        thread = MailSendThread(request, result_dict, list(result_dict))
        message = MagicMock()
        message.return_value.send.return_value = sent
        with patch(
            "payroll.threadings.mail.payslip_pdf", return_value=HttpResponse(b"")
        ), patch("payroll.threadings.mail.render_to_string", return_value=""), patch(
            "payroll.threadings.mail.EmailMessage", message
        ), patch(
            "payroll.threadings.mail.ConfiguredEmailBackend"
        ), patch(
            "payroll.threadings.mail.set_selected_company"
        ), patch(
            "payroll.threadings.mail.Payslip"
        ) as model:
            thread.run()
        return message, model

    def test_an_employee_without_an_email_is_skipped_and_not_marked_sent(self):
        message, model = self.send(
            {
                1: {"instances": [payslip(1, "a@test.horilla")]},
                2: {"instances": [payslip(2, None)]},
            }
        )
        self.assertEqual(message.call_count, 1)
        self.assertEqual(message.call_args.args[3], ["a@test.horilla"])
        model.objects.filter.assert_called_once_with(id__in=[1])

    def test_a_mail_that_was_not_sent_is_not_marked_sent(self):
        _message, model = self.send(
            {1: {"instances": [payslip(1, "a@test.horilla")]}}, sent=0
        )
        model.objects.filter.assert_not_called()
