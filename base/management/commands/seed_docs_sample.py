"""manage.py seed_docs_sample - the sample company of the user guide."""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from base.demo_data.docs_sample import DEFAULT_PASSWORD, seed_docs_sample


class Command(BaseCommand):
    help = (
        "Create Lakeside Works Ltd, the sample company that every example and "
        "screenshot of the user guide comes from. Use a throwaway database: "
        "--flush wipes it first, which is how the environment is reset."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Flush all existing data before seeding (full reset).",
        )
        parser.add_argument(
            "--no-input",
            "--noinput",
            action="store_false",
            dest="interactive",
            help="Do not prompt for confirmation.",
        )
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Password of the cast logins (default: the documented one).",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            if options["interactive"]:
                answer = input(
                    "This will DELETE all data in the database. Are you sure? [yes/no]: "
                )
                if answer.lower() != "yes":
                    self.stdout.write("Aborted.")
                    return
            call_command("flush", "--no-input", verbosity=0)
            self.stdout.write(self.style.SUCCESS("Database flushed."))

        result = seed_docs_sample(password=options["password"])
        if "skipped" in result:
            self.stdout.write(self.style.WARNING(result["skipped"]))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {result['company']}: {result['employees']} employees, "
                f"{result['leave_requests']} leave requests."
            )
        )
        self.stdout.write("Cast logins (email as username):")
        for login in result["logins"]:
            self.stdout.write(f"  {login}")
        self.stdout.write("Maya Chen is the administrator (superuser).")
