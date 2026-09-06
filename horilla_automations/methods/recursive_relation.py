"""
horilla_automation/recursive_relation.py
"""

from django.apps import apps
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField
from django.db.models.fields.reverse_related import (
    ForeignObjectRel,
    ManyToManyRel,
    ManyToOneRel,
    OneToOneRel,
)

# Set a recursion depth limit to prevent cycles

MAX_DEPTH = 4


def get_all_relation_paths(source_model, target_model, max_depth=5):
    relation_paths = []

    def walk(model, path, visited_models, depth):
        if depth > max_depth or model in visited_models or is_history_model(model):
            return

        visited_models.add(model)

        for field in model._meta.get_fields():
            if not field.is_relation:
                continue

            # Forward relations
            if not field.auto_created:
                related_model = field.related_model
                if not related_model or is_history_model(related_model):
                    continue

                new_path = f"{path}__{field.name}" if path else field.name
                if related_model == target_model:
                    relation_paths.append(new_path)
                else:
                    walk(related_model, new_path, visited_models.copy(), depth + 1)

            # Reverse relations (related_name or default accessor)
            elif isinstance(field, ForeignObjectRel):
                related_model = field.related_model
                if not related_model or is_history_model(related_model):
                    continue

                accessor_name = field.get_accessor_name()
                new_path = f"{path}__{accessor_name}" if path else accessor_name
                if related_model == target_model:
                    relation_paths.append(new_path)
                else:
                    walk(related_model, new_path, visited_models.copy(), depth + 1)

    walk(source_model, "", set(), 0)
    return relation_paths


def get_simple_relation_paths(source_model, target_model, max_depth=5):
    results = []
    all_paths = set()

    def walk(model, path, visited_models, depth):
        if depth > max_depth or model in visited_models:
            return

        visited_models = visited_models | {model}

        for field in model._meta.get_fields():
            if not field.is_relation or isinstance(field, ManyToManyField):
                continue

            # Skip fields without a valid remote_field or related_model
            remote = getattr(field, "remote_field", None)
            related_model = getattr(remote, "model", None)
            if related_model is None:
                continue

            # Determine accessor name
            if field.auto_created and not field.concrete:
                accessor = field.get_accessor_name()
            else:
                accessor = field.name

            new_path = f"{path}__{accessor}" if path else accessor

            if related_model == target_model:
                results.append(new_path)
                all_paths.add(new_path)
            elif depth + 1 < max_depth:
                walk(related_model, new_path, visited_models, depth + 1)

    walk(source_model, "", set(), 0)

    # Post-process to remove paths that are strict supersets of others
    unique_paths = []
    for path in sorted(results, key=lambda p: p.count("__")):  # shortest first
        if not any(
            path != other and path.startswith(other + "__") for other in unique_paths
        ):
            unique_paths.append(path)

    return unique_paths


def is_history_model(model):
    return (
        model._meta.model_name.endswith("_history")
        or model._meta.app_label == "simple_history"
        or model.__name__.lower().endswith("history")
    )


def get_forward_relation_paths_separated(source_model, target_model, max_depth=5):
    """
    Recursively find forward relation paths from source_model to target_model,
    separating ForeignKey and ManyToManyField paths, excluding history models.
    """
    fk_paths = []
    m2m_paths = []

    def walk(model, path, visited_models, depth):
        if depth > max_depth or model in visited_models or is_history_model(model):
            return

        visited_models.add(model)

        for field in model._meta.get_fields():
            if not field.is_relation or field.auto_created:
                continue  # Skip non-relational fields and reverse relations

            related_model = field.related_model
            if not related_model or is_history_model(related_model):
                continue

            new_path = f"{path}__{field.name}" if path else field.name

            if related_model == target_model:
                if field.many_to_many:
                    m2m_paths.append((new_path, field))
                else:
                    fk_paths.append((new_path, field))
            else:
                walk(related_model, new_path, visited_models.copy(), depth + 1)

    walk(source_model, "", set(), 0)
    return fk_paths, m2m_paths


_a = {
    "pms.models.EmployeeKeyResult": {
        "mail_to": [
            ("employee_objective_id__employee_id__get_email", "Employee's mail"),
            (
                "employee_objective_id__employee_id__employee_work_inf__reporting_manager_id__get_email",
                "Reporting manager's mail",
            ),
            (
                "employee_objective_id__objective_id__managers__get_email",
                "Objective manager's mail",
            ),
        ],
        "mail_instance": [
            ("employee_objective_id__employee_id", "Employee"),
        ],
    }
}
