"""
Horilla management command to create a new user and associated employee.
"""

import uuid

from django.core.management.base import BaseCommand, CommandError

from employee.models import Employee
from horilla_auth.models import HorillaUser


class Command(BaseCommand):
    """
    Horilla management command to create a new user and associated employee.
    """

    help = "Creates a new user"

    def add_arguments(self, parser):
        parser.add_argument("--first_name", type=str, help="First name of the new user")
        parser.add_argument("--last_name", type=str, help="Last name of the new user")
        parser.add_argument("--username", type=str, help="Username of the new user")
        parser.add_argument("--password", type=str, help="Password for the new user")
        parser.add_argument("--email", type=str, help="Email of the new user")
        parser.add_argument("--phone", type=str, help="Phone number of the new user")

    def handle(self, *args, **options):
        if not options["first_name"]:
            first_name = input("Enter first name: ")
            last_name = input("Enter last name: ")
            username = input("Enter username: ")
            password = input("Enter password: ")
            email = input("Enter email: ")
            phone = input("Enter phone number: ")
        else:
            first_name = options["first_name"]
            last_name = options["last_name"]
            username = options["username"]
            password = options["password"]
            email = options["email"]
            phone = options["phone"]

        if HorillaUser.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f'User with username "{username}" already exists')
            )
            return

        try:
            user = HorillaUser.objects.create_superuser(
                username=username, email=email or "", password=password
            )
            employee = Employee()
            employee.employee_user_id = user
            employee.employee_first_name = first_name
            employee.employee_last_name = last_name
            employee.email = email
            employee.phone = phone
            employee.save()

            bot = HorillaUser.objects.filter(username="Horilla Bot").first()
            if bot is None:
                HorillaUser.objects.create_user(
                    username="Horilla Bot",
                    password=str(uuid.uuid4()),
                )

            self.stdout.write(
                self.style.SUCCESS(f'Employee "{employee}" created successfully')
            )
        except Exception as e:
            if "user" in locals():
                user.delete()
            raise CommandError(f'Error creating user "{username}": {e}') from e
