"""
horilla_company_manager.py
"""

import logging

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Q
from django.db.models.query import QuerySet

from horilla.horilla_middlewares import _thread_locals, get_selected_company
from horilla.signals import (
    post_bulk_update,
    post_model_clean,
    pre_bulk_update,
    pre_model_clean,
)

logger = logging.getLogger(__name__)
django_filter_update = QuerySet.update


def update(self, *args, **kwargs):
    """
    Bulk Update
    """
    # pre_update signal
    request = getattr(_thread_locals, "request", None)
    self.request = request
    pre_bulk_update.send(sender=self.model, queryset=self, args=args, kwargs=kwargs)
    result = django_filter_update(self, *args, **kwargs)
    # post_update signal
    post_bulk_update.send(sender=self.model, queryset=self, args=args, kwargs=kwargs)

    return result


django_model_clean = models.Model.clean


def clean(self, *args, **kwargs):
    """
    Method to override django clean and trigger to signals
    """
    pre_model_clean.send(sender=self._meta.model, instance=self, **kwargs)
    result = django_model_clean(self)
    post_model_clean.send(sender=self._meta.model, instance=self, **kwargs)
    return result


models.Model.clean = clean

setattr(QuerySet, "update", update)


class HorillaCompanyManager(models.Manager):

    company_filter_path = None

    def __new__(cls, related_company_field=None, *args, **kwargs):
        if cls is HorillaCompanyManager:
            cls = type(
                cls.__name__,
                (cls,),
                {"company_filter_path": related_company_field},
            )
        return super().__new__(cls)

    def __init__(self, related_company_field=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if related_company_field is not None:
            self.company_filter_path = related_company_field

    def _resolve_related_field(self, model, part):
        # Forward field
        try:
            return model._meta.get_field(part)
        except FieldDoesNotExist:
            pass

        # Reverse relation
        for rel in model._meta.related_objects:
            if rel.get_accessor_name() == part:
                return rel

        raise FieldDoesNotExist(part)

    def _field_exists(self, path):
        model = self.model

        parts = path.split("__")
        for i, part in enumerate(parts):
            try:
                field = self._resolve_related_field(model, part)
            except FieldDoesNotExist:
                logger.exception(
                    f"Invalid company filter path '{path}' for model {self.model.__name__}. "
                    f"Failed at field '{part}'."
                )
                return False

            # Only traverse if relational AND not last field
            if (
                getattr(field, "is_relation", False)
                and field.related_model
                and i < len(parts) - 1
            ):
                model = field.related_model
            elif i < len(parts) - 1:
                # Non-relational field in middle of path = invalid
                logger.exception(
                    f"Invalid company filter path '{path}' for model {self.model.__name__}. "
                    f"Field '{part}' is not relational."
                )
                return False

        return True

    def _has_company_id_fk_or_m2m(self):
        try:
            field = self.model._meta.get_field("company_id")
            return isinstance(field, (models.ForeignKey, models.ManyToManyField))
        except FieldDoesNotExist:
            return False

    def get_company_filter_path(self):
        if self.company_filter_path and self._field_exists(self.company_filter_path):
            return self.company_filter_path

        if self._has_company_id_fk_or_m2m():
            return "company_id"

        return None

    def get_queryset(self):
        qs = super().get_queryset()
        company = get_selected_company()
        filter_path = self.get_company_filter_path()

        if not filter_path or not company:
            return qs

        # Superuser / legacy "all": no company filter (true tenant-wide).
        # Non-superuser "all" (All my companies): restrict to assignment
        # companies (all_my_company_ids), falling back to allowed ids.
        if company == "all":
            request = getattr(_thread_locals, "request", None)
            filter_ids = None
            if request:
                filter_ids = getattr(request, "all_my_company_ids", None)
                if filter_ids is None:
                    filter_ids = getattr(request, "allowed_company_ids", None)
            if filter_ids is None:
                return qs
            if not filter_ids:
                return qs.none()
            try:
                return qs.filter(
                    Q(**{f"{filter_path}__in": list(filter_ids)})
                    | Q(**{f"{filter_path}__isnull": True})
                ).distinct()
            except Exception as e:
                logger.exception(
                    f"Company filter (all-my-companies) failed for model "
                    f"{self.model.__name__} with path '{filter_path}': {e}"
                )
                return qs.none()

        try:
            return qs.filter(
                Q(**{filter_path: company}) | Q(**{f"{filter_path}__isnull": True})
            ).distinct()
        except Exception as e:
            logger.exception(
                f"Company filter failed for model {self.model.__name__} "
                f"with path '{filter_path}': {e}"
            )
            return qs.none()

    def _get_is_active_filter(self):
        """
        Return True unless the request explicitly passes is_active=False/false.
        """
        request = getattr(_thread_locals, "request", None)
        raw = request.GET.get("is_active", True) if request else True
        return raw not in ["False", "false", False]

    def all(self):
        """
        Override all() to exclude inactive records by default.
        Only applies is_active filtering when a request context is active (not during startup/scheduler).
        - For `employee` model: respect request.GET `is_active` param; default to active only.
        - For `offboardingemployee` model: return unfiltered.
        - For other models:
            1. If the model itself has `is_active`, filter by it (respects GET param, default True).
            2. If the model has `employee_id` FK to Employee, hide records of inactive employees.
               Else, find the first FK to Employee and use that.
        """
        queryset = self.get_queryset()
        request = getattr(_thread_locals, "request", None)
        if not request:
            return queryset

        try:
            model_name = queryset.model._meta.model_name

            if model_name == "employee":
                # ?is_active=all asks for active and inactive together (a chart
                # that counts both kinds of people opens its list this way).
                # A window of exits or joins (the dashboard's Hire vs Turnover chart) is
                # about people who may have left, so it is not narrowed to active ones.
                everyone = request.GET.get("is_active") == "all" or any(
                    request.GET.get(k)
                    for k in (
                        "exited_from",
                        "exited_till",
                        "joined_from",
                        "joined_till",
                    )
                )
                if not everyone:
                    queryset = queryset.filter(is_active=self._get_is_active_filter())

            elif model_name == "offboardingemployee":
                return queryset

            else:
                model_fields = queryset.model._meta.fields
                model_field_names = {f.name for f in model_fields}

                if "is_active" in model_field_names:
                    queryset = queryset.filter(is_active=self._get_is_active_filter())

                try:
                    employee_model = apps.get_model("employee", "Employee")
                    if "employee_id" in model_field_names:
                        queryset = queryset.filter(employee_id__is_active=True)
                    else:
                        for field in model_fields:
                            if (
                                isinstance(field, models.ForeignKey)
                                and field.related_model is employee_model
                            ):
                                if field.null:
                                    queryset = queryset.filter(
                                        Q(**{f"{field.name}__isnull": True})
                                        | Q(**{f"{field.name}__is_active": True})
                                    )
                                else:
                                    queryset = queryset.filter(
                                        **{f"{field.name}__is_active": True}
                                    )
                                break
                except LookupError:
                    pass

        except Exception as e:
            logger.error(e)

        return queryset

    def entire(self):
        return super().get_queryset()
