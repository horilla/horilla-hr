from django.contrib import admin

from .models import OidcProvider


@admin.register(OidcProvider)
class OidcProviderAdmin(admin.ModelAdmin):
    # The raw Fernet ciphertext: editing it here would make the secret
    # undecryptable. Set the secret through SSO settings instead.
    exclude = ("_client_secret",)
