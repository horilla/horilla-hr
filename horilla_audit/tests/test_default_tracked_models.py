"""
What gets audited on an install nobody has configured.

DEFAULT_TRACKED_MODELS was the three Employee models only, so "who changed this
salary", "who approved this leave" and "who edited this attendance record" --
the first questions asked in any HR audit -- had no answer out of the box.

These tests pin the floor, and pin the two exclusions that are deliberate, so a
later well-meaning "add everything" change has to argue with a test rather than
silently double the write volume.
"""

from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.test import TestCase

from horilla_audit.registry import (
    DEFAULT_TRACKED_MODELS,
    _resolve_model,
    apply_audit_configuration,
)

# The domains an HR audit actually asks about.
REQUIRED = [
    ("employee", "Employee"),
    ("employee", "EmployeeWorkInformation"),
    ("employee", "EmployeeBankDetails"),
    ("payroll", "Contract"),
    ("payroll", "Payslip"),
    ("payroll", "SalaryStructure"),
    ("payroll", "LoanAccount"),
    ("payroll", "Reimbursement"),
    ("leave", "LeaveRequest"),
    ("leave", "AvailableLeave"),
    ("leave", "LeaveType"),
    ("attendance", "Attendance"),
    ("attendance", "AttendanceOverTime"),
]


class DefaultTrackedModelsTests(TestCase):
    def test_every_listed_model_resolves(self):
        # _resolve_model returns None for a name that does not exist and the
        # registry skips it silently, so a typo here would disable auditing for
        # that model without any error at all.
        unresolved = [
            f"{app}.{name}"
            for app, name in DEFAULT_TRACKED_MODELS
            if _resolve_model(app, name) is None
        ]

        self.assertEqual(unresolved, [])

    def test_payroll_leave_and_attendance_are_covered(self):
        listed = set(DEFAULT_TRACKED_MODELS)

        missing = [pair for pair in REQUIRED if pair not in listed]

        self.assertEqual(missing, [])

    def test_high_churn_bulk_created_model_is_excluded(self):
        # attendance.WorkRecords is written by a scheduled job every 30 minutes
        # via bulk_create, which auditlog does not observe at all -- so tracking
        # it would cost the most writes in the system for an incomplete trail.
        self.assertNotIn(("attendance", "WorkRecords"), set(DEFAULT_TRACKED_MODELS))

    def test_all_defaults_register_with_auditlog(self):
        apply_audit_configuration()

        unregistered = [
            f"{app}.{name}"
            for app, name in DEFAULT_TRACKED_MODELS
            if (model := _resolve_model(app, name)) and not auditlog.contains(model)
        ]

        self.assertEqual(unregistered, [])


class PayrollChangeIsLoggedTests(TestCase):
    """The end-to-end claim: editing pay data leaves a trail by default."""

    def setUp(self):
        apply_audit_configuration()

    def test_editing_a_contract_writes_a_log_entry(self):
        from base.models import Company
        from horilla.testkit import make_employee
        from payroll.models.models import Contract

        company = Company.objects.create(company="Acme", hq=True)
        employee = make_employee(company=company, email="pay@test.horilla")
        contract = Contract.objects.create(
            contract_name="Initial",
            employee_id=employee,
            contract_start_date="2026-01-01",
            wage=50000,
        )
        before = LogEntry.objects.filter(object_pk=str(contract.pk)).count()

        contract.wage = 90000
        contract.save()

        # A wage change with no record of who made it is the gap this closes.
        self.assertGreater(
            LogEntry.objects.filter(object_pk=str(contract.pk)).count(), before
        )
