"""Organization taxonomy renames (departments, jobs, roles) preserving PKs."""

from __future__ import annotations

import logging

from django.db import transaction

from base.demo_data.catalog import (
    DEPARTMENT_RENAMES,
    JOB_POSITION_RENAMES,
    JOB_ROLE_LABEL_RENAMES,
    JOB_ROLE_RENAMES,
)
from base.models import Company, Department, Holidays, JobPosition, JobRole

logger = logging.getLogger(__name__)

# Holidays ship generic and shared (company_id=None) across every demo
# company. Re-scope the subset that actually matches one company's
# real-world region, so switching company context shows a genuinely
# different holiday calendar instead of an identical one everywhere.
# Company 1 = US, 2 = India, 3 = UK (see base_data.json).
HOLIDAY_COMPANY_BY_NAME = {
    "Good Friday": 3,  # UK bank holiday
    "Easter Monday": 3,  # UK bank holiday
    "Eid al-Fitr": 2,  # gazetted holiday in India
    "Eid al-Adha": 2,  # gazetted holiday in India
    "Labor Day": 2,  # India observes May 1 as Labour Day
}

# One department exclusive to each company, so every company's own
# department list is genuinely different, not just a shared catalog.
COMPANY_EXCLUSIVE_DEPARTMENTS = {
    1: "Corporate Services",
    2: "India Delivery Center",
    3: "UK Regional Support",
}


@transaction.atomic
def standardize_org_taxonomy() -> dict[str, int]:
    """
    Rename departments, job positions, and roles in place by PK.

    In-place renames keep all EmployeeWorkInformation and related FKs valid
    without remapping. Returns counts of updated rows per model.
    """
    dept_updated = 0
    for pk, name in DEPARTMENT_RENAMES.items():
        updated = (
            Department.objects.filter(pk=pk)
            .exclude(department=name)
            .update(department=name)
        )
        dept_updated += updated

    # Ensure Operations (Managers) stays shared across companies
    ops = Department.objects.filter(pk=6).first()
    if ops is not None:
        company_ids = list(ops.company_id.values_list("pk", flat=True))
        if set(company_ids) != {1, 2, 3}:
            from base.models import Company

            ops.company_id.set(Company.objects.filter(pk__in=[1, 2, 3]))

    job_updated = 0
    for pk, name in JOB_POSITION_RENAMES.items():
        updated = (
            JobPosition.objects.filter(pk=pk)
            .exclude(job_position=name)
            .update(job_position=name)
        )
        job_updated += updated

    role_updated = 0
    for pk, name in JOB_ROLE_RENAMES.items():
        role_updated += (
            JobRole.objects.filter(pk=pk).exclude(job_role=name).update(job_role=name)
        )

    for old, new in JOB_ROLE_LABEL_RENAMES.items():
        role_updated += (
            JobRole.objects.filter(job_role=old)
            .exclude(job_role=new)
            .update(job_role=new)
        )

    logger.info(
        "Org taxonomy standardized: departments=%s jobs=%s roles=%s",
        dept_updated,
        job_updated,
        role_updated,
    )
    return {
        "departments": dept_updated,
        "job_positions": job_updated,
        "job_roles": role_updated,
    }


@transaction.atomic
def differentiate_org_taxonomy_by_company() -> dict[str, int]:
    """
    Give each demo company at least some genuinely distinct org taxonomy
    instead of one identical shared catalog everywhere: region-appropriate
    holidays, and one company-exclusive department. Additive only -- no
    existing Department is re-scoped, so no EmployeeWorkInformation's
    current department becomes invisible under its own company's filter.
    """
    holidays_updated = 0
    for name, company_pk in HOLIDAY_COMPANY_BY_NAME.items():
        holidays_updated += (
            Holidays.objects.filter(name=name)
            .exclude(company_id=company_pk)
            .update(company_id=company_pk)
        )

    departments_created = 0
    for company_pk, dept_name in COMPANY_EXCLUSIVE_DEPARTMENTS.items():
        dept, created = Department.objects.get_or_create(department=dept_name)
        if set(dept.company_id.values_list("pk", flat=True)) != {company_pk}:
            dept.company_id.set(Company.objects.filter(pk=company_pk))
        if created:
            departments_created += 1

    logger.info(
        "Org taxonomy differentiation: %s holiday(s) re-scoped, %s company-exclusive department(s) ensured",
        holidays_updated,
        departments_created,
    )
    return {"holidays": holidays_updated, "departments": departments_created}
