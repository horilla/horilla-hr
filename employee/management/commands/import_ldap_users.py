import ldap
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from employee.models import Employee
from horilla_auth.models import HorillaUser


class Command(BaseCommand):
    help = "Imports employees from LDAP into the Django database"

    def handle(self, *args, **kwargs):
        try:
            connection = ldap.initialize(settings.AUTH_LDAP_SERVER_URI)
            connection.simple_bind_s(
                settings.AUTH_LDAP_BIND_DN, settings.AUTH_LDAP_BIND_PASSWORD
            )

            search_base = (
                "ou=users,dc=test,dc=com"  # Replace with your actual search base
            )
            search_filter = "(objectClass=inetOrgPerson)"

            results = connection.search_s(
                search_base, ldap.SCOPE_SUBTREE, search_filter
            )

            for dn, entry in results:

                user_id = entry.get("uid", [b""])[0].decode("utf-8")
                email = entry.get("mail", [b""])[0].decode("utf-8") or None
                first_name = entry.get("givenName", [b""])[0].decode("utf-8")
                last_name = entry.get("sn", [b""])[0].decode("utf-8")
                name = entry.get("cn", [b""])[0].decode("utf-8")
                phone = entry.get("telephoneNumber", [b""])[0].decode("utf-8")

                # Get the password from LDAP
                ldap_password = entry.get("userPassword", [b""])[0].decode("utf-8")

                if not email and not user_id:
                    self.stdout.write(
                        self.style.WARNING(f"Skipped {name}: no email and no uid.")
                    )
                    continue
                # Without an email, the uid (the username) finds the employee
                lookup = (
                    {"email": email}
                    if email
                    else {"employee_user_id__username": user_id}
                )

                # Create or update the Employee record, storing the LDAP password
                employee, created = Employee.objects.update_or_create(
                    **lookup,
                    defaults={
                        "employee_first_name": first_name,
                        "employee_last_name": last_name,
                        "email": email,
                        "phone": phone,
                    },
                )

                # Retrieve the associated HorillaUser if it exists
                try:
                    if email:
                        user = HorillaUser.objects.get(
                            Q(username=email) | Q(username=user_id) | Q(email=email)
                        )
                    else:
                        user = employee.employee_user_id
                        if user is None:
                            raise HorillaUser.DoesNotExist
                    user.username = user_id
                    user.set_password(
                        ldap_password
                    )  # Hash and set the password securely
                    user.save()  # Save the changes to the HorillaUser instance
                    action = "Updated"
                except HorillaUser.DoesNotExist:
                    # If the user does not exist, handle it accordingly (e.g., log a message or create a new user)
                    self.stdout.write(
                        self.style.WARNING(f"User for employee {name} does not exist.")
                    )
                    continue

                action = "Created" if created else "Updated"
                self.stdout.write(
                    self.style.SUCCESS(f"{action} employee {name} with LDAP password")
                )

            connection.unbind_s()

        except ldap.LDAPError as e:
            self.stderr.write(self.style.ERROR(f"LDAP Error: {e}"))
