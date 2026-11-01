"""Offboarding dashboard "Offboarding Pipeline" widget tests.

Regression coverage for a bug where the pipeline rendered one tile per
OffboardingStage *row* instead of one tile per stage *type* -- since every
Offboarding process/template seeds its own set of stage rows, having more
than one process in the company multiplied the tile count (e.g. 3 templates
x 6 stage types = 18 tiles, with the same stage label repeated per template).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from horilla.testkit import make_company, make_employee
from offboarding.dashboard import PIPELINE_STAGE_TYPES
from offboarding.models import Offboarding, OffboardingEmployee, OffboardingStage


class OffboardingPipelineWidgetTests(TestCase):
    def setUp(self):
        self.company = make_company("Pipeline Co")
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="pipeline-admin",
            email="pipeline-admin@test.horilla",
            password="pass",
        )
        # A superuser with no linked Employee gets redirected to the new-hire
        # onboarding flow before ever reaching the dashboard view.
        make_employee(
            company=self.company,
            email="pipeline-admin-profile@test.horilla",
            user=self.admin,
        )
        self.client = Client()
        self.client.force_login(self.admin)

        # Two separate offboarding processes/templates -- each auto-seeds its
        # own interview/handover/fnf/other/archived stage rows (see
        # Offboarding.save()), which is exactly the setup that used to
        # multiply tile counts.
        self.process_a = Offboarding.objects.create(
            title="Wave A", description="a", company_id=self.company
        )
        self.process_b = Offboarding.objects.create(
            title="Wave B", description="b", company_id=self.company
        )

        def stage(process, stage_type):
            return OffboardingStage.objects.get(offboarding_id=process, type=stage_type)

        employees = [
            make_employee(company=self.company, email=f"exit{i}@test.horilla")
            for i in range(5)
        ]

        # Same stage *type*, different underlying stage *rows* (different
        # templates) -- the scenario that used to render as separate tiles.
        OffboardingEmployee.objects.create(
            employee_id=employees[0], stage_id=stage(self.process_a, "interview")
        )
        OffboardingEmployee.objects.create(
            employee_id=employees[1], stage_id=stage(self.process_b, "interview")
        )
        OffboardingEmployee.objects.create(
            employee_id=employees[2], stage_id=stage(self.process_a, "archived")
        )
        OffboardingEmployee.objects.create(
            employee_id=employees[3], stage_id=stage(self.process_b, "archived")
        )
        OffboardingEmployee.objects.create(
            employee_id=employees[4], stage_id=stage(self.process_a, "fnf")
        )

    def _get_pipeline(self):
        response = self.client.get(reverse("offboarding-dashboard-pipeline"))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_renders_exactly_one_tile_per_stage_type(self):
        data = self._get_pipeline()
        self.assertEqual(len(data["stages"]), len(PIPELINE_STAGE_TYPES))
        types = [s["type"] for s in data["stages"]]
        self.assertEqual(
            len(types), len(set(types)), "a stage type was rendered more than once"
        )
        self.assertEqual(types, [t for t, _label in PIPELINE_STAGE_TYPES])

    def test_counts_are_aggregated_across_offboarding_templates(self):
        data = self._get_pipeline()
        by_type = {s["type"]: s["count"] for s in data["stages"]}
        self.assertEqual(by_type["interview"], 2)
        self.assertEqual(by_type["archived"], 2)
        self.assertEqual(by_type["fnf"], 1)
        self.assertEqual(by_type["handover"], 0)
        self.assertEqual(by_type["other"], 0)
        self.assertEqual(by_type["notice_period"], 0)
        # Every employee is accounted for: none dropped, none double-counted.
        self.assertEqual(sum(by_type.values()), 5)
        self.assertEqual(data["total"], 5)
