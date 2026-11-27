"""
Import employees from LDAP into Horilla.

Uses ldap3 (pure Python) on every platform, so the same code path works on
Windows and Linux without compiling python-ldap.

Passwords are never imported: existing Horilla passwords are left untouched.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from ldap3 import ALL, Connection, Server
from ldap3.core.exceptions import LDAPException

from employee.models import Employee
from horilla_ldap.models import LDAPSettings

SEARCH_FILTER = "(objectClass=inetOrgPerson)"
ATTRIBUTES = ["uid", "mail", "givenName", "sn", "cn", "telephoneNumber"]


def get_attribute(entry, name):
    """Return the first value of an LDAP attribute as a string, or ''."""
    if name not in entry:
        return ""
    value = entry[name].value
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value) if value else ""


class Command(BaseCommand):
    help = (
        "Imports employees from LDAP into the Django database using LDAP "
        "settings from the database"
    )

    def handle(self, *args, **kwargs):
        settings = LDAPSettings.objects.first()
        if not settings:
            self.stdout.write(self.style.ERROR("LDAP settings are not configured."))
            return

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

        connection = None
        counts = {"created": 0, "updated": 0, "no_user": 0, "skipped": 0, "failed": 0}

        try:
            connection = Connection(
                Server(ldap_server, get_info=ALL),
                user=bind_dn,
                password=bind_password,
            )
            if not connection.bind():
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed to bind to LDAP server: {connection.last_error}"
                    )
                )
                return

            if not connection.search(base_dn, SEARCH_FILTER, attributes=ATTRIBUTES):
                self.stderr.write(
                    self.style.ERROR(
                        f"LDAP search under '{base_dn}' returned nothing: "
                        f"{connection.result.get('description')}"
                    )
                )
                return

            for entry in connection.entries:
                user_id = get_attribute(entry, "uid")
                email = get_attribute(entry, "mail")
                first_name = get_attribute(entry, "givenName")
                last_name = get_attribute(entry, "sn")
                name = get_attribute(entry, "cn")
                phone = get_attribute(entry, "telephoneNumber")

                # Fall back to the common name when givenName is missing
                first_name = first_name or name

                # Email is optional; without it the uid finds the employee.
                email = email or None
                if not email and not user_id:
                    counts["skipped"] += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping '{name}': entry has no mail and no uid."
                        )
                    )
                    continue

                try:
                    result = self.create_or_update_employee(
                        user_id, email, first_name, last_name, phone
                    )
                    counts[result] += 1
                except Exception as e:  # keep going with the remaining entries
                    counts["failed"] += 1
                    self.stderr.write(
                        self.style.ERROR(f"Failed to import '{email or user_id}': {e}")
                    )

        except LDAPException as e:
            self.stderr.write(self.style.ERROR(f"LDAP error: {e}"))
            return
        finally:
            if connection is not None and connection.bound:
                connection.unbind()

        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"Created: {counts['created']}, Updated: {counts['updated']}, "
                f"No Horilla user: {counts['no_user']}, "
                f"Skipped: {counts['skipped']}, Failed: {counts['failed']}."
            )
        )

    @staticmethod
    def find_employee(user_id, email):
        """
        Find the employee an LDAP entry belongs to.

        The LDAP uid is the stable account ID, so it is tried first (via the
        employee's Horilla username). The mail attribute can change, so email is
        only the fallback.
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

    def create_or_update_employee(self, user_id, email, first_name, last_name, phone):
        """Create or update one employee. Returns 'created', 'updated' or 'no_user'."""
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
            employee.employee_first_name = first_name or ""
            employee.employee_last_name = last_name or ""
            employee.phone = phone or ""
            employee.save()

            # A new employee gets its Horilla user automatically on save.
            user = employee.employee_user_id
            if user is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"User for employee {first_name} {last_name} does not exist."
                    )
                )
                return "no_user"

            if user_id:
                user.username = user_id
            if email:
                user.email = email
            # The existing Horilla password is intentionally left untouched.
            user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{action} employee {first_name} {last_name}.")
        )
        return "created" if created else "updated"
