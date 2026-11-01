"""Password reset links must point at the host the user is actually using.

`PassWordResetForm.save()` built the link from `get_current_site(request)`.
That resolves through django.contrib.sites, and the only row a normal install
has is the one the framework's own migration creates -- domain
``example.com``. Nothing in Horilla ever updates it, so every reset mail sent
a link to

    http://example.com/reset/<uid>/<token>/

while the product itself was reachable on the real host. Leave-request mail
never had the problem: it reads the host straight off the request
(``leave/threading.py``), which is what the form now does as well.

These drive the real `save()` and capture the context handed to `send_mail`,
rather than re-deriving the logic in the test -- a test that reimplements the
branch it is checking would pass against the broken code too.

Reported as https://github.com/horilla/horilla-hr/issues/1241 by @KerelOlivier.
"""

from django.test import RequestFactory, TestCase, override_settings

from base.forms import PassWordResetForm
from horilla.testkit import make_company, make_employee


class _CapturingResetForm(PassWordResetForm):
    """Real save(); send_mail captured instead of dispatched."""

    def __init__(self, username):
        super().__init__(data={"email": username})
        self.captured_context = None

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        self.captured_context = context


# The hosts below are invented for the test. request.get_host() validates
# against ALLOWED_HOSTS and raises DisallowedHost otherwise -- which is the
# behaviour being relied on in production, and the reason CI (which sets
# ALLOWED_HOSTS=localhost,127.0.0.1) rejected them. Declare them here rather
# than letting the suite depend on whatever the environment happens to allow.
@override_settings(
    ALLOWED_HOSTS=[
        "hr.acme-corp.test",
        "real-host.test",
        "ignored.test",
        "localhost",
        "127.0.0.1",
        "testserver",
    ]
)
class PasswordResetDomainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = make_company("Reset Co")
        cls.employee = make_employee(
            company=cls.company,
            email="resetme@test.horilla",
            first_name="Reset",
            last_name="Me",
        )
        cls.username = cls.employee.employee_user_id.username

    def _send(self, host, **extra):
        form = _CapturingResetForm(self.username)
        self.assertTrue(form.is_valid(), form.errors)
        request = RequestFactory().post("/forgot-password/", HTTP_HOST=host)
        form.save(request=request, **extra)
        self.assertIsNotNone(form.captured_context, "save() did not reach send_mail")
        return form.captured_context

    def test_link_uses_the_request_host_not_example_com(self):
        context = self._send("hr.acme-corp.test")
        self.assertEqual(context["domain"], "hr.acme-corp.test")
        self.assertNotEqual(
            context["domain"],
            "example.com",
            "the reset link pointed at django.contrib.sites' default row",
        )

    def test_site_name_is_also_the_real_host(self):
        """site_name appears in the mail body, so it must not say example.com."""
        context = self._send("hr.acme-corp.test")
        self.assertEqual(context["site_name"], "hr.acme-corp.test")

    def test_a_port_in_the_host_is_preserved(self):
        """A Docker or dev install on a non-default port must keep it."""
        context = self._send("localhost:8000")
        self.assertEqual(context["domain"], "localhost:8000")

    def test_explicit_domain_override_still_wins(self):
        context = self._send("ignored.test", domain_override="forced.test")
        self.assertEqual(context["domain"], "forced.test")
        self.assertEqual(context["site_name"], "forced.test")

    def test_unvalidated_forwarded_host_is_not_trusted(self):
        """X-Forwarded-Host is attacker-controllable: reset-link poisoning.

        request.get_host() is validated against ALLOWED_HOSTS and ignores the
        header unless USE_X_FORWARDED_HOST is set, which is what we want for a
        link that grants account access.
        """
        context = self._send("real-host.test", **{})
        self.assertEqual(context["domain"], "real-host.test")

        form = _CapturingResetForm(self.username)
        self.assertTrue(form.is_valid(), form.errors)
        request = RequestFactory().post(
            "/forgot-password/",
            HTTP_HOST="real-host.test",
            HTTP_X_FORWARDED_HOST="attacker.test",
        )
        form.save(request=request)
        self.assertEqual(
            form.captured_context["domain"],
            "real-host.test",
            "an unvalidated X-Forwarded-Host must not steer the reset link",
        )
