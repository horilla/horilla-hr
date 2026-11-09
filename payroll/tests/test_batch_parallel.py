"""Several slices of one run at the same time never pay anyone twice and never lose anyone."""

import threading
from datetime import date
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from horilla.testkit import make_company, make_employee
from payroll.methods import batch_run
from payroll.models.models import Contract, PayrollBatch, PayrollBatchLine, Payslip
from payroll.tests.factories_payroll import make_active_contract
from payroll.tests.test_batch_run import EMPTY_LEAVES, months

START = date(2026, 4, 1)
END = date(2026, 4, 30)


class ParallelSliceTests(TransactionTestCase):
    def setUp(self):
        self.company = make_company("Parallel Co")
        self.people = []
        for number in range(9):
            employee = make_employee(
                company=self.company,
                email=f"p{number}@par.horilla",
                first_name=f"P{number}",
            )
            Contract.objects.filter(employee_id=employee).delete()
            make_active_contract(employee, wage=30000.0)
            self.people.append(employee)

    def test_four_workers_pay_each_person_exactly_once(self):
        batch = batch_run.create_batch(
            name="April", start_date=START, end_date=END, employees=self.people
        )
        errors = []

        def worker():
            try:
                while True:
                    if not batch_run.generate_slice(
                        PayrollBatch.objects.get(pk=batch.pk), size=2
                    ):
                        if not PayrollBatchLine.objects.filter(
                            payroll_batch=batch, status=PayrollBatchLine.QUEUED
                        ).exists():
                            break
            except Exception as exc:  # noqa: BLE001 - reported to the test below
                errors.append(exc)
            finally:
                connection.close()

        with patch(
            "payroll.methods.methods.months_between_range", side_effect=months
        ), patch(
            "payroll.methods.methods.get_daily_salary",
            return_value={"day_wage": 1000.0},
        ), patch(
            "payroll.methods.methods.get_leaves", return_value=EMPTY_LEAVES
        ), patch(
            "attendance.methods.utils.get_employee_attendance_summary", return_value={}
        ):
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=120)

        close_old_connections()
        self.assertEqual(errors, [])
        slips = Payslip.objects.filter(payroll_batch=batch)
        self.assertEqual(slips.count(), 9)
        self.assertEqual(slips.values("employee_id").distinct().count(), 9)
        self.assertEqual(
            PayrollBatchLine.objects.filter(
                payroll_batch=batch, status=PayrollBatchLine.DONE
            ).count(),
            9,
        )
        batch.refresh_from_db()
        self.assertEqual(batch.progress_state, PayrollBatch.DONE)
        self.assertEqual(batch.generated_count, 9)
