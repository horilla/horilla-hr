import platform
import re
import sys

from django.core.management.base import BaseCommand
from django.db.models import Q

from employee.models import Employee
from horilla_auth.models import HorillaUser
from horilla_ldap.models import LDAPSettings

if platform.system() == "Linux":
    import ldap  # Use python-ldap for Linux
else:
    from ldap3 import ALL, Connection, Server  # Use ldap3 for Windows


class Command(BaseCommand):
    help = "Imports employees from LDAP into the Django database using LDAP settings from the database"

    def handle(self, *args, **kwargs):
        # Detect OS
        os_name = platform.system()
        # self.stdout.write(self.style.NOTICE(f"Running on {os_name}"))

        # Fetch LDAP settings from the database
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

        try:
            if os_name == "Linux":
                # LDAP connection for Linux (python-ldap)
                connection = ldap.initialize(ldap_server)
                connection.simple_bind_s(bind_dn, bind_password)
                search_filter = "(objectClass=inetOrgPerson)"
                results = connection.search_s(
                    base_dn, ldap.SCOPE_SUBTREE, search_filter
                )

                for dn, entry in results:
                    user_id = entry.get("uid", [b""])[0].decode("utf-8")
                    email = entry.get("mail", [b""])[0].decode("utf-8")
                    first_name = entry.get("givenName", [b""])[0].decode("utf-8")
                    last_name = entry.get("sn", [b""])[0].decode("utf-8")
                    name = entry.get("cn", [b""])[0].decode("utf-8")
                    phone = entry.get("telephoneNumber", [b""])[0].decode("utf-8")

                    # Get the password from LDAP
                    ldap_password = entry.get("telephoneNumber", [b""])[0].decode(
                        "utf-8"
                    )

                    # Remove non-numeric characters but keep numbers
                    clean_phone = re.sub(r"[^\d]", "", phone)
                    ldap_password = clean_phone

                    self.create_or_update_employee(
                        user_id, email, first_name, last_name, phone, ldap_password
                    )

                connection.unbind_s()

            else:
                # LDAP connection for Windows (ldap3)
                server = Server(ldap_server, get_info=ALL)
                connection = Connection(server, user=bind_dn, password=bind_password)
                if not connection.bind():
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to bind to LDAP server: {connection.last_error}"
                        )
                    )
                    return

                search_filter = "(objectClass=inetOrgPerson)"
                connection.search(
                    base_dn,
                    search_filter,
                    attributes=[
                        "uid",
                        "mail",
                        "givenName",
                        "sn",
                        "cn",
                        "telephoneNumber",
                        "userPassword",
                    ],
                )

                for entry in connection.entries:
                    user_id = entry.uid.value if entry.uid else ""
                    email = entry.mail.value if entry.mail else ""
                    first_name = entry.givenName.value if entry.givenName else ""
                    last_name = entry.sn.value if entry.sn else ""
                    name = entry.cn.value if entry.cn else ""
                    phone = entry.telephoneNumber.value if entry.telephoneNumber else ""

                    # Get the password from LDAP
                    clean_phone = re.sub(r"[^\d]", "", phone)
                    ldap_password = clean_phone

                    self.create_or_update_employee(
                        user_id, email, first_name, last_name, phone, ldap_password
                    )

                connection.unbind()

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))

    def create_or_update_employee(
        self, user_id, email, first_name, last_name, phone, ldap_password
    ):
        email = email or None
        if not email and not user_id:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped {first_name} {last_name}: no email and no uid."
                )
            )
            return
        # Without an email, the uid (kept as the username) finds the employee
        lookup = {"email": email} if email else {"employee_user_id__username": user_id}
        employee, created = Employee.objects.update_or_create(
            **lookup,
            defaults={
                "employee_first_name": first_name or "",
                "employee_last_name": last_name or "",
                "phone": phone or "",
            },
        )

        try:
            if email:
                user = HorillaUser.objects.get(
                    Q(username=email) | Q(username=user_id) | Q(email=email)
                )
            else:
                user = employee.employee_user_id
                if user is None:
                    raise HorillaUser.DoesNotExist
            user.username = email or user_id
            user.set_password(ldap_password)  # Hash and store password securely
            user.save()
            action = "Updated"
        except HorillaUser.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(
                    f"User for employee {first_name} {last_name} does not exist."
                )
            )
            return

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{action} employee {first_name} {last_name}.")
        )
