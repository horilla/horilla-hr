"""
email_backend.py

This module is used to write email backends
"""

import importlib
import logging

from django.core.cache import cache
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend

from base.email_redaction import get_current_company, redact_credential_body
from base.models import DynamicEmailConfiguration, EmailLog
from horilla import settings
from horilla.horilla_middlewares import _thread_locals

logger = logging.getLogger(__name__)


class DefaultHorillaMailBackend(EmailBackend):
    def __init__(
        self,
        host=None,
        port=None,
        username=None,
        password=None,
        use_tls=None,
        fail_silently=None,
        use_ssl=None,
        timeout=None,
        ssl_keyfile=None,
        ssl_certfile=None,
        **kwargs,
    ):
        self.configuration = self.get_dynamic_email_config()
        ssl_keyfile = (
            getattr(self.configuration, "ssl_keyfile", None)
            if self.configuration
            else ssl_keyfile or getattr(settings, "ssl_keyfile", None)
        )
        ssl_certfile = (
            getattr(self.configuration, "ssl_certfile", None)
            if self.configuration
            else ssl_certfile or getattr(settings, "ssl_certfile", None)
        )

        super().__init__(
            host=self.dynamic_host,
            port=self.dynamic_port,
            username=self.dynamic_username,
            password=self.dynamic_password,
            use_tls=self.dynamic_use_tls,
            fail_silently=self.dynamic_fail_silently,
            use_ssl=self.dynamic_use_ssl,
            timeout=self.dynamic_timeout,
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile,
            **kwargs,
        )

    @staticmethod
    def get_dynamic_email_config():
        request = getattr(_thread_locals, "request", None)
        company = None
        if request and not request.user.is_anonymous:
            company = request.user.employee_get.get_company()
        configuration = DynamicEmailConfiguration.objects.filter(
            company_id=company
        ).first()
        if configuration is None:
            configuration = DynamicEmailConfiguration.objects.filter(
                is_primary=True
            ).first()
        if configuration:
            display_email_name = (
                f"{configuration.display_name} <{configuration.from_email}>"
            )

            user_id = ""
            if request:
                if (
                    configuration.use_dynamic_display_name
                    and request.user.is_authenticated
                ):
                    display_email_name = f"{request.user.employee_get.get_full_name()} <{request.user.employee_get.get_email()}>"
                if request.user.is_authenticated:
                    user_id = request.user.pk
                    reply_to = [
                        f"{request.user.employee_get.get_full_name()} <{request.user.employee_get.get_email()}>",
                    ]
                    cache.set(f"reply_to{request.user.pk}", reply_to)

            cache.set(f"dynamic_display_name{user_id}", display_email_name)

        return configuration

    @property
    def dynamic_host(self):
        return (
            self.configuration.host
            if self.configuration
            else getattr(settings, "EMAIL_HOST", None)
        )

    @property
    def dynamic_port(self):
        return (
            self.configuration.port
            if self.configuration
            else getattr(settings, "EMAIL_PORT", None)
        )

    @property
    def dynamic_username(self):
        return (
            self.configuration.username
            if self.configuration
            else getattr(settings, "EMAIL_HOST_USER", None)
        )

    @property
    def dynamic_mail_sent_from(self):
        return (
            self.configuration.from_email
            if self.configuration
            else getattr(settings, "DEFAULT_FROM_EMAIL", None)
        )

    @property
    def dynamic_display_name(self):
        return self.configuration.display_name if self.configuration else None

    @property
    def dynamic_from_email_with_display_name(self):
        if self.dynamic_display_name and self.dynamic_mail_sent_from:
            return f"{self.dynamic_display_name} <{self.dynamic_mail_sent_from}>"
        return self.dynamic_mail_sent_from or getattr(
            settings, "DEFAULT_FROM_EMAIL", ""
        )

    @property
    def dynamic_password(self):
        return (
            self.configuration.password
            if self.configuration
            else getattr(settings, "EMAIL_HOST_PASSWORD", None)
        )

    @property
    def dynamic_use_tls(self):
        return (
            self.configuration.use_tls
            if self.configuration
            else getattr(settings, "EMAIL_USE_TLS", None)
        )

    @property
    def dynamic_fail_silently(self):
        return (
            self.configuration.fail_silently
            if self.configuration
            else getattr(settings, "EMAIL_FAIL_SILENTLY", True)
        )

    @property
    def dynamic_use_ssl(self):
        return (
            self.configuration.use_ssl
            if self.configuration
            else getattr(settings, "EMAIL_USE_SSL", None)
        )

    @property
    def dynamic_timeout(self):
        return (
            self.configuration.timeout
            if self.configuration
            else getattr(settings, "EMAIL_TIMEOUT", None)
        )


EMAIL_BACKEND = getattr(settings, "EMAIL_BACKEND", "")


BACKEND_CLASS: EmailBackend = DefaultHorillaMailBackend
default = "base.backends.ConfiguredEmailBackend"

setattr(BACKEND_CLASS, "send_messages", DefaultHorillaMailBackend.send_messages)

if EMAIL_BACKEND and EMAIL_BACKEND != default:
    module_path, class_name = EMAIL_BACKEND.rsplit(".", 1)
    module = importlib.import_module(module_path)
    BACKEND_CLASS = getattr(module, class_name)


class ConfiguredEmailBackend(BACKEND_CLASS):

    def send_messages(self, email_messages):
        response = super(BACKEND_CLASS, self).send_messages(email_messages)
        for message in email_messages:
            from_email = (
                self.dynamic_from_email_with_display_name
                or message.from_email
                or getattr(settings, "DEFAULT_FROM_EMAIL", "")
            )
            email_log = EmailLog(
                subject=message.subject,
                from_email=from_email,
                to=message.to,
                body=redact_credential_body(message.subject, message.body),
                status="sent" if response else "failed",
                company_id=get_current_company(),
            )
            email_log.save()
        return response


if EMAIL_BACKEND != default:
    from_mail = getattr(settings, "DEFAULT_FROM_EMAIL", "example@gmail.com")
    username = getattr(settings, "EMAIL_HOST_USER", "example@gmail.com")
    ConfiguredEmailBackend.dynamic_username = from_mail
    ConfiguredEmailBackend.dynamic_from_email_with_display_name = from_mail


__all__ = ["ConfiguredEmailBackend"]


message_init = EmailMessage.__init__


def new_init(
    self,
    subject="",
    body="",
    from_email=None,
    to=None,
    bcc=None,
    connection=None,
    attachments=None,
    headers=None,
    cc=None,
    reply_to=None,
):
    """
    custom __init_method to override
    """
    request = getattr(_thread_locals, "request", None)
    DefaultHorillaMailBackend()
    user_id = ""
    if request and request.user and request.user.is_authenticated:
        user_id = request.user.pk
        reply_to = cache.get(f"reply_to{user_id}") if not reply_to else reply_to

    if not from_email:
        from_email = cache.get(f"dynamic_display_name{user_id}")

    message_init(
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


EmailMessage.__init__ = new_init
