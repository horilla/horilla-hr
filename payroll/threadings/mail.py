"""
mail.py

This module is used handle mail sent in thread
"""

import logging
from threading import Thread

from django.core.mail import EmailMessage
from django.template.loader import render_to_string

from base.backends import ConfiguredEmailBackend
from employee.models import EmployeeWorkInformation
from horilla.horilla_middlewares import get_selected_company, set_selected_company
from payroll.models.models import Payslip
from payroll.views.views import payslip_pdf

logger = logging.getLogger(__name__)


class MailSendThread(Thread):
    """
    MailSend
    """

    def __init__(self, request, result_dict, ids):
        Thread.__init__(self)
        self.result_dict = result_dict
        self.ids = ids
        self.request = request
        self.host = request.get_host()
        self.protocol = "https" if request.is_secure() else "http"
        # The thread starts without the request's selected company, which the
        # payslip PDF's currency (and every company-scoped query) depends on.
        self.company_id = get_selected_company()

    def run(self) -> None:
        super().run()
        set_selected_company(self.company_id)
        for record in list(self.result_dict.values()):
            html_message = render_to_string(
                "payroll/mail_templates/default.html",
                {
                    "record": record,
                    "host": self.host,
                    "protocol": self.protocol,
                },
                request=self.request,
            )
            attachments = []
            for instance in record["instances"]:
                response = payslip_pdf(self.request, instance.id)
                attachments.append(
                    (
                        f"{instance.get_payslip_title()}.pdf",
                        response.content,
                        "application/pdf",
                    )
                )
            employee = record["instances"][0].employee_id
            email_backend = ConfiguredEmailBackend()
            display_email_name = email_backend.dynamic_from_email_with_display_name
            if self.request:
                try:
                    display_email_name = f"{self.request.user.employee_get.get_full_name()} <{self.request.user.employee_get.email}>"
                except:
                    logger.error(Exception)

            email = EmailMessage(
                f"Hello, {record['instances'][0].get_name()} Your Payslips is Ready!",
                html_message,
                display_email_name,
                [employee.get_mail()],
                reply_to=[display_email_name],
            )
            email.attachments = attachments

            # Send the email
            email.content_subtype = "html"
            try:
                email.send()
                Payslip.objects.filter(id__in=self.ids).update(sent_to_employee=True)
            except Exception as e:
                logger.exception(e)

        return
