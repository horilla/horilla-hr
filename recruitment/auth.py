from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import AnonymousUser

from .models import Candidate


class CandidateAuthenticationBackend(BaseBackend):
    """
    Candidates log in to the application tracking page with their email and the
    password from their invitation mail (see `Candidate.issue_portal_password`).
    """

    def authenticate(self, request, username=None, password=None):
        email = (username or "").strip().lower()
        if not email or not password:
            return None

        candidates = Candidate.objects.filter(email__iexact=email)
        for candidate in candidates:
            if candidate.check_portal_password(password):
                return candidate
        return None

    def get_user(self, user_id):
        try:
            return Candidate.objects.get(pk=user_id)
        except Candidate.DoesNotExist:
            return AnonymousUser()
