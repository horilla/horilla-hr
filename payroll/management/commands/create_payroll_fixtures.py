"""
Management command: create_payroll_fixtures
-------------------------------------------
Clears payroll and rebuilds it as a coherent demo: components, a structure,
contracts, attendance, loans, reimbursements, and a finished payroll run.

Every payroll screen needs data that agrees with every other one. A payslip
whose components do not exist, a contributions page with no employer shares,
a run whose review flags nothing -- each is a screen you cannot judge. So this
builds one consistent month rather than rows per table:

  * Components sized so a payslip adds up and the employer owes something.
  * Contracts that differ on purpose -- wage, filing status, loss-of-pay basis
    -- because the engine branches on all three.
  * Attendance across the whole window with the cases the review step exists
    to catch: unresolved conflicts, a mid-month joiner, heavy loss of pay,
    somebody with no attendance at all.
  * A run for the first whole month, generated through the real engine, so the
    runs list, the payslips, and the contributions page all show the same
    figures.

Deliberately destructive: it drops every payroll row first, including contracts
and the tax packs, then reseeds. Half a wipe leaves components pointing at
structures that no longer exist.

Run:
    python manage.py create_payroll_fixtures
    python manage.py create_payroll_fixtures --employees 45
    python manage.py create_payroll_fixtures --from 2026-08-01 --to 2026-09-23
    python manage.py create_payroll_fixtures --no-run    # skip generating payslips
"""

import contextlib
import datetime
import random

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

SEED = 20260823  # Fixed, so two runs of this command produce the same demo.

# Sized against a 30,000-60,000 wage so a payslip has a believable shape: the
# earnings add up to something above the wage, and the deductions take a
# visible but survivable slice.
EARNINGS = [
    # title, code, fixed?, amount or rate, taxable
    ("House Rent Allowance", "HRA", False, 40.0, True),
    ("Dearness Allowance", "DA", False, 12.0, True),
    ("Conveyance Allowance", "CONV", True, 1600.0, False),
    ("Medical Allowance", "MED", True, 1250.0, False),
    ("Special Allowance", "SPL", True, 2000.0, True),
]

# The employer side is what the contributions page is for, so two of these
# carry one -- including one worked out by formula, which a rate cannot say.
DEDUCTIONS = [
    # title, code, rate, employer_rate, employer_formula, pretax
    ("Provident Fund (PF)", "PF", 12.0, 3.67, "", True),
    ("PF Pension", "PFP", 0.0, 0.0, "min(BASIC, 15000) * 0.0833", True),
    ("ESI", "ESI", 0.75, 3.25, "", True),
    ("Professional Tax", "PT", 0.0, 0.0, "", False),
]


