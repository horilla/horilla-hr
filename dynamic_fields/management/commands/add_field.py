import logging

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import connection
from simple_history.models import HistoricalRecords

from dynamic_fields.methods import column_exists
from dynamic_fields.models import DynamicField

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Command
    """

    help = "Save all instances of the specified model"

    def add_arguments(self, parser):
        parser.add_argument(
            "pk",
            type=str,
            help="Primary key of the DynamicField model to save instances for (e.g., employee.models.Model)",
        )
        parser.add_argument(
            "--is_alter_field",
            type=str,
            help="Indicates if the field is being altered",
            default=None,  # optional argument
        )

    def handle(self, *args, **kwargs):
        pk = kwargs["pk"]
        instance = DynamicField.objects.get(pk=pk)
        model = instance.get_model()
        field = instance.get_field()
        field.set_attributes_from_name(instance.field_name)
        if not column_exists(model._meta.db_table, instance.field_name):
            with connection.schema_editor() as editor:
                editor.add_field(model, field)
            logger.info(
                f"Field does not exist, adding it in {model.__class__.__name__}."
            )
        model.add_to_class(field.column, field)

        name = HistoricalRecords().get_history_model_name(model).lower()
        historical_model_ct = ContentType.objects.filter(model=name).first()
        if historical_model_ct:
            history_model = historical_model_ct.model_class()
            if not column_exists(history_model._meta.db_table, instance.field_name):
                with connection.schema_editor() as editor:
                    editor.add_field(history_model, field)
                logger.info(
                    f"Field does not exist, adding it in {history_model.__class__.__name__}."
                )
            history_model.add_to_class(field.column, field)
