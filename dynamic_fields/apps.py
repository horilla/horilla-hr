import logging
import sys

from django.apps import AppConfig
from django.core.management import call_command
from django.db import connection

from dynamic_fields.methods import column_exists

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
            dynamic_objects = DynamicField.objects.filter()
            # Ensure this logic only runs when the server is started (and only once)
            if any(cmd in sys.argv for cmd in ["runserver", "shell"]):
                fields_to_remove = DynamicField.objects.filter(remove_column=True)
                for df in fields_to_remove:
                    try:
                        call_command("delete_field", *(df.pk,))
                    except Exception as e:
                        logger.error(e)
                for df in dynamic_objects:
                    field = df.get_field()
                    field.set_attributes_from_name(df.field_name)
                    model = df.get_model()
                    if not column_exists(model._meta.db_table, df.field_name):
                        logger.info("Field does not exist, adding it.")
                        with connection.schema_editor() as editor:
                            editor.add_field(model, field)
                    model.add_to_class(field.name, field)

                    name = HistoricalRecords().get_history_model_name(model).lower()
                    historical_model_ct = ContentType.objects.filter(model=name).first()
                    if historical_model_ct:
                        history_model = historical_model_ct.model_class()
                        if not hasattr(history_model, field.column):
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
