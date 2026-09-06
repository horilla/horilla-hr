"""The onboarding portal token must not be served over the API.

OnboardingPortal.token is not descriptive data -- it is the credential.
onboarding/urls.py routes user-creation, profile-view, employee-creation and
employee-bank-details on `<str:token>` alone, and those views carry no
authentication decorator, so holding the token is what grants access to
complete a candidate's onboarding, bank details included. It is generated
server-side with secrets.token_hex.

`fields = "__all__"` put it in every response body, where it reaches request
logs, reverse proxies and browser history -- a far wider surface than the row
it belongs to.

These use SimpleTestCase and an unsaved instance: both assertions are about
the serializer's field map, so building a Candidate (which needs a
Recruitment with matching open_positions) would add a fixture that can break
for reasons unrelated to what is being checked.
"""

from django.test import SimpleTestCase

from horilla_api.api_serializers.onboarding.serializers import (
    OnboardingPortalSerializer,
)


class OnboardingPortalTokenSerialisationTests(SimpleTestCase):
    def test_token_is_not_in_the_serialised_output(self):
        """The token must not appear in what the serializer emits.

        Asserted through the serializer's field map rather than by
        serializing an instance: OnboardingPortal.candidate_id is a required
        OneToOne, and get_candidate_id dereferences it, so producing output
        needs a saved Candidate -- which needs a Recruitment with matching
        open_positions. That fixture can break for reasons that have nothing
        to do with the token, and DRF omits every write_only field from
        to_representation, so the field map is the same guarantee.
        """
        fields = OnboardingPortalSerializer().get_fields()

        self.assertTrue(
            fields["token"].write_only,
            "token is readable, so it is emitted in every response body",
        )

    def test_token_remains_writable(self):
        """write_only, not excluded: the create path still sets it.

        Excluding the field instead would make the serializer silently drop
        a supplied token, leaving a portal row whose URL cannot be built.
        """
        fields = OnboardingPortalSerializer().get_fields()

        self.assertIn("token", fields)
        self.assertFalse(
            fields["token"].read_only, "token must still accept a value on write"
        )
