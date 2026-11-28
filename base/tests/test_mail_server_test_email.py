"""The mail server's "Send test mail" reports what really happened.

It connected with the signed-in user's company (or primary) configuration and
only then swapped in the one being tested, which by then changed just the
From address: testing a second server sent through the first. And it ignored
the result of the send, so a server set to fail silently always showed
"Mail sent successfully".
"""

import socketserver
import threading
from unittest import mock

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import TestCase

from base.models import DynamicEmailConfiguration
from horilla.testkit import make_company, make_employee, make_user

URL = "/settings/mail-server-test-email/"


class SMTPCatcher(socketserver.ThreadingTCPServer):
    """A local SMTP server that accepts every message and counts them."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        self.received = []
        catcher = self

        class Handler(socketserver.StreamRequestHandler):
            def reply(self, line):
                self.wfile.write((line + "\r\n").encode())

            def handle(self):
                self.reply("220 catcher")
                while line := self.rfile.readline().decode(errors="replace"):
                    verb = line.strip().split(" ")[0].upper()
                    if verb == "EHLO":
                        self.wfile.write(b"250-catcher\r\n250 8BITMIME\r\n")
                    elif verb == "DATA":
                        self.reply("354 go on")
                        data = b""
                        while (chunk := self.rfile.readline()) != b".\r\n":
                            data += chunk
                        catcher.received.append(data)
                        self.reply("250 queued")
                    elif verb == "QUIT":
                        self.reply("221 bye")
                        return
                    else:
                        self.reply("250 ok")

        super().__init__(("127.0.0.1", 0), Handler)
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def stop(self):
        self.shutdown()
        self.server_close()


def closed_port():
    """A local port with nothing listening on it."""
    with socketserver.TCPServer(("127.0.0.1", 0), None) as probe:
        return probe.server_address[1]


class MailServerTestEmailTests(TestCase):
    def setUp(self):
        self.company = make_company("Co")
        user = make_user("admin", is_superuser=True)
        make_employee(company=self.company, email="admin@test.horilla", user=user)
        self.client.force_login(user)
        self.addCleanup(cache.clear)

    def catcher(self):
        catcher = SMTPCatcher()
        self.addCleanup(catcher.stop)
        return catcher

    def server(self, port, **fields):
        return DynamicEmailConfiguration.objects.create(
            host="127.0.0.1",
            port=port,
            from_email="hr@test.horilla",
            use_tls=False,
            use_ssl=False,
            timeout=5,
            **fields,
        )

    def send_test(self, configuration):
        response = self.client.post(
            f"{URL}?instance_id={configuration.pk}",
            {"to_email": "someone@test.horilla"},
            HTTP_HX_REQUEST="true",
        )
        return [str(m) for m in get_messages(response.wsgi_request)]

    def test_a_working_server_sends_the_test_mail(self):
        catcher = self.catcher()
        server = self.server(catcher.port, is_primary=True, company_id=self.company)
        self.assertEqual(self.send_test(server), ["Mail sent successfully"])
        self.assertEqual(len(catcher.received), 1)

    def test_a_failing_server_set_to_fail_silently_is_reported(self):
        server = self.server(
            closed_port(), fail_silently=True, is_primary=True, company_id=self.company
        )
        messages = self.send_test(server)
        self.assertNotIn("Mail sent successfully", messages)
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith("Something went wrong"), messages)

    def test_the_server_being_tested_is_the_one_that_sends(self):
        in_use = self.catcher()
        tested = self.catcher()
        self.server(in_use.port, is_primary=True, company_id=self.company)
        second = self.server(tested.port)
        self.assertEqual(self.send_test(second), ["Mail sent successfully"])
        self.assertEqual((len(in_use.received), len(tested.received)), (0, 1))

    def test_a_failing_second_server_is_not_reported_as_working(self):
        in_use = self.catcher()
        self.server(in_use.port, is_primary=True, company_id=self.company)
        broken = self.server(closed_port())
        messages = self.send_test(broken)
        self.assertNotIn("Mail sent successfully", messages)
        self.assertEqual(in_use.received, [])

    def test_a_backend_that_sends_nothing_without_an_error_is_reported(self):
        catcher = self.catcher()
        server = self.server(catcher.port, is_primary=True, company_id=self.company)
        with mock.patch(
            "base.backends.ConfiguredEmailBackend.send_messages", return_value=0
        ):
            messages = self.send_test(server)
        self.assertEqual(messages, ["The mail server did not accept the mail."])
