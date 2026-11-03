"""
The client IP behind a reverse proxy (horilla.client_ip).

X-Forwarded-For is believed only on a connection from a trusted proxy, and
only from the right: nginx appends the address it saw, so anything a client
wrote itself sits further left and is never used.
"""

from unittest import mock

from django.test import RequestFactory, SimpleTestCase, override_settings

from horilla import client_ip as client_ip_module
from horilla.client_ip import client_ip

NGINX = "172.19.0.3"


def ip(remote, xff=None):
    meta = {"REMOTE_ADDR": remote}
    if xff is not None:
        meta["HTTP_X_FORWARDED_FOR"] = xff
    return client_ip(RequestFactory().get("/login/", **meta))


class ClientIpTests(SimpleTestCase):
    def setUp(self):
        client_ip_module._resolved.clear()

    @override_settings(HORILLA_TRUSTED_PROXIES=[])
    def test_with_no_trusted_proxy_the_header_is_ignored(self):
        self.assertEqual(ip("203.0.113.9", "10.20.30.7"), "203.0.113.9")

    @override_settings(HORILLA_TRUSTED_PROXIES=["172.16.0.0/12"])
    def test_behind_the_proxy_the_appended_address_is_the_client(self):
        self.assertEqual(ip(NGINX, "192.168.1.50"), "192.168.1.50")

    @override_settings(HORILLA_TRUSTED_PROXIES=["172.16.0.0/12"])
    def test_a_client_written_header_is_never_used(self):
        self.assertEqual(ip(NGINX, "8.8.8.8, 192.168.1.50"), "192.168.1.50")

    @override_settings(HORILLA_TRUSTED_PROXIES=["172.16.0.0/12"])
    def test_a_direct_connection_is_not_believed(self):
        # Port 8000 published past nginx: the header comes from the client.
        self.assertEqual(ip("192.168.1.50", "8.8.8.8"), "192.168.1.50")

    @override_settings(HORILLA_TRUSTED_PROXIES=["172.16.0.0/12"])
    def test_no_header_from_the_proxy_means_the_proxy(self):
        self.assertEqual(ip(NGINX), NGINX)
        self.assertEqual(ip(NGINX, "not-an-ip"), NGINX)

    @override_settings(HORILLA_TRUSTED_PROXIES=["nginx"])
    def test_a_hostname_is_resolved(self):
        with mock.patch(
            "horilla.client_ip.socket.getaddrinfo",
            return_value=[(None, None, None, "", (NGINX, 0))],
        ):
            self.assertEqual(ip(NGINX, "192.168.1.50"), "192.168.1.50")
            self.assertEqual(ip("172.19.0.9", "8.8.8.8"), "172.19.0.9")

    @override_settings(HORILLA_TRUSTED_PROXIES=["nginx"])
    def test_an_unknown_hostname_trusts_nothing(self):
        with mock.patch(
            "horilla.client_ip.socket.getaddrinfo", side_effect=OSError("no such host")
        ):
            self.assertEqual(ip(NGINX, "8.8.8.8"), NGINX)

    @override_settings(HORILLA_TRUSTED_PROXIES=["172.16.0.0/12", "10.0.0.0/8"])
    def test_a_chain_of_trusted_proxies_is_followed(self):
        # client -> load balancer (10.0.0.4) -> nginx
        self.assertEqual(ip(NGINX, "8.8.8.8, 81.2.69.160, 10.0.0.4"), "81.2.69.160")
