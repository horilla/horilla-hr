import logging
import sys

from django.apps import AppConfig
from django.core.management import call_command
from django.db import connection

from dynamic_fields.methods import column_exists, is_management_command

logger = logging.getLogger(__name__)


class DynamicFieldsConfig(AppConfig):
    """
    DynamicFieldsConfig
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "dynamic_fields"

    def ready(self):
        from django.contrib.contenttypes.models import ContentType
        from simple_history.models import HistoricalRecords

        from dynamic_fields import signals  # noqa: F401
        from dynamic_fields.models import DynamicField

        try:
            changes_schema = any(cmd in sys.argv for cmd in ["runserver", "shell"])
            # Web servers need the fields on the models to load and save their
            # values. Other manage.py commands must not see them: makemigrations
            # would write them into a migration. A worker only learns of a field
            # here, so one added while running needs a restart to reach them all.
            if changes_schema or not is_management_command(sys.argv):
                if changes_schema:
                    fields_to_remove = DynamicField.objects.filter(remove_column=True)
                    for df in fields_to_remove:
                        try:
                            call_command("delete_field", *(df.pk,))
                        except Exception as e:
                            logger.error(e)
                for df in DynamicField.objects.filter(remove_column=False):
                    field = df.get_field()
                    field.set_attributes_from_name(df.field_name)
                    model = df.get_model()
                    if not column_exists(model._meta.db_table, df.field_name):
                        if not changes_schema:
                            # Querying a field with no column would break every
                            # query on the model.
                            logger.warning(
                                "%s has no column for dynamic field %s, skipping it.",
                                model._meta.db_table,
                                df.field_name,
                            )
                            continue
                        logger.info("Field does not exist, adding it.")
                        with connection.schema_editor() as editor:
                            editor.add_field(model, field)
                    model.add_to_class(field.name, field)

                    name = HistoricalRecords().get_history_model_name(model).lower()
                    historical_model_ct = ContentType.objects.filter(model=name).first()
                    if historical_model_ct:
                        history_model = historical_model_ct.model_class()
                        if not hasattr(history_model, field.column) and column_exists(
                            history_model._meta.db_table, df.field_name
                        ):
                            history_model.add_to_class(field.column, field)

        except Exception as e:
            logger.error(e)
            logger.info("ignore if it is fresh installation")

        from django.urls import include, path

        from base.urls import urlpatterns

        urlpatterns.append(
            path("df/", include("dynamic_fields.urls")),
        )

        return super().ready()
