"""Mail sent by an employee without an email keeps the configured sender.

Sender and reply-to headers were built as "Name <address>" from the signed-in
employee's address; without one the header could not be built and the mail
failed to send.
"""

from django.core.cache import cache
from django.core.mail import EmailMessage
from django.test import RequestFactory, TestCase

from base.backends import ConfiguredEmailBackend
from base.models import DynamicEmailConfiguration
from horilla.horilla_middlewares import _thread_locals
from horilla.testkit import make_company, make_employee, make_user


class MailHeadersWithoutEmailTests(TestCase):
    def setUp(self):
        company = make_company("Co")
        DynamicEmailConfiguration.objects.create(
            host="localhost",
            port=25,
            from_email="hr@test.horilla",
            display_name="HR",
            is_primary=True,
            use_dynamic_display_name=True,
        )
        user = make_user("sam")
        make_employee(company=company, email="", user=user)
        request = RequestFactory().get("/")
        request.user = user
        _thread_locals.request = request
        self.addCleanup(setattr, _thread_locals, "request", None)
        self.addCleanup(cache.clear)

    def test_mail_keeps_the_configured_sender_and_no_reply_to(self):
        ConfiguredEmailBackend()
        built = EmailMessage("Hello", "Body", to=["someone@test.horilla"]).message()
        self.assertIn("hr@test.horilla", built["From"])
        self.assertIsNone(built["Reply-To"])
