"""
The tenancy system check must actually catch an unscoped model.

Tenancy is opt-in per model: isolation exists only where someone remembered a
HorillaCompanyManager. Across 233 models that is 233 chances to forget, and
forgetting is silent. This check turns the omission into a failed
`manage.py check`; these tests make sure it would.
"""

from django.core.checks import Warning as CheckWarning
from django.db import models
from django.test import SimpleTestCase

from base.checks import EXEMPT, check_company_scoped_managers
from base.horilla_company_manager import HorillaCompanyManager


class TenancyCheckTests(SimpleTestCase):
    def test_current_codebase_is_clean(self):
        # If this fails, a model with a company_id gained an unscoped default
        # manager. Scope it, or add it to EXEMPT with the reason it is global.
        #
        # The ProbeModel classes below register themselves in the app registry
        # for the life of the process, so exclude them -- otherwise this asserts
        # on whether it ran before or after them.
        real = [
            p
            for p in check_company_scoped_managers(None)
            if "ProbeModel" not in getattr(p.obj, "__name__", "")
        ]
        self.assertEqual(real, [])

    def test_every_exemption_carries_a_reason(self):
        for label, reason in EXEMPT.items():
            self.assertTrue(reason.strip(), f"{label} is exempt with no reason")

    def test_an_unscoped_company_model_is_reported(self):
        class Meta:
            app_label = "base"

        offender = type(
            "UnscopedProbeModel",
            (models.Model,),
            {
                "__module__": __name__,
                "Meta": Meta,
                "company_id": models.ForeignKey(
                    "base.Company", on_delete=models.CASCADE, null=True
                ),
            },
        )

        problems = [
            p
            for p in check_company_scoped_managers(None)
            if getattr(p.obj, "__name__", "") == "UnscopedProbeModel"
        ]

        self.assertEqual(len(problems), 1)
        self.assertIsInstance(problems[0], CheckWarning)
        self.assertEqual(problems[0].id, "horilla.tenancy.W001")

    def test_a_scoped_company_model_is_not_reported(self):
        class Meta:
            app_label = "base"

        type(
            "ScopedProbeModel",
            (models.Model,),
            {
                "__module__": __name__,
                "Meta": Meta,
                "company_id": models.ForeignKey(
                    "base.Company", on_delete=models.CASCADE, null=True
                ),
                "objects": HorillaCompanyManager(),
            },
        )

        problems = [
            p
            for p in check_company_scoped_managers(None)
            if getattr(p.obj, "__name__", "") == "ScopedProbeModel"
        ]

        self.assertEqual(problems, [])
