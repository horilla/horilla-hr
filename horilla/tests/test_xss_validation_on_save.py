"""XSS validation must run on every write path, not only through a ModelForm.

GHSA-rf47-2qgf-qq4j: `has_xss` is applied in `HorillaModel.clean_fields()`,
which only reaches a save through `full_clean()` -- and `full_clean()` was
commented out of `HorillaModel.save()` during an unrelated CBV merge. Every
DRF `serializer.save()` and every direct `.save()` then stored raw markup,
which combined with `|safe` rendering re-opened stored XSS.

That made it a bypass of CVE-2025-59525 (which added `has_xss`) and re-opened
the ticket-comment sink of CVE-2025-59832. The reported chain was: any
authenticated employee comments on a ticket, an administrator opens it, the
payload runs in the admin's session and exfiltrates password hashes through
the export endpoint.

These tests exercise `.save()` directly, which is the path that was
unprotected -- a test going through a ModelForm would have passed throughout.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from helpdesk.models import Comment


class XSSValidationOnSaveTests(TestCase):
    # The payload from the advisory, plus shapes that do not rely on <script>.
    PAYLOADS = [
        "<img src=x onerror=\"fetch('/api/export')\">",
        "<script>alert(1)</script>",
        "<svg/onload=alert(1)>",
        "<body onload=alert(1)>",
        "<details open ontoggle=alert(1)>",
    ]

    def test_direct_save_rejects_xss(self):
        """The path the advisory used. Before the fix this stored raw markup."""
        for payload in self.PAYLOADS:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    Comment(comment=payload).save()

    def test_rejection_names_the_offending_field(self):
        """An operator seeing this needs to know which field was refused."""
        with self.assertRaises(ValidationError) as caught:
            Comment(comment="<script>alert(1)</script>").save()
        self.assertIn("comment", caught.exception.message_dict)

    def test_legitimate_rich_text_still_saves(self):
        """The check must not break the editors these fields are written in.

        A validator that rejects ordinary formatting would be reverted within
        a week, which is how the original one came to be disabled.
        """
        for value in (
            "<p>Plain paragraph</p>",
            "<p>With <strong>bold</strong> and <em>italic</em></p>",
            '<a href="https://example.com">a link</a>',
            '<img src="https://example.com/shot.png" alt="screenshot">',
            "<ul><li>one</li><li>two</li></ul>",
            "no markup at all",
        ):
            with self.subTest(value=value):
                comment = Comment(comment=value)
                comment.clean_fields()  # must not raise

    def test_xss_exempt_fields_are_still_honoured(self):
        """Models that legitimately store markup opt out by name.

        horilla_automations and horilla_views both declare xss_exempt_fields;
        calling clean_fields() from save() must not start rejecting those.
        """
        comment = Comment(comment="<script>alert(1)</script>")
        comment.xss_exempt_fields = ["comment"]
        comment.clean_fields()  # must not raise
