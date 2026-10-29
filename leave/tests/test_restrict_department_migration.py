"""Migration leave.0011 turned RestrictLeave.department from a ForeignKey into a ManyToManyField. Its first version dropped every existing
restriction's department; this runs the real migration over real rows to keep that from coming back."""

import datetime

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("leave", "0010_historicalleaverequest_cancellation_requested_and_more")]
AFTER = [("leave", "0011_remove_restrictleave_department_and_more")]


class RestrictDepartmentMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        executor.loader.build_graph()
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(
            executor.loader.graph.leaf_nodes()
        )  # leave the database at the latest schema for the tests after this one
        super().tearDown()

    def make(self, apps, title, department):
        return apps.get_model("leave", "RestrictLeave").objects.create(
            title=title,
            start_date=datetime.date(2026, 12, 20),
            end_date=datetime.date(2026, 12, 31),
            department=department,
            description="x",
        )

    def test_every_restriction_keeps_its_department(self):
        old = self.migrate(BEFORE)
        Department = old.get_model("base", "Department")
        eng, sales = Department.objects.create(
            department="Eng"
        ), Department.objects.create(department="Sales")
        first, second = self.make(old, "Year end freeze", eng), self.make(
            old, "Audit week", sales
        )
        orphan_free = self.make(old, "Also eng", eng)

        new = self.migrate(AFTER)
        RestrictLeave = new.get_model("leave", "RestrictLeave")
        self.assertEqual(
            list(
                RestrictLeave.objects.get(pk=first.pk).department.values_list(
                    "pk", flat=True
                )
            ),
            [eng.pk],
        )
        self.assertEqual(
            list(
                RestrictLeave.objects.get(pk=second.pk).department.values_list(
                    "pk", flat=True
                )
            ),
            [sales.pk],
        )
        self.assertEqual(
            list(
                RestrictLeave.objects.get(pk=orphan_free.pk).department.values_list(
                    "pk", flat=True
                )
            ),
            [eng.pk],
        )
        self.assertEqual(RestrictLeave.objects.count(), 3, "no restriction was lost")
        self.assertNotIn(
            "department_old",
            [f.name for f in RestrictLeave._meta.get_fields()],
            "the temporary column is gone",
        )

    def test_going_back_restores_one_department_per_restriction(self):
        old = self.migrate(BEFORE)
        Department = old.get_model("base", "Department")
        eng = Department.objects.create(department="Eng")
        row = self.make(old, "Freeze", eng)
        new = self.migrate(AFTER)
        sales = new.get_model("base", "Department").objects.create(department="Sales")
        new.get_model("leave", "RestrictLeave").objects.get(pk=row.pk).department.add(
            sales
        )  # a second department, only possible after the change

        back = self.migrate(BEFORE)
        restored = back.get_model("leave", "RestrictLeave").objects.get(pk=row.pk)
        self.assertEqual(
            restored.department_id,
            min(eng.pk, sales.pk),
            "the old column keeps the first department",
        )
