import ldap
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from employee.models import Employee
from horilla_ldap.models import LDAPSettings


class Command(BaseCommand):
    help = "Imports employees from LDAP into the Django database"

    def handle(self, *args, **kwargs):
        # Prefer the LDAP settings saved in Horilla, falling back to the
        # AUTH_LDAP_* Django settings for the server and bind details.
        ldap_settings = LDAPSettings.objects.first()
        server_uri = (ldap_settings and ldap_settings.ldap_server) or getattr(
            settings, "AUTH_LDAP_SERVER_URI", None
        )
        bind_dn = (ldap_settings and ldap_settings.bind_dn) or getattr(
            settings, "AUTH_LDAP_BIND_DN", None
        )
        bind_password = (ldap_settings and ldap_settings.bind_password) or getattr(
            settings, "AUTH_LDAP_BIND_PASSWORD", None
        )
        search_base = ldap_settings and ldap_settings.base_dn

        if not all([server_uri, bind_dn, bind_password, search_base]):
            self.stderr.write(
                self.style.ERROR(
                    "LDAP settings are incomplete. Configure the server, bind DN, "
                    "bind password and base DN in the LDAP settings page."
                )
            )
            return

        try:
            connection = ldap.initialize(server_uri)
            connection.simple_bind_s(bind_dn, bind_password)

            search_filter = "(objectClass=inetOrgPerson)"

            results = connection.search_s(
                search_base, ldap.SCOPE_SUBTREE, search_filter
            )

            for dn, entry in results:

                user_id = entry.get("uid", [b""])[0].decode("utf-8")
                email = entry.get("mail", [b""])[0].decode("utf-8")
                first_name = entry.get("givenName", [b""])[0].decode("utf-8")
                last_name = entry.get("sn", [b""])[0].decode("utf-8")
                name = entry.get("cn", [b""])[0].decode("utf-8")
                # Fall back to the common name when givenName is missing
                first_name = first_name or name
                phone = entry.get("telephoneNumber", [b""])[0].decode("utf-8")

                # Email is optional; without it the uid finds the employee.
                email = email or None
                if not email and not user_id:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping '{name}': entry has no mail and no uid."
                        )
                    )
                    continue

                try:
                    self.create_or_update_employee(
                        user_id, email, first_name, last_name, phone, name
                    )
                except Exception as e:  # keep going with the remaining entries
                    self.stderr.write(
                        self.style.ERROR(f"Failed to import '{email or user_id}': {e}")
                    )

            connection.unbind_s()

        except ldap.LDAPError as e:
            self.stderr.write(self.style.ERROR(f"LDAP Error: {e}"))

    @staticmethod
    def find_employee(user_id, email):
        """
        The LDAP uid is the stable account ID, so match on it first (via the
        employee's Horilla username). Email can change, so it is the fallback.
        """
        if user_id:
            employee = Employee.objects.filter(
                employee_user_id__username=user_id
            ).first()
            if employee:
                return employee
        if email:
            return Employee.objects.filter(email=email).first()
        return None

    def create_or_update_employee(
        self, user_id, email, first_name, last_name, phone, name
    ):
        with transaction.atomic():
            employee = self.find_employee(user_id, email)
            created = employee is None

            if created:
                employee = Employee(email=email)
            elif (
                email
                and employee.email != email
                and Employee.objects.filter(email=email)
                .exclude(pk=employee.pk)
                .exists()
            ):
                raise ValueError(
                    f"cannot change the email of '{employee.email}' to '{email}': "
                    "another employee already uses it."
                )

            employee.email = email
            employee.employee_first_name = first_name
            employee.employee_last_name = last_name
            employee.phone = phone
            employee.save()

            # A new employee gets its Horilla user automatically on save.
            user = employee.employee_user_id
            if user is None:
                self.stdout.write(
                    self.style.WARNING(f"User for employee {name} does not exist.")
                )
                return

            if user_id:
                user.username = user_id
            if email:
                user.email = email
            # The existing Horilla password is intentionally left untouched.
            user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} employee {name}"))
