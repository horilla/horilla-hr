from django.apps import AppConfig


class HorillaIdentityConfig(AppConfig):
    """
    Shared foundation for identity-provider integrations (SCIM, SAML, OIDC).

    Holds the link between an external identity and a Horilla user, and the
    provisioning service that is the only place IdP-driven code is allowed to
    create, change, deactivate or remove employees.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "horilla_identity"
    verbose_name = "Identity"
