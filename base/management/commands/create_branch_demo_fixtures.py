"""
Management command: create_branch_demo_fixtures
--------------------------------------------------
Replaces all data with a two-company ("two branches") demo dataset: 60
employees (30 per company), real day-by-day Attendance running up to today,
real LeaveRequest rows spanning the month before last through 30 days into
the future, and Payslips for the one most-recently-closed calendar month
only.

Built on the same two-layer trick as create_precise_payroll_fixtures.py:
real Attendance/LeaveRequest rows for a calendar that looks genuine, plus an
AttendanceSummaryOverride stating the exact present/paid_leave/unpaid_leave
counts for whichever period a payslip is about to be built from. That
override is applied last, over whatever the day-by-day rows computed, so the
payslip's own paid_days + unpaid_days is guaranteed to reconcile against
that period's calendar days by construction -- not by hoping every
downstream classification (week off, holiday, conflict) landed as intended.

Only the last fully-closed month gets that treatment, because only that
month gets a payslip. Everything else here -- the month before it, the
current month-to-date, and any future leave -- is real rows with no override
and no reconciliation guarantee: attendance can never be later than today
(nobody has "attended" a day that hasn't happened), but leave is routinely
approved ahead of time, so it is the one row type allowed past that line.

Run:
    python manage.py create_branch_demo_fixtures
"""

import calendar
import contextlib
import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

EMPLOYEES_PER_COMPANY = 30
WAGE_BY_COMPANY = {"Branch A": 30000.0, "Branch B": 28000.0}
# Real files already on disk under media/base/icon/ -- the same ones
# load_data/base_data.json points its own demo companies at -- so each
# branch gets a distinct, real icon rather than the "no icon" fallback.
ICON_BY_COMPANY = {
    "Branch A": "base/icon/Horilla_1.png",
    "Branch B": "base/icon/Horilla_2.png",
}
WEEKEND_CHECKINS_PER_COMPANY = 6
CTC_DOWN_WAGE_TO_CTC_MULTIPLIER = 2.2
# 9 of every 30 (30%) on CTC Down -- the same ratio
# create_precise_payroll_fixtures.py uses, so both modes show up as
# themselves rather than one crowding out the other.
CTC_DOWN_INDEXES = set(range(21, 30))

# Per-employee leave-day count, 0 through 4, reused with different offsets
# for the payroll month vs. the month before it so the two months don't read
# identically.
LEAVE_DAYS_BY_INDEX = [0, 1, 2, 3, 4, 0, 1, 2, 3, 4]
OLDER_MONTH_LEAVE_OFFSET = 3

EMPLOYEE_NAMES = [
    ("Olivia", "Bennett"),
    ("Ethan", "Brooks"),
    ("Sophia", "Ramirez"),
    ("Liam", "Foster"),
    ("Ava", "Whitfield"),
    ("Noah", "Griffin"),
    ("Isabella", "Park"),
    ("Mason", "Delgado"),
    ("Mia", "Sullivan"),
    ("Lucas", "Whitaker"),
    ("Emma", "Coleman"),
    ("James", "Carter"),
    ("Charlotte", "Reyes"),
    ("Benjamin", "Hayes"),
    ("Amelia", "Torres"),
    ("Henry", "Mitchell"),
    ("Harper", "Simmons"),
    ("Alexander", "Price"),
    ("Evelyn", "Russell"),
    ("Sebastian", "Ward"),
    ("Abigail", "Fox"),
    ("Jack", "Chambers"),
    ("Emily", "Nash"),
    ("Daniel", "Holloway"),
    ("Elizabeth", "Marsh"),
    ("Matthew", "Pratt"),
    ("Sofia", "Lane"),
    ("David", "Osborne"),
    ("Victoria", "Hale"),
    ("Joseph", "Doyle"),
]

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday"]

# The same department/job-position taxonomy base/demo_data/catalog.py already
# standardises the main demo dataset onto -- reused rather than invented a
# second time, so this dataset's org chart reads like the rest of the app's.
DEPARTMENT_STRUCTURE = [
    ("Engineering", ["Software Engineer", "Backend Engineer", "Frontend Engineer"]),
    (
        "Sales",
        ["Sales Representative", "Sales Manager", "Business Development Manager"],
    ),
    ("Human Resources", ["HR Manager", "HR Business Partner", "Recruiter"]),
    ("Marketing", ["Marketing Specialist", "Digital Marketing Specialist"]),
    ("Finance", ["Financial Analyst", "Accounts Payable Clerk"]),
]