class Command(BaseCommand):
    help = "Clear payroll and rebuild it as a coherent demo dataset."

    def add_arguments(self, parser):
        parser.add_argument("--employees", type=int, default=45)
        parser.add_argument("--from", dest="from_date", default="")
        parser.add_argument("--to", dest="to_date", default="")
        parser.add_argument(
            "--no-run",
            action="store_true",
            help="Build the data but do not generate payslips.",
        )
        parser.add_argument(
            "--keep",
            action="store_true",
            help="Do not clear first. For topping up an existing demo.",
        )

    def handle(self, *args, **options):
        today = datetime.date.today()
        start = _date(options["from_date"], datetime.date(today.year, 8, 1))
        end = _date(options["to_date"], today)
        if start > end:
            start, end = end, start

        random.seed(SEED)

        if not options["keep"]:
            self._clear()

        self._tax_packs()
        earnings, deductions = self._components()
        gross_up, ctc_down = self._structures(earnings, deductions)
        employees = self._contracts(gross_up, ctc_down, options["employees"])
        self._attendance(employees, start, end)
        self._loans_and_claims(employees)

        if not options["no_run"]:
            self._run(employees, start)

        self._report(start, end)

    # -- clearing ---------------------------------------------------------

    def _clear(self):
        """
        Every payroll row, in an order the foreign keys allow.

        Contracts are PROTECTed by filing status and salary structure, so they
        have to go before either. Payslips hold installments, so they go before
        the loans. Getting this order wrong fails loudly rather than half way,
        which is why it is spelled out rather than looped over the app's models.
        """
        from attendance.models import AttendanceConflictResolution
        from payroll.models.models import (
            Allowance,
            Contract,
            Deduction,
            FilingStatus,
            LoanAccount,
            PayrollBatch,
            PayrollBatchLine,
            Payslip,
            Reimbursement,
            SalaryStructure,
        )
        from payroll.models.tax_models import TaxBracket

        self.stdout.write("Clearing payroll...")
        for model in (
            PayrollBatchLine,
            Payslip,
            PayrollBatch,
            Reimbursement,
            LoanAccount,
            Contract,
            SalaryStructure,
            Allowance,
            Deduction,
            TaxBracket,
            FilingStatus,
        ):
            # entire(): the demo is being rebuilt for every company, and a
            # company-filtered delete would leave another company's rows behind
            # to collide with the new ones.
            manager = getattr(model.objects, "entire", None)
            queryset = manager() if manager else model.objects.all()
            count = queryset.count()
            if count:
                queryset.delete()
                self.stdout.write(f"  {model.__name__:22} {count} deleted")

        # The audit trail of payslips that no longer exist.
        for name in ("HistoricalPayslip", "HistoricalContract"):
            model = _historical(name)
            if model is not None and model.objects.exists():
                count = model.objects.count()
                model.objects.all().delete()
                self.stdout.write(f"  {name:22} {count} deleted")

        conflicts = AttendanceConflictResolution.objects.all()
        if conflicts.exists():
            count = conflicts.count()
            conflicts.delete()
            self.stdout.write(f"  {'ConflictResolution':22} {count} deleted")

    # -- configuration ----------------------------------------------------

    def _tax_packs(self):
        """The country packs, reloaded. seed_tax_packs already knows them."""
        self.stdout.write("Loading tax packs...")
        call_command("seed_tax_packs", verbosity=0)
        call_command("sync_system_components", verbosity=0)

    def _components(self):
        from payroll.models.models import Allowance, Deduction

        self.stdout.write("Building components...")
        earnings = []
        for order, (title, code, fixed, value, taxable) in enumerate(EARNINGS, 1):
            earnings.append(
                Allowance.objects.create(
                    title=title,
                    code=code,
                    sequence=order * 10,
                    is_fixed=fixed,
                    amount=value if fixed else None,
                    based_on=None if fixed else "basic_pay",
                    rate=None if fixed else value,
                    is_taxable=taxable,
                    # Fixed perks (Conveyance, Medical, Special) apply
                    # everywhere. The percentage ones (HRA, DA) read
                    # kwargs["basic_pay"] directly, correct only under Gross
                    # Up -- reaching CTC Down contracts too would give them a
                    # second, zero-valued "House Rent Allowance" beside their
                    # real one. Scoped to Gross Up contract holders once those
                    # are known, in _contracts().
                    include_active_employees=fixed,
                    is_condition_based=False,
                )
            )

        deductions = []
        for order, (title, code, rate, emp_rate, formula, pretax) in enumerate(
            DEDUCTIONS, 1
        ):
            fixed = not rate
            deductions.append(
                Deduction.objects.create(
                    title=title,
                    code=code,
                    sequence=order * 10,
                    is_fixed=fixed,
                    amount=200.0 if fixed else None,
                    based_on=None if fixed else "basic_pay",
                    rate=rate or None,
                    employer_basis=(
                        Deduction.EMPLOYER_BASIS_FORMULA
                        if formula
                        else Deduction.EMPLOYER_BASIS_RATE
                    ),
                    employer_rate=emp_rate,
                    employer_formula=formula,
                    is_pretax=pretax,
                    include_active_employees=True,
                    is_condition_based=False,
                )
            )
        self.stdout.write(f"  {len(earnings)} earnings, {len(deductions)} deductions")
        return earnings, deductions

    def _structures(self, earnings, deductions):
        """
        Both modes the engine supports, not just one.

        Gross Up and CTC Down read the contract wage differently -- basic pay
        outright, or the whole package to divide -- and a demo carrying only
        one exercises exactly one of those readings.
        """
        from payroll.models.models import Allowance, SalaryStructure

        gross_up = SalaryStructure.objects.create(
            title="Standard — Monthly Staff",
            structure_mode="gross_up",
        )
        gross_up.allowances.set(earnings)
        gross_up.deductions.set(deductions)

        # CTC Down requires exactly one earning flagged is_basic_pay -- the
        # structure invariants refuse a save without one, since basic pay
        # would otherwise be zero and income tax based on it would tax
        # nothing. Expressed as a formula, not a flat amount: contracts on
        # this structure carry different Monthly CTC figures, and a fixed
        # amount would not scale with the one it belongs to.
        basic = Allowance.objects.create(
            title="Basic Pay",
            code="BASIC",
            sequence=5,
            is_basic_pay=True,
            is_fixed=False,
            based_on="formula",
            formula="CTC * 0.4",
            is_taxable=True,
            include_active_employees=False,
            is_condition_based=False,
        )
        # Absorbs whatever the fixed and percentage earnings before it did not
        # use up. Only meaningful in CTC Down, and only as the last component
        # -- structure_problems() refuses one that is not.
        balance = Allowance.objects.create(
            title="Flexible Benefits (Balance)",
            code="FLEX",
            sequence=90,
            is_fixed=False,
            based_on="balance",
            is_taxable=True,
            include_active_employees=False,
            is_condition_based=False,
        )
        # HRA and DA, restated for this structure rather than reused from the
        # Gross Up set. `based_on="basic_pay"` reads kwargs["basic_pay"]
        # directly, which is correct in Gross Up (the contract wage, known
        # before any earning runs) and is 0 throughout a CTC Down pass --
        # basic there is not known until the flagged component computes it.
        # `based_on="component", percentage_of_code="BASIC"` is the strategy
        # that reads the live value instead; test_ctc_down.py is where that
        # convention is established.
        ctc_hra = Allowance.objects.create(
            title="House Rent Allowance",
            code="CHRA",
            sequence=10,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=40.0,
            is_taxable=True,
            include_active_employees=False,
            is_condition_based=False,
        )
        ctc_da = Allowance.objects.create(
            title="Dearness Allowance",
            code="CDA",
            sequence=20,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=12.0,
            is_taxable=True,
            include_active_employees=False,
            is_condition_based=False,
        )
        ctc_down = SalaryStructure.objects.create(
            title="Standard — CTC Down",
            structure_mode="ctc_down",
        )
        # The flat earnings (Conveyance, Medical, Special) have no basis to
        # get wrong and carry over unchanged; what is left of the package
        # after all of them is what the balance component absorbs.
        flat_earnings = [a for a in earnings if a.is_fixed]
        ctc_down.allowances.set([basic, ctc_hra, ctc_da, *flat_earnings, balance])
        ctc_down.deductions.set(deductions)

        self.stdout.write(f"  Structures: {gross_up.title}, {ctc_down.title}")
        return gross_up, ctc_down

    # -- people -----------------------------------------------------------

    def _contracts(self, gross_up, ctc_down, wanted):
        """
        Contracts that differ on purpose.

        The engine branches on the wage, the filing status, the loss-of-pay
        basis, and the structure mode, so a demo where every contract is
        identical exercises one path and hides the rest. Roughly a third go
        on CTC Down, stating Monthly CTC instead of a wage.
        """
        from employee.models import Employee
        from payroll.models.models import Contract, FilingStatus

        statuses = list(FilingStatus.objects.order_by("id"))
        employees = list(
            Employee.objects.filter(is_active=True).order_by("id")[:wanted]
        )
        self.stdout.write(f"Creating {len(employees)} contracts...")

        bases = ["wage", "gross_pay", "monthly_ctc"]
        divisors = ["working_days", "calendar_days"]
        on_ctc_down, on_gross_up = [], []

        for index, employee in enumerate(employees):
            # --keep runs this against people who may already have one; two
            # active contracts on the same employee is what the model itself
            # refuses, not a case worth working around.
            if Contract.objects.filter(
                employee_id=employee, contract_status="active"
            ).exists():
                continue

            filing_status = statuses[index % len(statuses)] if statuses else None
            common = dict(
                contract_name=f"{employee.get_full_name()} — Standard",
                employee_id=employee,
                contract_start_date=datetime.date(2024, 1, 1),
                contract_status="active",
                filing_status=filing_status,
                calculate_daily_leave_amount=True,
                daily_leave_amount_base=bases[index % len(bases)],
                daily_leave_amount_divisor=divisors[index % len(divisors)],
                deduct_leave_from_basic_pay=True,
            )

            if index % 3 == 2:
                # The wage is left at 0 rather than omitted: resolve_basic_pay_
                # source reads contract.pay_rate, and a falsy rate is what
                # sends it to the flagged component instead of double-counting
                # the wage as basic pay on top of the package.
                Contract.objects.create(
                    **common,
                    wage_type="monthly",
                    wage=0,
                    monthly_ctc=round(45000 + (index % 7) * 6000, 2),
                    salary_structure_id=ctc_down,
                )
                on_ctc_down.append(employee)
            else:
                Contract.objects.create(
                    **common,
                    wage_type="monthly",
                    wage=round(28000 + (index % 9) * 4000, 2),
                    salary_structure_id=gross_up,
                )
                on_gross_up.append(employee)

        # Structure-specific components (include_active_employees=False on
        # them, above) are scoped here rather than reaching everyone: only now
        # is it known who ended up on which structure. Contract.create()
        # setting salary_structure_id does not itself do this wiring --
        # that only happens through Contract.set_salary_structure(), a
        # separate method nothing here calls, which is why it has to be done
        # explicitly.
        for structure, group in ((gross_up, on_gross_up), (ctc_down, on_ctc_down)):
            if not group:
                continue
            for allowance in structure.allowances.filter(
                include_active_employees=False
            ):
                allowance.specific_employees.add(*group)
            for deduction in structure.deductions.filter(
                include_active_employees=False
            ):
                deduction.specific_employees.add(*group)

        self.stdout.write(
            f"  {len(on_ctc_down)} on CTC Down, {len(on_gross_up)} on Gross Up"
        )
        return employees

    # -- attendance -------------------------------------------------------

    def _attendance(self, employees, start, end):
        """
        A window of attendance with the cases the review step exists to catch.

        A demo where everybody worked every day proves nothing: the blocked
        count is zero, the loss-of-pay column is zero, and the regularisation
        flow has nothing to regularise.
        """
        from attendance.models import Attendance

        self.stdout.write(f"Generating attendance {start} to {end}...")

        # The window is rebuilt, not added to. Attendance is unique per
        # employee per date, so leaving what is there means either a collision
        # or -- worse, with ignore_conflicts -- a month that is half the old
        # data and half the new, which no payslip would reconcile against.
        stale = Attendance.objects.filter(
            employee_id__in=employees, attendance_date__range=(start, end)
        )
        removed = stale.count()
        if removed:
            stale.delete()
            self.stdout.write(f"  cleared {removed} existing records in the window")
        _clear_leave(employees, start, end, self.stdout)
        days = [
            start + datetime.timedelta(days=offset)
            for offset in range((end - start).days + 1)
            if (start + datetime.timedelta(days=offset)).weekday() < 5
        ]

        paid_type, unpaid_type = _leave_types()
        # Fractions of the roster, not fixed slice bounds -- a 12-person demo
        # (as the tests use) otherwise gets zero deliberate conflicts, since
        # employees[5:8] falls past a list that short.
        count = len(employees)
        joiner = employees[count // 4] if count > 4 else None
        conflicted = employees[count // 2 : count // 2 + max(1, count // 6)]
        heavy_lop = employees[-2] if count > 2 else None
        no_attendance = employees[-1] if count > 1 else None

        records, leaves = [], 0
        for index, employee in enumerate(employees):
            # Leave is decided first, because attendance has to avoid it.
            # Somebody on approved leave did not also clock in, and generating
            # both puts an unresolved conflict on every person who took a day
            # off -- which blocked 18 of 45 and made a working demo look broken.
            on_leave, conflict_days = _leave_plan(
                index,
                days,
                paid_type,
                unpaid_type,
                deliberate=employee in conflicted,
            )

            if employee == no_attendance:
                _book_leave(employee, on_leave, conflict_days)
                leaves += len(on_leave) + len(conflict_days)
                continue  # every run has one; the review warns about them

            for day in days:
                # Except for the few meant to collide, which is the case the
                # review step and the regularisation flow exist for.
                if day in on_leave and day not in conflict_days:
                    continue
                if employee == joiner and day < start + datetime.timedelta(days=20):
                    continue  # started mid-window
                if employee == heavy_lop and day.day % 3:
                    continue  # in about one day in three

                roll = random.random()
                if roll < 0.04:
                    continue  # absent
                if roll < 0.09:
                    worked, out = "04:30", "13:30"  # half day
                elif roll < 0.16:
                    worked, out = "09:45", "18:45"  # overtime
                else:
                    worked, out = "08:30", "17:30"

                records.append(
                    Attendance(
                        employee_id=employee,
                        attendance_date=day,
                        attendance_clock_in_date=day,
                        attendance_clock_in=datetime.time(9, 0),
                        attendance_clock_out_date=day,
                        attendance_clock_out=_time(out),
                        attendance_worked_hour=worked,
                        attendance_overtime="01:15" if worked == "09:45" else "00:00",
                        minimum_hour="08:00",
                        at_work_second=_secs(worked),
                        overtime_second=4500 if worked == "09:45" else 0,
                        attendance_validated=True,
                    )
                )

            _book_leave(employee, on_leave, conflict_days)
            leaves += len(on_leave) + len(conflict_days)

        Attendance.objects.bulk_create(records, batch_size=500)
        self.stdout.write(
            f"  {len(records)} attendance records, {leaves} leave requests"
        )

    # -- the rest of the sections -----------------------------------------

    def _loans_and_claims(self, employees):
        from payroll.models.models import LoanAccount, Reimbursement

        self.stdout.write("Adding loans and claims...")
        today = datetime.date.today()
        loans = claims = 0

        with _as_request():
            loans, claims = self._write_loans_and_claims(employees, today)

        self.stdout.write(f"  {loans} loans/advances, {claims} reimbursements")

    def _write_loans_and_claims(self, employees, today):
        from payroll.models.models import LoanAccount, Reimbursement

        loans = claims = 0
        for offset, employee in enumerate(employees[:4]):
            LoanAccount.objects.create(
                employee_id=employee,
                title="Staff loan" if offset % 2 else "Salary advance",
                type="loan" if offset % 2 else "advanced_salary",
                loan_amount=60000 if offset % 2 else 20000,
                provided_date=today - datetime.timedelta(days=60),
                installments=12 if offset % 2 else 4,
                installment_amount=5000,
                installment_start_date=today - datetime.timedelta(days=30),
                description="Demo fixture.",
            )
            loans += 1

        # Reimbursement.save() also refuses a claim with no attachment --
        # written for a request cycle, which a command is not.
        for offset, employee in enumerate(employees[4:8]):
            claim = Reimbursement(
                employee_id=employee,
                title="Travel claim" if offset % 2 else "Medical claim",
                type="reimbursement",
                allowance_on=today - datetime.timedelta(days=10),
                amount=2500 if offset % 2 else 4000,
                status="approved",
            )
            claim.attachment.save(
                "receipt.txt", ContentFile(b"Demo fixture receipt."), save=False
            )
            claim.save()
            claims += 1

        return loans, claims

    def _run(self, employees, start):
        """
        A finished run for the first whole month, through the real engine.

        Generated rather than inserted: a payslip built by hand agrees with
        nothing, and the point of the demo is that the runs list, the payslips
        and the contributions page all show the same figures.
        """
        import calendar

        from payroll.methods import batch_run

        month_end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
        self.stdout.write(f"Running payroll for {start} to {month_end}...")

        review = batch_run.review(employees, start, month_end)
        ready = [row["employee"] for row in review["rows"] if not row["blocked"]]
        self.stdout.write(
            f"  {len(ready)} ready, {review['blocked_count']} blocked, "
            f"{len(review['excluded'])} excluded"
        )
        if not ready:
            return

        batch = batch_run.create_batch(
            name=start.strftime("%B %Y"),
            start_date=start,
            end_date=month_end,
            employees=ready,
        )
        while batch_run.generate_slice(batch, size=25):
            pass
        batch.refresh_from_db()
        self.stdout.write(
            f"  {batch.generated_count} payslips, {batch.failed_count} failed, "
            f"net {batch.total_net:,.2f}"
        )

    def _report(self, start, end):
        from payroll.models.models import (
            Allowance,
            Contract,
            Deduction,
            FilingStatus,
            PayrollBatch,
            Payslip,
        )

        self.stdout.write(self.style.SUCCESS("\nDone."))
        for label, count in (
            ("Filing statuses", FilingStatus.objects.count()),
            ("Earnings", Allowance.objects.count()),
            ("Deductions", Deduction.objects.count()),
            ("Contracts", Contract.objects.count()),
            ("Payroll runs", PayrollBatch.objects.count()),
            ("Payslips", Payslip.objects.count()),
        ):
            self.stdout.write(f"  {label:18} {count}")
        self.stdout.write(f"  {'Window':18} {start} to {end}")


# ---------------------------------------------------------------------------


def _date(value, fallback):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def _time(hhmm):
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime.time(hour, minute)


def _secs(hhmm):
    hour, minute = (int(part) for part in hhmm.split(":"))
    return hour * 3600 + minute * 60


def _historical(name):
    from django.apps import apps

    try:
        return apps.get_model("payroll", name)
    except LookupError:
        return None


@contextlib.contextmanager
def _as_request():
    """
    Stand in a request, for model code that expects to be inside one.

    Several payroll models read the current user from thread-locals to decide
    what the saver is allowed to do. In a command there is nobody, so they hit
    None. A superuser is the right stand-in: a fixture is not being restricted
    by anybody's permissions.
    """
    from django.contrib.auth import get_user_model

    from horilla.horilla_middlewares import _thread_locals

    # A real user row, because HorillaModel.save() assigns request.user to
    # created_by and that has to be a HorillaUser. Where there is no superuser
    # -- a fresh database, or a test -- the first user is promoted in memory
    # and never saved: has_perm() then answers True without the fixture
    # granting anybody anything that outlives it.
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first()
    if user is None:
        user = User.objects.first()
        if user is not None:
            user.is_superuser = True  # in memory only; never saved

    previous = getattr(_thread_locals, "request", None)

    class _Request:
        def __init__(self, who):
            self.user = who
            self.session = {}

    _thread_locals.request = _Request(user)
    try:
        yield
    finally:
        _thread_locals.request = previous


def _clear_leave(employees, start, end, out):
    """
    Leave in the window, for the same reason: the fixtures create their own,
    and an old request overlapping a new one is a conflict nobody authored.
    """
    from leave.models import LeaveRequest

    stale = LeaveRequest.objects.filter(
        employee_id__in=employees, start_date__range=(start, end)
    )
    removed = stale.count()
    if removed:
        stale.delete()
        out.write(f"  cleared {removed} existing leave requests in the window")


def _leave_types():
    """
    A paid and an unpaid leave type, creating them if the install has none.

    Every conflict scenario the demo builds -- the deliberate ones the review
    step blocks on, and the ordinary paid/unpaid leave everyone else takes --
    needs both to exist. A bare create_summary_fixtures-style warn-and-skip
    would leave a demo with no conflicts and prove nothing about the review.
    """
    from leave.models import LeaveType

    # .first(), not get_or_create(): a real install can already have several
    # paid leave types (Casual, Sick, ...), and get_or_create's implicit get()
    # raises on more than one match. Only create when the filter comes back
    # empty.
    paid = LeaveType.objects.filter(payment="paid").first()
    if paid is None:
        paid = LeaveType.objects.create(name="Paid Leave (Demo)", payment="paid")

    unpaid = LeaveType.objects.filter(payment="unpaid").first()
    if unpaid is None:
        unpaid = LeaveType.objects.create(name="Unpaid Leave (Demo)", payment="unpaid")

    return paid, unpaid


def _leave_plan(index, days, paid_type, unpaid_type, deliberate):
    """
    Which days this person is on leave, and which of those also carry
    attendance on purpose.

    Returned rather than written, so the attendance loop can avoid the leave
    days -- the two have to be decided together or they contradict each other.
    """
    on_leave, conflicts = {}, set()

    if paid_type and index % 4 == 0:
        first = days[len(days) // 3]
        for day in (first, _next_working(days, first)):
            if day:
                on_leave[day] = paid_type

    if unpaid_type and index % 7 == 0:
        on_leave[days[len(days) // 2]] = unpaid_type

    if deliberate and paid_type:
        # Three days of approved leave over days the person also clocked in
        # for: an unresolved conflict, which blocks the run until somebody
        # regularises it. Every demo needs a few.
        for offset in range(3):
            day = days[4 + offset]
            on_leave[day] = paid_type
            conflicts.add(day)

    return on_leave, conflicts


def _next_working(days, after):
    """The next day in the working-day list, or None at the end of it."""
    position = days.index(after)
    return days[position + 1] if position + 1 < len(days) else None


def _book_leave(employee, on_leave, conflict_days):
    """
    The approved leave itself. One request per day rather than per run, so a
    person's leave days do not have to be contiguous.
    """
    from leave.models import LeaveRequest

    for day, leave_type in on_leave.items():
        LeaveRequest.objects.create(
            employee_id=employee,
            leave_type_id=leave_type,
            start_date=day,
            end_date=day,
            status="approved",
        )
