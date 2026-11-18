"""
leave_request_bulk_approve must carry its own auth decorators.

They were once attached to the _posted_ids helper just above it, which left
the view itself open: an anonymous POST reached request.user.employee_get on
an AnonymousUser and returned a 500.
"""

from django.test import TestCase
from django.urls import reverse


class LeaveRequestBulkApproveAuthTests(TestCase):
    def test_anonymous_post_is_redirected_to_login(self):
        url = reverse("leave-requests-bulk-approve")
        response = self.client.post(url, {"ids": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