COMPANIES = [
    {"name": "Branch A"},
    {
        "name": "Branch B",
        "address": "88 Secondary Ave",
        "city": "Riverside",
        "zip": "94022",
    },
]


def _add_months(d, delta):
    m = d.month - 1 + delta
    y = d.year + m // 12
    m = m % 12 + 1
    return datetime.date(y, m, 1)


def _weekdays(start, end):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += datetime.timedelta(days=1)


class Command(BaseCommand):
    help = (
        "Replace all data with a two-company, 60-employee demo dataset: "
        "attendance to date, leave into the future, payroll for last month."
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Flushing the database..."))
        call_command("flush", "--no-input", verbosity=0)

        self.stdout.write("Loading tax packs and standard components...")
        call_command("seed_tax_packs", verbosity=0)
        call_command("sync_system_components", verbosity=0)

        paid_type, unpaid_type = self._leave_types()

        today = datetime.date.today()
        this_month_start = datetime.date(today.year, today.month, 1)
        last_month_start = _add_months(this_month_start, -1)
        last_month_end = this_month_start - datetime.timedelta(days=1)
        older_month_start = _add_months(this_month_start, -2)
        older_month_end = last_month_start - datetime.timedelta(days=1)
        leave_horizon_end = today + datetime.timedelta(days=30)

        self.stdout.write(
            f"Windows -- older month: {older_month_start}..{older_month_end}, "
            f"payroll month: {last_month_start}..{last_month_end}, "
            f"current month to date: {this_month_start}..{today}, "
            f"leave horizon through: {leave_horizon_end}"
        )

        payslips_created = 0
        runs_created = 0
        total_employees = 0
        for company_spec in COMPANIES:
            self.stdout.write(f"\n=== {company_spec['name']} ===")
            company, shift = self._scaffolding(company_spec)
            if company_spec is COMPANIES[0]:
                self._superuser(company)
            wage = WAGE_BY_COMPANY.get(company_spec["name"], 30000.0)
            gross_up, ctc_down = self._structure(company, wage)
            position_pool = self._departments(company)
            employees = self._employees(
                company, shift, gross_up, ctc_down, wage, position_pool, today
            )
            total_employees += len(employees)
            self._announcement(company, today)

            for index, employee in enumerate(employees):
                self._extra_coverage_for(
                    employee,
                    index,
                    shift,
                    older_month_start,
                    older_month_end,
                    this_month_start,
                    today,
                    leave_horizon_end,
                    paid_type,
                    unpaid_type,
                )
                self._payroll_month_for(
                    employee,
                    index,
                    shift,
                    last_month_start,
                    last_month_end,
                    paid_type,
                    unpaid_type,
                )
                summary = self._verified_summary(
                    employee, last_month_start, last_month_end
                )
                self.stdout.write(
                    f"  {employee.get_full_name():20s}  "
                    f"present={summary['present']:>4}  "
                    f"paid_leave={summary['paid_leave']:>3}  "
                    f"unpaid_leave={summary['unpaid_leave']:>3}  "
                    f"paid_days={summary['paid_days']:>5}  "
                    f"unpaid_days={summary['unpaid_days']:>4}"
                )

            self._ongoing_leave_for(employees, today, paid_type, unpaid_type)
            self._today_attendance_for(employees, today, shift)
            self._pending_attendance_request_for(employees, older_month_start)
            self._pending_leave_for(employees, today, unpaid_type)
            with _as_request():
                self._loans_for(employees, today)
                self._reimbursements_for(employees, today)
                self._policy_and_discipline(company, employees)

            batch = self._run_payroll_batch(
                employees, last_month_start, last_month_end, company
            )
            payslips_created += batch.generated_count
            runs_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {len(COMPANIES)} companies, {total_employees} employees, "
                f"{runs_created} payroll runs, {payslips_created} payslips for "
                f"{last_month_start:%b %Y} -- every one verified paid_days + "
                f"unpaid_days == that month's calendar days. Attendance runs "
                f"through {today}; leave runs through {leave_horizon_end}."
            )
        )

    # -- scaffolding ---------------------------------------------------------

    def _scaffolding(self, company_spec):
        """
        A company and a shift this command fully controls, per branch --
        see create_precise_payroll_fixtures.py's own docstring for why a
        shared/loaded shift's week-off pattern is the wrong foundation here.
        EmployeeShiftSchedule only feeds the per-day worked-hour target;
        CompanyLeaves is the entirely separate, company-wide model that
        actually decides week-off classification, so both are built here,
        once per company.
        """
        from base.models import (
            CompanyLeaves,
            EmployeeShift,
            EmployeeShiftDay,
            EmployeeShiftSchedule,
        )
        from horilla.testkit import make_company

        name = company_spec["name"]
        overrides = {k: v for k, v in company_spec.items() if k != "name"}
        company = make_company(name, **overrides)
        icon_path = ICON_BY_COMPANY.get(name)
        if icon_path:
            company.icon = icon_path
            company.save(update_fields=["icon"])

        shift = EmployeeShift.objects.create(employee_shift=f"{name} Shift (Mon-Fri)")
        shift.company_id.add(company)
        for day_name in WEEKDAY_NAMES:
            day, _created = EmployeeShiftDay.objects.get_or_create(day=day_name)
            EmployeeShiftSchedule.objects.create(day=day, shift_id=shift)

        # "5"/"6" = Saturday/Sunday (base.models.WEEK_DAYS). based_on_week
        # left blank: every week, not one specific week of the month.
        for week_day in ("5", "6"):
            weekly_off, _created = CompanyLeaves.objects.get_or_create(
                based_on_week=None,
                based_on_week_day=week_day,
            )
            weekly_off.company_id.add(company)

        self.stdout.write(f"  Company: {company}, shift: {shift.employee_shift}")
        return company, shift

    def _superuser(self, company):
        """
        Adam Admin -- the same name Horilla's own load_data/user_data.json
        seeds as pk=1 ("admin", is_superuser). ``flush`` wipes every
        HorillaUser along with everything else, and a demo dataset nobody
        can log in to isn't actually usable, so it's recreated here rather
        than left for whoever runs this command to notice is missing.
        """
        from horilla.testkit import make_employee, make_user

        user = make_user(
            "admin",
            password="admin",
            email="adam@horilla.com",
            is_superuser=True,
        )
        make_employee(
            company=company,
            email="adam@horilla.com",
            first_name="Adam",
            last_name="Admin",
            user=user,
        )
        self.stdout.write("  Superuser: admin / admin (Adam Admin)")

    # -- components/structure -------------------------------------------------

    def _structure(self, company, wage):
        """
        Two structures per company, each with its own components (not
        shared across branches) so every row carries a real company_id and
        a "BASIC"/"HRA"/etc. code lookup never has to guess which branch's
        component it means.
        """
        from payroll.models.models import Allowance, Deduction, SalaryStructure

        hra = Allowance.objects.create(
            title="House Rent Allowance",
            code="HRA",
            sequence=10,
            company_id=company,
            is_fixed=False,
            based_on="basic_pay",
            rate=40.0,
            is_taxable=True,
        )
        special = Allowance.objects.create(
            title="Special Allowance",
            code="SPL",
            sequence=20,
            company_id=company,
            is_fixed=True,
            amount=2000.0,
            is_taxable=True,
        )
        pf = Deduction.objects.create(
            title="Provident Fund (PF)",
            code="PF",
            sequence=10,
            company_id=company,
            is_fixed=False,
            based_on="basic_pay",
            rate=12.0,
            employer_rate=12.0,
            is_pretax=True,
        )
        pt = Deduction.objects.create(
            title="Professional Tax",
            code="PT",
            sequence=20,
            company_id=company,
            is_fixed=True,
            amount=200.0,
            is_pretax=False,
        )
        gross_up = SalaryStructure.objects.create(
            title=f"{company.company} — Standard",
            company_id=company,
            structure_mode="gross_up",
        )
        gross_up.allowances.set([hra, special])
        gross_up.deductions.set([pf, pt])

        basic = Allowance.objects.create(
            title="Basic Pay",
            code="BASIC",
            sequence=5,
            company_id=company,
            is_basic_pay=True,
            is_fixed=False,
            based_on="formula",
            formula="CTC * 0.4",
            is_taxable=True,
        )
        ctc_hra = Allowance.objects.create(
            title="House Rent Allowance",
            code="CHRA",
            sequence=10,
            company_id=company,
            is_fixed=False,
            based_on="component",
            percentage_of_code="BASIC",
            rate=40.0,
            is_taxable=True,
        )
        flex = Allowance.objects.create(
            title="Flexible Benefits (Balance)",
            code="FLEX",
            sequence=90,
            company_id=company,
            is_fixed=False,
            based_on="balance",
            is_taxable=True,
        )
        ctc_down = SalaryStructure.objects.create(
            title=f"{company.company} — CTC Down",
            company_id=company,
            structure_mode="ctc_down",
        )
        ctc_down.allowances.set([basic, ctc_hra, flex])
        ctc_down.deductions.set([pf, pt])

        self.stdout.write(f"  Structure: {gross_up.title} (Gross Up, wage {wage})")
        self.stdout.write(
            f"  Structure: {ctc_down.title} "
            f"(CTC Down, CTC {round(wage * CTC_DOWN_WAGE_TO_CTC_MULTIPLIER, 2)})"
        )
        return gross_up, ctc_down

    def _departments(self, company):
        """
        Department -> JobPosition -> JobRole, built fresh per company (like
        the salary components above) rather than shared, so each branch's
        org chart is its own real rows, not a borrowed label.

        Returns a flat, repeating list of (department, job_position,
        job_role) tuples for _employees() to cycle an index through.
        """
        from base.models import Department, JobPosition, JobRole

        pool = []
        for department_name, position_names in DEPARTMENT_STRUCTURE:
            department = Department.objects.create(department=department_name)
            department.company_id.add(company)
            for position_name in position_names:
                position = JobPosition.objects.create(
                    job_position=position_name,
                    department_id=department,
                )
                position.company_id.add(company)
                role = JobRole.objects.create(
                    job_role=position_name,
                    job_position_id=position,
                )
                role.company_id.add(company)
                pool.append((department, position, role))

        self.stdout.write(
            f"  {len(DEPARTMENT_STRUCTURE)} departments, {len(pool)} job positions"
        )
        return pool

    # -- people ----------------------------------------------------------------

    def _employees(
        self, company, shift, gross_up, ctc_down, wage, position_pool, today
    ):
        """
        Contract.salary_structure_id is never set directly on ``create()``
        -- only ``set_salary_structure()`` adds the employee to the
        structure's Allowance/Deduction rows' ``specific_employees``, which
        is what calculate_pre_tax_deduction / calculate_post_tax_deduction
        actually filter on. See create_precise_payroll_fixtures.py for the
        failure mode this sidesteps.
        """
        from employee.models import Employee, EmployeeWorkInformation
        from horilla.testkit import make_employee
        from payroll.models.models import Contract

        domain = company.company.lower().replace(" ", "-")
        # Adam Admin as the chart's root, one employee per department
        # promoted to that department's head (reporting to Admin) the first
        # time that department is seen, everyone else in it reporting to
        # that head -- so the Organization Chart has more than a lone node.
        admin_employee = Employee.objects.filter(email="adam@horilla.com").first()
        dept_heads = {}
        employees = []
        for i in range(EMPLOYEES_PER_COMPANY):
            first, last = EMPLOYEE_NAMES[i % len(EMPLOYEE_NAMES)]
            is_ctc_down = i in CTC_DOWN_INDEXES
            employee = make_employee(
                company=company,
                email=f"{first.lower()}.{last.lower()}{i}@{domain}.payroll.test",
                first_name=first,
                last_name=last,
                shift=shift,
            )
            Contract.objects.filter(employee_id=employee).delete()
            contract = Contract.objects.create(
                contract_name=f"{employee.get_full_name()} — Standard",
                employee_id=employee,
                contract_start_date=datetime.date(2024, 1, 1),
                contract_status="active",
                wage_type="monthly",
                wage=wage,
                calculate_daily_leave_amount=True,
                daily_leave_amount_divisor="calendar_days",
                deduct_leave_from_basic_pay=True,
            )
            if is_ctc_down:
                contract.set_salary_structure(ctc_down)
                Contract.objects.filter(pk=contract.pk).update(
                    monthly_ctc=round(wage * CTC_DOWN_WAGE_TO_CTC_MULTIPLIER, 2),
                    wage=0,
                    daily_leave_amount_base="monthly_ctc",
                )
            else:
                contract.set_salary_structure(gross_up)
                Contract.objects.filter(pk=contract.pk).update(
                    daily_leave_amount_base="wage",
                )

            # Department/dob/anniversary are set *after* the contract, never
            # before: Contract.save() does
            # `self.employee_id.employee_work_info.save()` (to sync
            # basic_salary), and that re-saves whatever EmployeeWorkInformation
            # snapshot was cached on the `employee` object at Contract-creation
            # time -- which, if these updates ran first, would be overwritten
            # right back to blank by that stale full save().
            department, job_position, job_role = position_pool[i % len(position_pool)]
            manager = dept_heads.get(department.pk, admin_employee)
            EmployeeWorkInformation.objects.filter(employee_id=employee).update(
                department_id=department,
                job_position_id=job_position,
                job_role_id=job_role,
                reporting_manager_id=manager,
            )
            dept_heads.setdefault(department.pk, employee)
            # A couple of employees per company get a dob/anniversary landing
            # in the current month, so the dashboard's Birthdays &
            # Anniversaries widget (which only ever looks at *this* month)
            # has something to show instead of reading empty by construction.
            if i == 2:
                Employee.objects.filter(pk=employee.pk).update(
                    dob=datetime.date(1990, today.month, min(today.day, 28))
                )
            if i == 7:
                EmployeeWorkInformation.objects.filter(employee_id=employee).update(
                    date_joining=datetime.date(
                        today.year - 3, today.month, min(today.day, 28)
                    )
                )
            employees.append(employee)

        ctc_down_count = len(CTC_DOWN_INDEXES)
        self.stdout.write(
            f"  {len(employees)} employees: {len(employees) - ctc_down_count} on Gross Up "
            f"({wage} monthly wage), {ctc_down_count} on CTC Down "
            f"({round(wage * CTC_DOWN_WAGE_TO_CTC_MULTIPLIER, 2)} monthly CTC)"
        )
        return employees

    def _leave_types(self):
        from leave.models import LeaveType

        paid_type, _created = LeaveType.objects.get_or_create(
            name="Fixture Paid Leave",
            defaults={"payment": "paid", "limit_leave": False},
        )
        unpaid_type, _created = LeaveType.objects.get_or_create(
            name="Fixture Unpaid Leave",
            defaults={"payment": "unpaid", "limit_leave": False},
        )
        return paid_type, unpaid_type

    def _announcement(self, company, today):
        """One welcome announcement per branch, so the dashboard's
        Announcements widget isn't empty by construction either."""
        from base.models import Announcement

        announcement = Announcement.objects.create(
            title=f"Welcome to {company.company}",
            description="Welcome aboard! Check the Policies page for everything you need to know.",
            expire_date=today + datetime.timedelta(days=30),
        )
        announcement.company_id.add(company)

    # -- attendance / leave outside the payroll month ---------------------------

    def _extra_coverage_for(
        self,
        employee,
        index,
        shift,
        older_start,
        older_end,
        current_start,
        current_end,
        leave_horizon_end,
        paid_type,
        unpaid_type,
    ):
        """
        Real rows for everything the payroll month's reconciliation doesn't
        need to be exact about: the month before it (variety on the
        Attendance/Leave screens), the current month up to today (attendance
        can never be later than today), and -- the one place leave is
        allowed ahead of where attendance can reach -- approved leave dated
        after today. No AttendanceSummaryOverride here: no payslip reads out
        of these three windows, so there is nothing that must reconcile.
        """
        from attendance.models import Attendance
        from leave.models import LeaveRequest

        # Older month: a scattered few leave days (a different slice of the
        # pattern than the payroll month uses below), the rest present.
        older_weekdays = list(_weekdays(older_start, older_end))
        older_leave_count = min(
            LEAVE_DAYS_BY_INDEX[
                (index + OLDER_MONTH_LEAVE_OFFSET) % len(LEAVE_DAYS_BY_INDEX)
            ],
            max(len(older_weekdays) - 1, 0),
        )
        older_leave_days = (
            older_weekdays[:older_leave_count] if older_leave_count else []
        )
        older_present_days = [d for d in older_weekdays if d not in older_leave_days]

        for day in older_present_days:
            Attendance.objects.create(
                employee_id=employee,
                attendance_date=day,
                shift_id=shift,
                attendance_clock_in=datetime.time(9, 0),
                attendance_clock_out=datetime.time(18, 0),
                attendance_worked_hour="09:00",
                minimum_hour="08:00",
                attendance_validated=True,
            )
        for position, day in enumerate(older_leave_days):
            leave_type = paid_type if position % 2 == 0 else unpaid_type
            LeaveRequest.objects.create(
                employee_id=employee,
                leave_type_id=leave_type,
                start_date=day,
                end_date=day,
                status="approved",
                start_date_breakdown="full_day",
                end_date_breakdown="full_day",
                description="Branch demo — prior month",
            )

        # Current month to date: present every weekday, except a light
        # once-in-five-employees single unpaid day, so the ongoing month
        # isn't suspiciously perfect either.
        current_weekdays = list(_weekdays(current_start, current_end))
        skip_day = None
        if current_weekdays and index % 5 == 0:
            skip_day = current_weekdays[-1]
            LeaveRequest.objects.create(
                employee_id=employee,
                leave_type_id=unpaid_type,
                start_date=skip_day,
                end_date=skip_day,
                status="approved",
                start_date_breakdown="full_day",
                end_date_breakdown="full_day",
                description="Branch demo — current month",
            )
        for day in current_weekdays:
            if day == skip_day:
                continue
            Attendance.objects.create(
                employee_id=employee,
                attendance_date=day,
                shift_id=shift,
                attendance_clock_in=datetime.time(9, 0),
                attendance_clock_out=datetime.time(18, 0),
                attendance_worked_hour="09:00",
                minimum_hour="08:00",
                attendance_validated=True,
            )

        # Future: every third employee has a short approved leave block
        # ahead of today -- the one case where a leave row legitimately
        # outruns attendance, since nobody has attended a day that hasn't
        # happened yet.
        if index % 3 == 0:
            future_start = current_end + datetime.timedelta(days=7 + (index % 10))
            if future_start <= leave_horizon_end:
                future_end = min(
                    future_start + datetime.timedelta(days=1), leave_horizon_end
                )
                leave_type = paid_type if index % 2 == 0 else unpaid_type
                LeaveRequest.objects.create(
                    employee_id=employee,
                    leave_type_id=leave_type,
                    start_date=future_start,
                    end_date=future_end,
                    status="approved",
                    start_date_breakdown="full_day",
                    end_date_breakdown="full_day",
                    description="Branch demo — upcoming leave",
                )

    # -- the one month a payslip actually reads ---------------------------------

    def _payroll_month_for(
        self, employee, index, shift, start, end, paid_type, unpaid_type
    ):
        """
        Same two-layer trick as create_precise_payroll_fixtures.py's
        _attendance_for, scoped to the one month a payslip is about to be
        built from: real rows for a calendar that looks genuine, plus an
        AttendanceSummaryOverride stating the same counts outright, so the
        payslip's own paid_days + unpaid_days is guaranteed to reconcile
        against this month's calendar days by construction.
        """
        from attendance.models import Attendance, AttendanceSummaryOverride
        from leave.models import LeaveRequest

        Attendance.objects.filter(
            employee_id=employee, attendance_date__range=(start, end)
        ).delete()
        LeaveRequest.objects.filter(
            employee_id=employee, start_date__range=(start, end)
        ).delete()

        weekdays = list(_weekdays(start, end))
        leave_count = min(
            LEAVE_DAYS_BY_INDEX[index % len(LEAVE_DAYS_BY_INDEX)],
            max(len(weekdays) - 1, 0),
        )
        leave_days = weekdays[-leave_count:] if leave_count else []
        present_days = [d for d in weekdays if d not in leave_days]

        for day in present_days:
            Attendance.objects.create(
                employee_id=employee,
                attendance_date=day,
                shift_id=shift,
                attendance_clock_in=datetime.time(9, 0),
                attendance_clock_out=datetime.time(18, 0),
                attendance_worked_hour="09:00",
                minimum_hour="08:00",
                attendance_validated=True,
            )

        paid_leave_count = 0
        unpaid_leave_count = 0
        for position, day in enumerate(leave_days):
            is_paid = position % 2 == 0
            leave_type = paid_type if is_paid else unpaid_type
            if is_paid:
                paid_leave_count += 1
            else:
                unpaid_leave_count += 1
            LeaveRequest.objects.create(
                employee_id=employee,
                leave_type_id=leave_type,
                start_date=day,
                end_date=day,
                status="approved",
                start_date_breakdown="full_day",
                end_date_breakdown="full_day",
                description="Branch demo — payroll month",
            )

        # Balanced by construction: present + paid_leave + unpaid_leave +
        # absent(0) is exactly len(weekdays), and week_off/holiday are
        # whatever this command's own shift/calendar say for the period --
        # so overriding present/paid_leave/unpaid_leave/absent to these
        # counts, on top of that real week_off/holiday, always reconciles.
        AttendanceSummaryOverride.objects.update_or_create(
            employee_id=employee,
            from_date=start,
            to_date=end,
            defaults={
                "present": float(len(present_days)),
                "paid_leave": float(paid_leave_count),
                "unpaid_leave": float(unpaid_leave_count),
                "absent": 0.0,
                "note": "Branch demo — stated totals",
            },
        )

    def _verified_summary(self, employee, start, end):
        """
        The real attendance summary, fetched the same way the payroll
        engine does -- and checked, here, before anything is saved.
        Reconciliation failing stops the whole command rather than being
        logged and moved past.
        """
        from attendance.methods.utils import get_employee_attendance_summary

        summaries = get_employee_attendance_summary([employee], start, end)
        summary = summaries.get(employee.pk)
        if not summary:
            raise CommandError(
                f"No attendance summary returned for {employee} ({start}..{end})."
            )

        total_days = (end - start).days + 1
        paid_days = summary["paid_days"]
        unpaid_days = summary["unpaid_days"]
        if abs((paid_days + unpaid_days) - total_days) > 0.01:
            raise CommandError(
                f"{employee}: paid_days({paid_days}) + unpaid_days({unpaid_days}) "
                f"= {paid_days + unpaid_days}, not {total_days} (the period's own "
                f"calendar days). Raw summary: {summary}"
            )
        return summary

    # -- the payroll run itself --------------------------------------------------

    def _run_payroll_batch(self, employees, start, end, company):
        """
        The real "Run Payroll" pipeline (payroll/methods/batch_run.py) --
        the same create_batch()/generate_slice() pair the UI wizard calls --
        rather than writing Payslip rows directly. A payslip with no
        PayrollBatch behind it is invisible on the Payroll Runs page (it
        reads PayrollBatch.objects, not Payslip), which is exactly the gap
        this closes: generate_slice() re-reads the AttendanceSummaryOverride
        rows _payroll_month_for() already wrote, so the same by-construction
        reconciliation applies here with no extra plumbing.
        """
        from payroll.methods import batch_run
        from payroll.models.payroll_batch import PayrollBatch

        batch = batch_run.create_batch(
            name=f"{company.company} — {start.strftime('%b %Y')}",
            start_date=start,
            end_date=end,
            employees=employees,
        )
        # editable=False only blocks the form; stamp_company_on_create has no
        # thread-local company to read outside a request, so this is set
        # explicitly rather than left to default to None.
        PayrollBatch.objects.filter(pk=batch.pk).update(company_id=company)

        while batch_run.generate_slice(batch, size=len(employees)):
            pass
        batch.refresh_from_db()

        failed = list(batch.lines.filter(status="failed"))
        if failed:
            details = "; ".join(
                f"{line.employee_id}: {line.message}" for line in failed
            )
            raise CommandError(f"Payroll batch {batch} had failures: {details}")

        # Draft is what generate_slice() always writes; DRAFT -> APPROVED ->
        # PAID is the only path the model's state machine allows to PAID, so
        # both steps are taken rather than assigned directly.
        batch.payslips.update(status="paid")
        batch.status = PayrollBatch.APPROVED
        batch.save(update_fields=["status"])
        batch.status = PayrollBatch.PAID
        batch.save(update_fields=["status"])
        batch.refresh_totals()

        self.stdout.write(
            f"  Payroll run: {batch.batch_name} -- {batch.generated_count} payslips, "
            f"net {batch.total_net:,.2f}"
        )
        return batch

    # -- loans, advances, pending requests ---------------------------------------

    def _loans_for(self, employees, today):
        """
        A couple of loans and a couple of salary advances per branch, same
        shape as create_payroll_fixtures.py's own `_write_loans_and_claims`.
        Dated after today: these payslips are already generated and paid
        (a PayrollBatch, once PAID, cannot be changed), so an
        installment_start_date in the past would be a schedule that implies
        a deduction nothing will ever actually take.
        """
        from payroll.models.models import LoanAccount

        for offset, employee in enumerate(employees[:4]):
            is_loan = offset % 2 == 1
            LoanAccount.objects.create(
                employee_id=employee,
                title="Staff loan" if is_loan else "Salary advance",
                type="loan" if is_loan else "advanced_salary",
                loan_amount=60000 if is_loan else 20000,
                provided_date=today - datetime.timedelta(days=10),
                installments=12 if is_loan else 4,
                installment_amount=5000,
                installment_start_date=today + datetime.timedelta(days=20),
                description="Approved by HR.",
            )

    def _pending_leave_for(self, employees, today, unpaid_type):
        """Two not-yet-approved leave requests per branch, so the
        dashboard's Pending Approvals widget has something to show."""
        from leave.models import LeaveRequest

        for employee in employees[8:10]:
            start = today + datetime.timedelta(days=5)
            LeaveRequest.objects.create(
                employee_id=employee,
                leave_type_id=unpaid_type,
                start_date=start,
                end_date=start,
                status="requested",
                start_date_breakdown="full_day",
                end_date_breakdown="full_day",
                description="Branch demo — awaiting approval",
            )

    def _ongoing_leave_for(self, employees, today, paid_type, unpaid_type):
        """
        A couple of employees on approved leave spanning today specifically
        -- none of the other leave windows above are guaranteed to cover
        today itself, so without this the dashboard's On Leave tile can read
        zero purely by coincidence of which day the command happens to run
        on. Any Attendance row already covering these dates is cleared
        first, the same way the "current month" skip-day above does, so a
        present row and an approved leave never both claim the same day.
        """
        from attendance.models import Attendance
        from leave.models import LeaveRequest

        start = today - datetime.timedelta(days=2)
        end = today + datetime.timedelta(days=2)
        for offset, employee in enumerate(employees[10:12]):
            Attendance.objects.filter(
                employee_id=employee, attendance_date__range=(start, end)
            ).delete()
            leave_type = paid_type if offset % 2 == 0 else unpaid_type
            LeaveRequest.objects.create(
                employee_id=employee,
                leave_type_id=leave_type,
                start_date=start,
                end_date=end,
                status="approved",
                start_date_breakdown="full_day",
                end_date_breakdown="full_day",
                description="Branch demo — currently on leave",
            )

    def _today_attendance_for(self, employees, today, shift):
        """
        A realistic chunk of today's attendance, independent of the Mon-Fri
        weekday filter everything else here uses. "Today" is whatever day
        this command happens to be run on -- it can land on a Saturday or
        Sunday as easily as a weekday -- and the dashboard's Checked In
        Today tile reads Attendance rows for that exact date. Without this,
        running the command on a weekend leaves that tile at zero by pure
        chance of the calendar, not because anything about the dataset is
        wrong. Anyone on approved leave covering today is skipped, so a
        present row and an approved leave never both claim the same day.
        """
        from attendance.models import Attendance
        from leave.models import LeaveRequest

        on_leave_today = set(
            LeaveRequest.objects.filter(
                employee_id__in=employees,
                status="approved",
                start_date__lte=today,
                end_date__gte=today,
            ).values_list("employee_id", flat=True)
        )
        Attendance.objects.filter(
            employee_id__in=employees, attendance_date=today
        ).delete()
        # On a week off only a handful come in (6 per branch), not everyone.
        weekend_limit = WEEKEND_CHECKINS_PER_COMPANY if today.weekday() >= 5 else None
        checked_in = 0
        for employee in employees:
            if employee.pk in on_leave_today:
                continue
            if weekend_limit is not None and checked_in >= weekend_limit:
                break
            checked_in += 1
            Attendance.objects.create(
                employee_id=employee,
                attendance_date=today,
                shift_id=shift,
                attendance_clock_in=datetime.time(9, 0),
                attendance_clock_out=datetime.time(18, 0),
                attendance_worked_hour="09:00",
                minimum_hour="08:00",
                attendance_validated=True,
            )

    def _pending_attendance_request_for(self, employees, older_month_start):
        """One attendance-correction request left pending, for the
        Requests/Pending Approvals screens."""
        from attendance.models import Attendance

        row = (
            Attendance.objects.filter(
                employee_id=employees[6], attendance_date__gte=older_month_start
            )
            .order_by("attendance_date")
            .first()
        )
        if row is not None:
            Attendance.objects.filter(pk=row.pk).update(
                is_validate_request=True,
                is_validate_request_approved=False,
            )

    def _reimbursements_for(self, employees, today):
        """
        A couple of approved reimbursement claims per branch, same shape as
        create_payroll_fixtures.py's own claim half of
        `_write_loans_and_claims`. Reimbursement.save() refuses a claim with
        no attachment, so one is attached before the real save() rather than
        passed as a create() kwarg.
        """
        from django.core.files.base import ContentFile

        from payroll.models.models import Reimbursement

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
                "receipt.txt", ContentFile(b"Receipt on file."), save=False
            )
            claim.save()

    def _policy_and_discipline(self, company, employees):
        """One published policy and one minor disciplinary action per
        branch, so those screens aren't empty either."""
        from employee.models import Actiontype, DisciplinaryAction, Policy

        policy = Policy.objects.create(
            title="Code of Conduct",
            body="Standard company conduct policy for all employees.",
            is_visible_to_all=True,
        )
        policy.company_id.add(company)

        action_type, _created = Actiontype.objects.get_or_create(
            title="Verbal Warning",
            defaults={"action_type": "warning", "block_option": False},
        )
        disciplinary = DisciplinaryAction.objects.create(
            action=action_type,
            description="Late arrival, first occurrence.",
            unit_in="days",
            days=0,
            start_date=datetime.date.today(),
        )
        disciplinary.employee_id.add(employees[9])


@contextlib.contextmanager
def _as_request():
    """
    Stand in a request, for model code that expects to be inside one.

    Same helper as create_payroll_fixtures.py's own -- several payroll models
    read the current user from thread-locals (HorillaModel.save() assigns it
    to created_by, and some signals notify request.user), and in a command
    there is nobody. A superuser is the right stand-in: a fixture is not
    being restricted by anybody's permissions.
    """
    from django.contrib.auth import get_user_model

    from horilla.horilla_middlewares import _thread_locals

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
