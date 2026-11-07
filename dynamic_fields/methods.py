"""
dynamic_fields/methods.py
"""

from pathlib import Path

from django.db import connection
from django.template.loader import render_to_string

from horilla.horilla_middlewares import _thread_locals


def column_exists(table_name, column_name):
    """
    Check if the column exists in the database table.
    """
    with connection.cursor() as cursor:
        columns = [
            col[0]
            for col in connection.introspection.get_table_description(
                cursor, table_name
            )
        ]
        return column_name in columns


def is_management_command(argv):
    """
    Whether this process is manage.py or django-admin, rather than a web server.
    """
    program = Path(argv[0]) if argv else Path()
    return program.name in ("manage.py", "django-admin") or (
        program.name == "__main__.py" and program.parent.name == "django"
    )


def structured(self):
    """
    Render the form fields as HTML table rows with Bootstrap styling.
    """
    request = getattr(_thread_locals, "request", None)
    context = {
        "form": self,
        "request": request,
    }
    table_html = render_to_string("dynamic_fields/common/form.html", context)
    return table_html
