from collections import Counter

from django.db.models import Q
from django.http import QueryDict
from rest_framework.pagination import PageNumberPagination

from employee.models import EmployeeWorkInformation


def get_filter_url(current_url, request):
    url_parts = current_url.split("?")
    base_url = request.path
    query_params = QueryDict(url_parts[1], mutable=True)
    query_params.pop("groupby_field", None)
    return base_url + "?" + query_params.urlencode()


def groupby_queryset(request, url, field_name, queryset):
    queryset_with_counts = queryset.values(field_name)

    counts = Counter(item[field_name] for item in queryset_with_counts)

    result_list = []
    for i in counts:
        result_list.append({field_name: i, "count": counts[i]})

    counts_and_objects = []
    url = get_filter_url(url, request)
    for item in result_list:
        count = item["count"]
        related_fields = field_name.split("__")
        if item[field_name]:
            related_obj = queryset.filter(**{field_name: item[field_name]}).first()
            for field in related_fields:
                related_obj = getattr(related_obj, field)
            counts_and_objects.append(
                {
                    "count": count,
                    "name": str(related_obj),
                    "filter_url": f"{url}&{field_name}={item[field_name]}",
                }
            )
    pagination = PageNumberPagination()
    page = pagination.paginate_queryset(counts_and_objects, request)
    return pagination.get_paginated_response(page)


def permission_based_queryset(user, perm, queryset, user_obj=None):
    # Handle AnonymousUser during schema generation
    if not user.is_authenticated:
        return queryset.none()

    if user.has_perm(perm):
        return queryset

    employee = user.employee_get

    # Every narrowing branch below filters on employee_id, but 30 of the
    # models routed through this helper have no such field -- LinkedInAccount,
    # Recruitment, Objective, Project and the onboarding/offboarding stage
    # and task models among them. Those filters raise FieldError, so a user
    # *without* the permission got a 500 instead of a restricted list. There
    # is no per-employee predicate to apply on such a model, and returning
    # the unfiltered queryset would hand a permissionless caller everything,
    # so the correct answer is an empty queryset.
    if not any(f.name == "employee_id" for f in queryset.model._meta.fields):
        return queryset.none()

    is_manager = EmployeeWorkInformation.objects.filter(
        reporting_manager_id=employee
    ).exists()
    if is_manager:
        if user_obj:
            return queryset.filter(
                Q(employee_id=employee)
                | Q(employee_id__employee_work_info__reporting_manager_id=employee)
            )
        manager_filter = Q(employee_id=employee)
        subordinates_filter = Q(
            employee_id__employee_work_info__reporting_manager_id=employee
        )
        merged_filter = manager_filter | subordinates_filter
        merged_queryset = queryset.filter(merged_filter)
        return merged_queryset

    return queryset.filter(employee_id=employee)
