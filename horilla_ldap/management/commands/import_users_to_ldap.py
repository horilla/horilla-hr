import base64
import hashlib

from django.core.management.base import BaseCommand
from ldap3 import ALL, ALL_ATTRIBUTES, Connection, Server

from employee.models import Employee
from horilla_ldap.models import LDAPSettings


class Command(BaseCommand):
    help = "Import users from Django to LDAP using LDAP settings from the database"

    def handle(self, *args, **kwargs):
        # Get LDAP settings from the database
        settings = LDAPSettings.objects.first()
        if not settings:
            self.stdout.write(self.style.ERROR("LDAP settings are not configured."))
            return

        # Fetch LDAP server details from settings
        ldap_server = settings.ldap_server
        bind_dn = settings.bind_dn
        bind_password = settings.bind_password
        base_dn = settings.base_dn

        if not all([ldap_server, bind_dn, bind_password, base_dn]):
            self.stdout.write(
                self.style.ERROR(
                    "LDAP settings are incomplete. Please check your configuration."
                )
            )
            return

        # Connect to the LDAP server
        server = Server(ldap_server, get_info=ALL)

        try:
            conn = Connection(server, bind_dn, bind_password, auto_bind=True)

            # Fetch all users from Django
            users = Employee.objects.all()

            for user in users:
                if not user.employee_user_id:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping user {user} due to missing employee_user_id"
                        )
                    )
                    continue

                dn = f"uid={user.employee_user_id.username},{base_dn}"

                # Securely hash the password using SHA
                hashed_password = (
                    "{SHA}"
                    + base64.b64encode(
                        hashlib.sha1(user.phone.encode()).digest()
                    ).decode()
                )

                if user.employee_last_name is None:
                    user.employee_last_name = " "

                attributes = {
                    "objectClass": ["inetOrgPerson"],
                    "givenName": user.employee_first_name or "",
                    "sn": user.employee_last_name or "",
                    "cn": f"{user.employee_first_name} {user.employee_last_name}",
                    # Without an email, the username is the uid
                    "uid": user.email or user.employee_user_id.username,
                    "telephoneNumber": user.phone or "",
                    "userPassword": hashed_password,  # Securely store password
                }
                if user.email:
                    attributes["mail"] = user.email

                # Check if the user already exists in LDAP
                conn.search(
                    base_dn,
                    f"(uid={user.employee_user_id.username})",
                    attributes=ALL_ATTRIBUTES,
                )

                if conn.entries:
                    self.stdout.write(
                        self.style.WARNING(
                            f"{user.employee_first_name} {user.employee_last_name} already exists in LDAP. Skipping..."
                        )
                    )
                else:
                    # Add user to LDAP
                    if not conn.add(dn, attributes=attributes):
                        self.stdout.write(
                            self.style.ERROR(
                                f"Failed to add {user.employee_first_name} {user.employee_last_name}: {conn.result}"
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Successfully added {user.employee_first_name} {user.employee_last_name} to LDAP."
                            )
                        )

            conn.unbind()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An error occurred: {e}"))
