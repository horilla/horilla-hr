from django.core.management.base import BaseCommand

from horilla_theme.models import THEMES_DATA, HorillaColorTheme


class Command(BaseCommand):
    help = "Create default color themes for the CRM"

    def handle(self, *args, **options):
        # Check if themes already exist
        if HorillaColorTheme.objects.exists():
            self.stdout.write(
                self.style.WARNING("Themes already exist. Skipping creation.")
            )
            return

        created_count = 0
        self.stdout.write("Creating default color themes...")

        for theme_data in THEMES_DATA:
            try:
                theme, created = HorillaColorTheme.objects.get_or_create(
                    name=theme_data["name"], defaults=theme_data
                )
                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ Created theme: {theme.name}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"- Theme already exists: {theme.name}")
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Error creating theme {theme_data["name"]}: {str(e)}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully created {created_count} themes.")
        )
