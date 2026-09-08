"""
company_onboarding/signals.py

Grants the fine-grained permission slices that base/signals.py's
_DEFAULT_HRMS_GROUPS helper can't express, since that helper only grants
permissions at whole-app granularity:

- "Ventura Admin" needs base.add_company/change_company/change_status_company
  — Company lives inside `base`, a huge app with dozens of unrelated models,
  so granting via _DEFAULT_HRMS_GROUPS would mean either all of base's
  permissions (far too broad) or none.
- "Ventura HR" needs add/change on just CompanyBrandedTemplate/CompanyDocument
  within company_onboarding itself — _DEFAULT_HRMS_GROUPS' app_actions is
  also app-level, not model-level, so it can't isolate to just these two
  models either.

Both groups otherwise get their baseline company_onboarding grants normally
through base/signals.py's _DEFAULT_HRMS_GROUPS ("Ventura Admin": "__all__",
"Ventura HR": view-only) — this module only adds the slices that helper
structurally cannot express.
"""

from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def grant_ventura_admin_company_perms(sender, **kwargs):
    if getattr(sender, "label", None) != "company_onboarding":
        return
    group, _created = Group.objects.get_or_create(name="Ventura Admin")
    perms = Permission.objects.filter(
        content_type__app_label="base",
        content_type__model="company",
        codename__in=["add_company", "change_company", "change_status_company"],
    )
    group.permissions.add(*perms)


@receiver(post_migrate)
def grant_ventura_hr_branding_perms(sender, **kwargs):
    if getattr(sender, "label", None) != "company_onboarding":
        return
    group, _created = Group.objects.get_or_create(name="Ventura HR")
    perms = Permission.objects.filter(
        content_type__app_label="company_onboarding",
        content_type__model__in=("companybrandedtemplate", "companydocument"),
        codename__startswith="add_",
    ) | Permission.objects.filter(
        content_type__app_label="company_onboarding",
        content_type__model__in=("companybrandedtemplate", "companydocument"),
        codename__startswith="change_",
    )
    group.permissions.add(*perms)
