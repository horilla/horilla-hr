"""
outlook_auth/backeds.py
"""

import base64
import logging

from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend

from base.models import EmailLog
from horilla.horilla_middlewares import _thread_locals
from outlook_auth import models
from outlook_auth.views import send_outlook_email

logger = logging.getLogger(__name__)


class OutlookBackend(EmailBackend):
    """
    OutlookBackend
    """

    api: models.AzureApi = None

    def __init__(self, *args, **kwargs):
        request = getattr(_thread_locals, "request", None)
        self.request = request
        company = None
        if request and not request.user.is_anonymous:
            company = request.user.employee_get.get_company()
        api = models.AzureApi.objects.filter(company=company).first()
        if api is None:
            api = models.AzureApi.objects.filter(is_primary=True).first()
        self.api = api

    def send_messages(self, email_messages):
        response = super().send_messages(email_messages)
        return response

    @property
    def dynamic_from_email_with_display_name(self):
        if not self.request.user:
            return f"{self.api.outlook_display_name}<{self.api.outlook_email}>"
        employee = self.request.user.employee_get
        if not employee.get_email():
            return f"{self.api.outlook_display_name}<{self.api.outlook_email}>"
        full_name = employee.get_full_name()
        return f"{full_name} <{employee.get_email()}>"


actual_init = EmailMessage.__init__


def __init__(
    self: EmailMessage,
    subject="",
    body="",
    from_email=None,
    to=[],
    bcc=[],
    connection=None,
    attachments=None,
    headers=None,
    cc=[],
    reply_to=None,
    *args,
    **kwargs,
):
    """
    custom __init_method to override
    """
    request = getattr(_thread_locals, "request", None)
    self.request = request

    if request:
        try:
            if request.user.employee_get.email:
                display_email_name = f"{request.user.employee_get.get_full_name()} <{request.user.employee_get.email}>"
                from_email = display_email_name if not from_email else from_email
                reply_to = [display_email_name] if not reply_to else reply_to

        except Exception as e:
            logger.error(e)
    self.subject = subject
    self.body = body
    self.from_email = from_email
    self.to = to
    self.cc = cc
    self.bcc = bcc
    self.attachments = attachments
    self.headers = headers
    self.reply_to = reply_to

    actual_init(
        self,
        subject=subject,
        body=body,
        from_email=from_email,
        to=to,
        bcc=bcc,
        connection=connection,
        attachments=attachments,
        headers=headers,
        cc=cc,
        reply_to=reply_to,
    )

    # Prepare email data for Outlook API


def send_mail(self, *args, **kwargs):
    """
    Sent mail
    """

    self.email_data = {
        "message": {
            "subject": self.subject,
            "body": {
                "contentType": "HTML" if self.content_subtype == "html" else "Text",
                "content": self.body,
            },
            "toRecipients": [
                {"emailAddress": {"address": recipient}} for recipient in self.to
            ],
            "ccRecipients": [
                {"emailAddress": {"address": recipient}} for recipient in self.cc
            ],
            "bccRecipients": [
                {"emailAddress": {"address": recipient}} for recipient in self.bcc
            ],
        },
    }
    if self.request and not self.request.user.is_anonymous:
        reply_to = self.request.user.employee_get.get_email()
        if reply_to:
            self.email_data["message"]["replyTo"] = [
                {"emailAddress": {"address": reply_to}}
            ]

    if self.attachments:
        outlook_attachments = []
        for attachment in self.attachments:
            if isinstance(attachment, tuple):
                filename, content, mimetype = attachment
                if hasattr(content, "read"):
                    content = content.read()

                # Encode contentBytes using base64
                if isinstance(content, bytes):
                    content_bytes = base64.b64encode(content).decode("utf-8")
                else:
                    content_bytes = content

                outlook_attachments.append(
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": filename,
                        "contentType": mimetype,
                        "contentBytes": content_bytes,
                    }
                )
        self.email_data["message"]["attachments"] = outlook_attachments
    response, _ = send_outlook_email(self.request, self.email_data)

    email_log = EmailLog(
        subject=self.subject,
        from_email=self.from_email,
        to=self.to,
        body=self.body,
        status="sent" if response else "failed",
    )
    email_log.save()


EmailMessage.__init__ = __init__
EmailMessage.send = send_mail
