"""
Management command: create_branch_demo_fixtures
--------------------------------------------------
Replaces all data with a two-company ("two branches") demo dataset: 60
employees (30 per company), real day-by-day Attendance running up to today,
real LeaveRequest rows spanning the month before last through 30 days into
the future, and Payslips for the one most-recently-closed calendar month
only. Helpdesk tickets are spread over the last six months and routed through
each branch's department / job position hierarchy. Each branch also gets its
own asset inventory with allocations, requests and service requests, and
its own recruitments with stage pipelines, candidates and interviews, and
its own performance data: objectives with key results, employee objectives,
360 feedback, meetings and bonus points.

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
import random

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
# Employees per branch left out of the payroll run, so the dashboard has
# "still to run" people to show rather than everyone already paid.
UNRUN_PER_COMPANY = 3
# Days from today that a few contracts end, for the Contracts Ending panel.
CONTRACT_END_OFFSETS = {3: 12, 11: 27, 19: 48}
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

# Extra shifts per branch (name, start, end) beside the 09:00-18:00 default,
# and the work types employees are spread across -- so the attendance
# dashboard's shift / work-type breakdowns have more than one bucket.
EXTRA_SHIFTS = [
    ("Morning Shift", datetime.time(7, 0), datetime.time(16, 0)),
    ("Evening Shift", datetime.time(12, 0), datetime.time(21, 0)),
]
DEFAULT_SHIFT_HOURS = (datetime.time(9, 0), datetime.time(18, 0))
# Chart variety: share of attendance days dropped (i.e. absences) per shift
# slot, and per-department tweaks to lateness and worked hours, so the
# attendance dashboard's bars sit at clearly different levels.
SHIFT_ABSENCE_PERCENT = [5, 5, 18, 35]  # default, default, morning, evening
DEPARTMENT_LATE_EVERY = {
    "Engineering": 3,
    "Sales": 4,
    "Human Resources": 9,
    "Marketing": 6,
    "Finance": 14,
}
DEPARTMENT_EARLY_EVERY = {
    "Engineering": 12,
    "Sales": 4,
    "Human Resources": 6,
    "Marketing": 3,
    "Finance": 9,
}
# Minutes added to (or removed from) clock-out, so avg working hours differ.
DEPARTMENT_HOURS_OFFSET = {
    "Engineering": 70,
    "Sales": 25,
    "Human Resources": 0,
    "Marketing": -35,
    "Finance": -60,
}
WORK_TYPE_NAMES = ["Work From Office", "Work From Home", "Hybrid"]

FEMALE_FIRST_NAMES = {
    "Olivia",
    "Sophia",
    "Ava",
    "Isabella",
    "Mia",
    "Emma",
    "Charlotte",
    "Amelia",
    "Harper",
    "Evelyn",
    "Abigail",
    "Emily",
    "Elizabeth",
    "Sofia",
    "Victoria",
}

# Employee dashboard: request counts per branch.
DASHBOARD_PENDING_SHIFT_REQUESTS = 4
DASHBOARD_PENDING_WORK_TYPE_REQUESTS = 4
DASHBOARD_PENDING_SHIFT_ALLOCATIONS = 3
DASHBOARD_PENDING_DOCUMENT_REQUESTS = 5
DASHBOARD_REQUEST_REASONS = [
    "Commute timing has changed.",
    "Need a quieter setup for focused work.",
    "Temporary family commitment.",
    "Team coverage adjustment.",
]
DASHBOARD_DOCUMENT_TITLES = [
    "Address Proof",
    "Educational Certificate",
    "Previous Employment Letter",
    "Passport Copy",
    "Bank Account Details",
    "Medical Fitness Certificate",
]

# Hire vs Turnover chart: how many months back each hire joined / each exit
# falls. Joins stop short of the current month, which the Birthdays &
# Anniversaries widget reads as anniversaries (a hire this month would show as
# a "0 yr anniversary").
TURNOVER_HIRE_MONTHS_AGO = [5, 5, 4, 3, 3, 2, 1, 1]
TURNOVER_EXIT_MONTHS_AGO = [4, 3, 2, 2, 1, 0]

PROJECT_SPECS = [
    # (title, status, start offset, end offset, task status cycle)
    ("Website Revamp", "in_progress", -60, 30, ["completed", "in_progress", "to_do"]),
    (
        "Mobile App",
        "in_progress",
        -40,
        -5,
        ["completed", "in_progress", "in_progress", "to_do"],
    ),
    ("HR Portal Migration", "completed", -120, -20, ["completed"]),
    ("Q4 Marketing Campaign", "new", 5, 90, ["to_do"]),
    ("Data Warehouse", "on_hold", -75, 45, ["completed", "in_progress", "to_do"]),
]

PROJECT_TASK_TITLES = [
    "Requirements gathering",
    "UX wireframes",
    "Database schema",
    "API development",
    "Frontend build",
    "Integration testing",
    "Security review",
    "Performance tuning",
    "User acceptance testing",
    "Documentation",
    "Deployment plan",
    "Training session",
]

PROJECT_STAGES = [("In Progress", False), ("Review", False), ("Done", True)]

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

HELPDESK_TICKETS_PER_COMPANY = 48
HELPDESK_TAGS = [
    ("Urgent", "#ef4444"),
    ("Hardware", "#3b82f6"),
    ("Policy", "#a855f7"),
    ("Payroll", "#22c55e"),
    ("Facilities", "#f59e0b"),
]
HELPDESK_TYPES = [
    ("IT Support", "service_request", "ITS", "department", "Engineering"),
    ("Payroll Support", "service_request", "PAY", "department", "Finance"),
    ("HR Complaint", "complaint", "HRC", "job_position", "HR Manager"),
    ("Suggestion", "suggestion", "SUG", "department", "Marketing"),
    ("Meeting Request", "meeting_request", "MTG", "individual", "Sales"),
]
HELPDESK_TITLES = {
    "IT Support": [
        "VPN keeps disconnecting",
        "Laptop battery swelling",
        "Email not syncing on phone",
        "Request a second monitor",
        "Software licence renewal",
    ],
    "Payroll Support": [
        "Payslip shows wrong deductions",
        "Reimbursement not credited",
        "Tax declaration query",
        "Bonus slab clarification",
        "Loan instalment question",
    ],
    "HR Complaint": [
        "Unfair shift allocation",
        "Manager behaviour concern",
        "Leave balance mismatch",
        "Seating arrangement dispute",
        "Onboarding checklist incomplete",
    ],
    "Suggestion": [
        "Introduce flexible Fridays",
        "Healthier pantry snacks",
        "Quarterly town hall format",
        "Add more standing desks",
        "Internal referral campaign",
    ],
    "Meeting Request": [
        "Quarterly target review",
        "Client pipeline walkthrough",
        "Territory planning session",
        "Discount approval discussion",
        "Sales enablement sync",
    ],
}
# Month offsets from the current month, cycled by ticket index, so the 6-month
# trend chart gets real volume in every bucket.
HELPDESK_MONTH_BUCKETS = [-5, -4, -3, -3, -2, -2, -1, -1, -1, 0, 0, 0]
HELPDESK_OLD_STATUSES = [
    "resolved",
    "resolved",
    "resolved",
    "canceled",
    "resolved",
    "in_progress",
    "resolved",
    "on_hold",
]
HELPDESK_LAST_STATUSES = [
    "resolved",
    "in_progress",
    "resolved",
    "new",
    "on_hold",
    "resolved",
    "in_progress",
    "canceled",
]
HELPDESK_CURRENT_STATUSES = [
    "new",
    "in_progress",
    "new",
    "resolved",
    "on_hold",
    "new",
    "in_progress",
    "resolved",
]
HELPDESK_PRIORITIES = [
    "medium",
    "high",
    "low",
    "medium",
    "medium",
    "high",
    "low",
    "medium",
]
HELPDESK_OPEN_STATUSES = ("new", "in_progress", "on_hold")
HELPDESK_COMMENTS = [
    "Looking into this now.",
    "Escalated to the concerned team.",
    "Can you share more details or a screenshot?",
    "A fix has been applied, please confirm.",
    "Waiting on a response from the vendor.",
]
HELPDESK_FAQS = [
    (
        "Getting Started",
        [
            (
                "How do I raise a ticket?",
                "Open the Helpdesk, choose New Ticket, pick a type and describe the issue.",
            ),
            (
                "How are tickets routed?",
                "Each ticket type is forwarded to a department, job position or person.",
            ),
        ],
    ),
    (
        "IT & Access",
        [
            (
                "How do I reset my password?",
                "Use the Forgot Password link on the sign-in page or raise an IT Support ticket.",
            ),
            (
                "How do I request new hardware?",
                "Raise an IT Support ticket with the item and a short justification.",
            ),
        ],
    ),
    (
        "Payroll & Benefits",
        [
            (
                "When are payslips released?",
                "Payslips are published once the monthly payroll run is closed.",
            ),
            (
                "How do I claim a reimbursement?",
                "Submit it under Payroll, attach the receipt and wait for approval.",
            ),
        ],
    ),
]

ASSETS_PER_COMPANY = 56
ASSET_REQUESTS_PER_COMPANY = 30
ASSET_CATALOG = [
    (
        "Laptops",
        [
            ("Dell Latitude 5440", 82000),
            ("MacBook Air M3", 124000),
            ("Lenovo ThinkPad E14", 68000),
        ],
    ),
    ("Phones", [("iPhone 15", 79000), ("Samsung Galaxy S24", 74000)]),
    ("Headphones", [("Sony WH-1000XM5", 29000), ("Bose QuietComfort 45", 27000)]),
    ("Monitors", [("Dell U2723QE", 45000), ("LG UltraFine 27", 38000)]),
    ("Accessories", [("Logitech MX Master 3S", 9500), ("Laptop Backpack", 3200)]),
]
ASSET_MONTH_BUCKETS = [-5, -4, -3, -3, -2, -2, -1, -1, 0, 0, 0, 0]
ASSET_RETURN_STATUSES = ["Healthy", "Minor damage", "Healthy", "Major damage"]
ASSET_REQUEST_STATUSES = ["Requested", "Approved", "Rejected", "Approved", "Requested"]
ASSET_REQUEST_NOTES = [
    "Needed for a new project.",
    "Current device is slow.",
    "Replacement for a damaged unit.",
    "Required for client visits.",
]
ASSET_SERVICE_STATUSES = [
    "Requested",
    "In Progress",
    "Completed",
    "Rejected",
    "Requested",
]
ASSET_SERVICE_ISSUES = [
    "Keyboard keys are unresponsive.",
    "Battery drains within two hours.",
    "Screen flickers intermittently.",
    "Device overheats under load.",
    "Charging port is loose.",
]

RECRUITMENT_PLANS = [
    ("Software Engineer", 3, 2),
    ("Sales Representative", 2, 1),
    ("HR Business Partner", 1, 0),
    ("Marketing Specialist", 2, 2),
    ("Financial Analyst", 2, 1),
]
RECRUITMENT_EXTRA_STAGES = [
    ("Technical Test", "test", 2),
    ("Interview", "interview", 3),
    ("Hired", "hired", 4),
    ("Cancelled Candidates", "cancelled", 50),
]
RECRUITMENT_STAGE_PATTERN = [
    "applied",
    "applied",
    "applied",
    "initial",
    "initial",
    "test",
    "test",
    "interview",
    "interview",
    "interview",
    "hired",
    "cancelled",
    "applied",
    "initial",
    "hired",
    "cancelled",
]
RECRUITMENT_MONTH_BUCKETS = [0, 0, -1, 0, -1, -2, 0, -1, 0, -1, 0, -2, 0, -1, 0, -2]
RECRUITMENT_SOURCES = [
    "application",
    "software",
    "application",
    "other",
    "application",
    "software",
]
RECRUITMENT_REFERRAL_SOURCES = [
    "job_board",
    "company_career_site",
    "social_media",
    "employee_referral",
    "recruiter_headhunter",
    "search_engine",
    "college_university",
    "job_board",
]
CANDIDATE_FIRST_NAMES = [
    "Emma",
    "Liam",
    "Sofia",
    "Noah",
    "Olivia",
    "Ethan",
    "Mia",
    "Lucas",
    "Chloe",
    "Mason",
    "Grace",
    "Oliver",
    "Nora",
    "Elijah",
    "Hannah",
    "James",
    "Lily",
    "Henry",
    "Leah",
    "Daniel",
]
CANDIDATE_LAST_NAMES = [
    "Walker",
    "Brooks",
    "Fisher",
    "Hayes",
    "Morgan",
    "Bennett",
    "Carter",
    "Dawson",
    "Ellis",
    "Foster",
    "Gray",
    "Harper",
    "Jensen",
    "Keller",
    "Lawson",
]
CANDIDATE_CITIES = ["Austin", "Denver", "Seattle", "Boston", "Chicago", "Portland"]
TALENT_POOLS = [
    (
        "Engineering Bench",
        "Strong engineering profiles to consider for future openings.",
    ),
    (
        "Sales and Marketing",
        "Promising sales and marketing candidates kept for later roles.",
    ),
    (
        "Future Hires",
        "Good fits we could not place yet but want to stay in touch with.",
    ),
]
TALENT_POOL_REASONS = [
    "Strong profile, no open position at the moment.",
    "Good interview feedback, revisit next quarter.",
    "Great skills, salary expectation slightly above budget.",
    "Interested in a future opening on the team.",
]
TALENT_POOL_MEMBERS = 6

# One shared 5-stage onboarding pipeline (+ one task per stage) is built per
# recruitment that has hired candidates; "Initial" is skipped here since the
# Recruitment post_save signal already creates it.
ONBOARDING_STAGE_TITLES = [
    "Initial",
    "Introduction & Orientation",
    "Technical Setup",
    "Training & Knowledge Transfer",
    "First Task Assignment",
]
ONBOARDING_STAGE_TASKS = {
    "Initial": "Complete Employment Paperwork",
    "Introduction & Orientation": "Attend Orientation Session",
    "Technical Setup": "Set Up Laptop and Accounts",
    "Training & Knowledge Transfer": "Complete Onboarding Training Modules",
    "First Task Assignment": "Submit First Assignment",
}
# (stage the candidate currently sits at, that stage's own task status,
# whether the onboarding portal has been sent and, if so, whether it has
# been used) -- cycled across each recruitment's hired candidates so every
# company gets a realistic mix: a couple finished, a couple mid-pipeline,
# one with a stuck task, one brand new hire nothing has been sent to yet.
ONBOARDING_PROGRESS_PLAN = [
    ("First Task Assignment", "done", True),
    ("First Task Assignment", "done", True),
    ("Technical Setup", "ongoing", False),
    ("Technical Setup", "stuck", False),
    ("Introduction & Orientation", "ongoing", False),
    ("Initial", "todo", None),
]

PERFORMANCE_OBJECTIVES = [
    (
        "Improve customer satisfaction",
        ["Raise CSAT score", "Cut ticket response time", "Close escalations"],
    ),
    (
        "Grow quarterly revenue",
        ["New accounts signed", "Upsell conversions", "Pipeline coverage"],
    ),
    (
        "Strengthen engineering quality",
        ["Reduce open bugs", "Raise test coverage", "Shorten release cycle"],
    ),
    ("Upskill the team", ["Complete certifications", "Run knowledge-sharing talks"]),
    (
        "Streamline internal operations",
        ["Automate manual reports", "Reduce onboarding time"],
    ),
    ("Improve employee engagement", ["Run pulse surveys", "Lift eNPS score"]),
    (
        "Expand into new markets",
        ["Launch regional pilots", "Sign channel partners", "Localise product pages"],
    ),
    (
        "Reduce operating costs",
        ["Renegotiate vendor contracts", "Cut cloud spend", "Consolidate tooling"],
    ),
    (
        "Accelerate product delivery",
        ["Ship roadmap milestones", "Lower cycle time", "Cut review backlog"],
    ),
    (
        "Strengthen security posture",
        ["Close audit findings", "Complete access reviews", "Run phishing drills"],
    ),
    (
        "Improve talent acquisition",
        ["Fill open roles", "Shorten time to hire", "Raise offer acceptance"],
    ),
    (
        "Boost customer retention",
        ["Lower churn rate", "Launch loyalty program", "Run renewal outreach"],
    ),
    (
        "Enhance data and analytics",
        ["Build KPI dashboards", "Improve data quality", "Train teams on reporting"],
    ),
]
PERFORMANCE_OBJECTIVES_PER_COMPANY = [8, 5]
PERFORMANCE_STATUSES = [
    "On Track",
    "On Track",
    "Closed",
    "Behind",
    "On Track",
    "At Risk",
    "Not Started",
    "Closed",
]
PERFORMANCE_FEEDBACK_STATUSES = [
    "Not Started",
    "On Track",
    "On Track",
    "Behind",
    "At Risk",
    "Closed",
]
PERFORMANCE_PROGRESS_RANGE = {
    "Not Started": (0, 0),
    "On Track": (45, 90),
    "Behind": (20, 50),
    "At Risk": (5, 30),
    "Closed": (100, 100),
}
PERFORMANCE_FEEDBACK_CYCLES = [
    "Quarterly Review",
    "Mid-year Check-in",
    "Peer Feedback Round",
]
PERFORMANCE_QUESTIONS = [
    ("How would you rate this person's overall performance?", "2"),
    ("What are this person's biggest strengths?", "1"),
    ("Does this person collaborate well with the team?", "3"),
]
PERFORMANCE_MEETING_TITLES = [
    "Monthly one-on-one",
    "Goal alignment sync",
    "Performance check-in",
    "Quarterly review prep",
]
# Days from today, so the dashboard's next-14-days window has meetings in it.
PERFORMANCE_MEETING_DAY_OFFSETS = [-12, 1, 3, 6, 9, 12]
PERFORMANCE_EMPLOYEES_PER_COMPANY = 16
PERFORMANCE_MANAGERS_PER_OBJECTIVE = 2
PERFORMANCE_FEEDBACKS_PER_COMPANY = 6


def _add_months(d, delta):
    m = d.month - 1 + delta
    y = d.year + m // 12
    m = m % 12 + 1
    return datetime.date(y, m, 1)


def _create_leave(**fields):
    """
    LeaveRequest.objects.create that never lets one employee hold two leaves
    over the same day. The ORM bypasses the form's overlap validation, so the
    generator has to enforce it: a leave that would overlap an existing one
    (any status but rejected/cancelled) is skipped.
    """
    from leave.models import LeaveRequest

    clash = LeaveRequest.objects.filter(
        employee_id=fields["employee_id"],
        start_date__lte=fields["end_date"],
        end_date__gte=fields["start_date"],
    ).exclude(status__in=["rejected", "cancelled"])
    if clash.exists():
        return None
    return LeaveRequest.objects.create(**fields)


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
        tickets_created = open_tickets = 0
        assets_created = asset_requests = service_requests = 0
        projects_created = 0
        recruitments_created = candidates_created = hires_created = (
            interviews_created
        ) = 0
        pools_created = pool_members_created = 0
        onboarded_created = portals_sent = portals_incomplete = 0
        performance_totals = [0] * 6
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
            self._shifts_worktypes_punctuality_for(company, employees, shift)
            self._pending_leave_for(employees, today, unpaid_type)
            with _as_request():
                self._employee_dashboard_for(company, employees, shift, today)
                self._loans_for(employees, today)
                self._reimbursements_for(employees, today)
                self._policy_and_discipline(company, employees)
                tickets, open_count = self._helpdesk_for(company, employees, today)
                tickets_created += tickets
                open_tickets += open_count
                assets, requests, services = self._assets_for(company, employees, today)
                projects_created += self._projects_for(company, employees, today)
                assets_created += assets
                asset_requests += requests
                service_requests += services
                recs, cands, hires, interviews, pools, pool_members = (
                    self._recruitment_for(company, employees, today)
                )
                recruitments_created += recs
                candidates_created += cands
                hires_created += hires
                interviews_created += interviews
                pools_created += pools
                pool_members_created += pool_members
                onboarded, sent, incomplete = self._onboarding_for(
                    company, employees, today
                )
                onboarded_created += onboarded
                portals_sent += sent
                portals_incomplete += incomplete
                performance = self._performance_for(
                    company, employees, today, COMPANIES.index(company_spec)
                )
                performance_totals = [
                    total + added
                    for total, added in zip(performance_totals, performance)
                ]

            batch = self._run_payroll_batch(
                employees[:-UNRUN_PER_COMPANY],
                last_month_start,
                last_month_end,
                company,
            )
            payslips_created += batch.generated_count
            runs_created += 1

            self._turnover_for(company, employees, today)

        self.stdout.write(self.style.SUCCESS("\nDone."))
        self.stdout.write(
            self.style.SUCCESS(
                f"Companies:   {len(COMPANIES)} companies, {total_employees} employees"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Payroll:     {runs_created} runs, {payslips_created} payslips for "
                f"{last_month_start:%b %Y} -- every one verified paid_days + "
                f"unpaid_days == that month's calendar days"
            )
        )
        self.stdout.write(self.style.SUCCESS(f"Attendance:  runs through {today}"))
        self.stdout.write(
            self.style.SUCCESS(f"Leave:       runs through {leave_horizon_end}")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Helpdesk:    {tickets_created} tickets ({open_tickets} open)"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Assets:      {assets_created} assets, {asset_requests} requests, "
                f"{service_requests} service requests. Projects: {projects_created}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Recruitment: {recruitments_created} recruitments, "
                f"{candidates_created} candidates ({hires_created} hired), "
                f"{interviews_created} interviews"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Talent pool: {pools_created} pools ({pool_members_created} members)"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Onboarding:  {onboarded_created} candidates in the pipeline, "
                f"{portals_sent} portals sent ({portals_incomplete} incomplete)"
            )
        )
        (
            objectives_total,
            emp_objectives_total,
            krs_total,
            feedbacks_total,
            meetings_total,
            bonus_total,
        ) = performance_totals
        self.stdout.write(
            self.style.SUCCESS(
                f"Performance: {objectives_total} objectives, {emp_objectives_total} employee "
                f"objectives, {krs_total} key results, {feedbacks_total} feedbacks, "
                f"{meetings_total} meetings, {bonus_total} bonus awards"
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

        # Same weekday schedule as the default shift, with its own hours.
        self._shift_hours = {shift.pk: DEFAULT_SHIFT_HOURS}
        self._extra_shifts = {}
        for shift_name, start, end in EXTRA_SHIFTS:
            extra = EmployeeShift.objects.create(employee_shift=f"{name} {shift_name}")
            extra.company_id.add(company)
            for day_name in WEEKDAY_NAMES:
                day, _created = EmployeeShiftDay.objects.get_or_create(day=day_name)
                EmployeeShiftSchedule.objects.create(
                    day=day,
                    shift_id=extra,
                    start_time=start,
                    end_time=end,
                )
            self._shift_hours[extra.pk] = (start, end)
            self._extra_shifts[shift_name] = extra
        EmployeeShiftSchedule.objects.filter(shift_id=shift).update(
            start_time=DEFAULT_SHIFT_HOURS[0],
            end_time=DEFAULT_SHIFT_HOURS[1],
        )

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
            Employee.objects.filter(pk=employee.pk).update(
                gender="female" if first in FEMALE_FIRST_NAMES else "male"
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
            if i in CONTRACT_END_OFFSETS:
                Contract.objects.filter(pk=contract.pk).update(
                    contract_end_date=today
                    + datetime.timedelta(days=CONTRACT_END_OFFSETS[i])
                )
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
            _create_leave(
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
            _create_leave(
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
                _create_leave(
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
            _create_leave(
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
            _create_leave(
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
            LeaveRequest.objects.filter(
                employee_id=employee, start_date__lte=end, end_date__gte=start
            ).delete()
            _create_leave(
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
        from attendance.models import Attendance, AttendanceLateComeEarlyOut
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
            # A few arrive late / leave early so the dashboard's Attendance Daily
            # Overview has Late Arrival and Early Departure values, not just On Time.
            # (The clock-in views write the AttendanceLateComeEarlyOut rows by hand,
            # so they are created here the same way.)
            kind = (
                "late_come"
                if checked_in % 5 == 3
                else "early_out" if checked_in % 7 == 5 else None
            )
            clock_in = (
                datetime.time(9, 45) if kind == "late_come" else datetime.time(9, 0)
            )
            clock_out = (
                datetime.time(16, 30) if kind == "early_out" else datetime.time(18, 0)
            )
            worked = {"late_come": "08:15", "early_out": "07:30"}.get(kind, "09:00")
            attendance = Attendance.objects.create(
                employee_id=employee,
                attendance_date=today,
                shift_id=shift,
                attendance_clock_in=clock_in,
                attendance_clock_out=clock_out,
                attendance_worked_hour=worked,
                minimum_hour="08:00",
                attendance_validated=True,
            )

    def _shifts_worktypes_punctuality_for(self, company, employees, default_shift):
        """
        Spread employees over three shifts and three work types, then rewrite
        every existing Attendance row to match: shift_id/work_type_id follow
        the employee, clock-in/out follow that shift's hours, and a
        deterministic subset of days is made a late arrival (clock-in 15-70
        minutes after shift start) or an early departure (clock-out 30-90
        minutes before shift end), each with its AttendanceLateComeEarlyOut
        row -- the table the attendance dashboard's Late Arrival / Early
        Out cards and per-department chart count. Every 4th employee is
        deliberately chronically late so departments differ in the chart.
        Rows are written with .update() so no clock-in/out side effects fire.
        """
        from attendance.models import Attendance, AttendanceLateComeEarlyOut
        from base.models import WorkType
        from employee.models import EmployeeWorkInformation

        work_types = []
        for wt_name in WORK_TYPE_NAMES:
            work_type = WorkType.objects.create(
                work_type=f"{wt_name} ({company.company})"
            )
            work_type.company_id.add(company)
            work_types.append(work_type)

        shifts = [default_shift, default_shift, *self._extra_shifts.values()]
        departments = {
            w.employee_id_id: w.department_id.department if w.department_id else None
            for w in EmployeeWorkInformation.objects.filter(
                employee_id__in=employees
            ).select_related("department_id")
        }
        late_total = early_total = absent_total = 0
        for index, employee in enumerate(employees):
            shift_slot = index % len(shifts)
            shift = shifts[shift_slot]
            department = departments.get(employee.pk)
            work_type = work_types[index % len(work_types)]
            EmployeeWorkInformation.objects.filter(employee_id=employee).update(
                shift_id=shift,
                work_type_id=work_type,
            )
            start, end = self._shift_hours[shift.pk]
            late_every = DEPARTMENT_LATE_EVERY.get(department, 7)
            early_every = DEPARTMENT_EARLY_EVERY.get(department, 9)
            if index % 4 == 0:  # chronically late regardless of department
                late_every = min(late_every, 3)
            hours_offset = DEPARTMENT_HOURS_OFFSET.get(department, 0)
            # Shift-level absence rate, nudged per employee so it isn't flat.
            absence_percent = SHIFT_ABSENCE_PERCENT[shift_slot] + (index % 4) * 3

            for attendance in Attendance.objects.filter(employee_id=employee):
                day = attendance.attendance_date
                # Today is left alone so the Checked In Today tile is unchanged.
                if day != datetime.date.today() and (
                    (index * 31 + day.toordinal() * 17) % 100 < absence_percent
                ):
                    attendance.delete()
                    absent_total += 1
                    continue
                seed = index * 3 + day.toordinal()
                clock_in = datetime.datetime.combine(day, start)
                clock_out = datetime.datetime.combine(day, end) + datetime.timedelta(
                    minutes=hours_offset
                )
                is_late = seed % late_every == 0
                is_early = (seed + 2) % early_every == 0 and not is_late
                if is_late:
                    clock_in += datetime.timedelta(minutes=15 + (seed * 11) % 56)
                if is_early:
                    clock_out -= datetime.timedelta(minutes=30 + (seed * 7) % 61)
                # Today may still be mid-shift; don't punch out in the future.
                now = datetime.datetime.now()
                if clock_out > now and day == now.date():
                    clock_out = max(clock_in, now.replace(second=0, microsecond=0))

                worked = int((clock_out - clock_in).total_seconds())
                Attendance.objects.filter(pk=attendance.pk).update(
                    shift_id=shift,
                    work_type_id=work_type,
                    attendance_clock_in=clock_in.time(),
                    attendance_clock_out=clock_out.time(),
                    attendance_worked_hour=f"{worked // 3600:02d}:{worked % 3600 // 60:02d}",
                    at_work_second=worked,
                )
                for flag, kind in ((is_late, "late_come"), (is_early, "early_out")):
                    if flag:
                        # Plain save(), not create()/get_or_create(): the
                        # model's save() saves twice (to fill employee_id),
                        # and create()'s force_insert would make the second
                        # save a duplicate INSERT on the same id.
                        AttendanceLateComeEarlyOut(
                            attendance_id=attendance,
                            type=kind,
                        ).save()
                late_total += is_late
                early_total += is_early

        self.stdout.write(
            f"  Shifts/work types assigned; {late_total} late arrivals, "
            f"{early_total} early departures, {absent_total} absences"
        )

    # -- employee dashboard ------------------------------------------------------

    def _employee_dashboard_for(self, company, employees, default_shift, today):
        """
        Data for the Employee dashboard (employee/dashboard.py), dated inside
        the current month because that is the period the dashboard opens on:

        * New joiners -- the employees left out of the payroll run (the last
          UNRUN_PER_COMPANY) get a date_joining in this month. Employees in
          the payroll run keep their old joining date, so payslips are
          unaffected.
        * Shift requests, shift allocations, work type requests and document
          requests (the four KPI cards): mostly pending, plus a few approved /
          canceled / rejected so each count differs from the list total.

        Needs the branch's extra shifts and work types, so it must run after
        _shifts_worktypes_punctuality_for.
        """
        from django.utils import timezone

        from base.models import ShiftRequest, WorkType, WorkTypeRequest
        from employee.models import EmployeeWorkInformation
        from horilla_documents.models import Document

        month_start = today.replace(day=1)

        def stamp(model, obj, day):
            # created_at is auto-set on save and is what the KPI cards filter on.
            model._base_manager.filter(pk=obj.pk).update(
                created_at=timezone.make_aware(
                    datetime.datetime.combine(day, datetime.time(11, 0))
                )
            )

        def month_day(i):
            return month_start + datetime.timedelta(days=(i * 2) % today.day)

        def reason(i):
            return DASHBOARD_REQUEST_REASONS[i % len(DASHBOARD_REQUEST_REASONS)]

        joiners = employees[-UNRUN_PER_COMPANY:]
        for i, employee in enumerate(joiners):
            EmployeeWorkInformation.objects.filter(employee_id=employee).update(
                date_joining=month_day(i + 1)
            )

        shifts = [default_shift, *self._extra_shifts.values()]
        work_types = list(WorkType.objects.filter(company_id=company).order_by("pk"))
        works = {
            w.employee_id_id: w
            for w in EmployeeWorkInformation.objects.filter(employee_id__in=employees)
        }

        def other_shift(employee):
            current = works[employee.pk].shift_id
            return next((s for s in shifts if s != current), shifts[0])

        def other_work_type(employee):
            current = works[employee.pk].work_type_id
            return next((w for w in work_types if w != current), work_types[0])

        requesters = employees[14:]

        shift_states = [{}] * DASHBOARD_PENDING_SHIFT_REQUESTS + [
            {"approved": True},
            {"canceled": True},
        ]
        for i, state in enumerate(shift_states):
            employee = requesters[i % len(requesters)]
            request = ShiftRequest.objects.create(
                employee_id=employee,
                shift_id=other_shift(employee),
                previous_shift_id=works[employee.pk].shift_id,
                requested_date=month_day(i) + datetime.timedelta(days=3),
                requested_till=month_day(i) + datetime.timedelta(days=30),
                description=reason(i),
                **state,
            )
            stamp(ShiftRequest, request, month_day(i))

        # Allocations are ShiftRequests with reallocate_to set.
        allocation_states = [{}] * DASHBOARD_PENDING_SHIFT_ALLOCATIONS + [
            {"reallocate_approved": True}
        ]
        for i, state in enumerate(allocation_states):
            employee = requesters[(i + 6) % len(requesters)]
            request = ShiftRequest.objects.create(
                employee_id=employee,
                reallocate_to=requesters[(i + 7) % len(requesters)],
                shift_id=other_shift(employee),
                previous_shift_id=works[employee.pk].shift_id,
                requested_date=month_day(i + 2) + datetime.timedelta(days=2),
                requested_till=month_day(i + 2) + datetime.timedelta(days=14),
                description=reason(i + 1),
                **state,
            )
            stamp(ShiftRequest, request, month_day(i + 2))

        work_type_states = [{}] * DASHBOARD_PENDING_WORK_TYPE_REQUESTS + [
            {"approved": True},
            {"canceled": True},
        ]
        for i, state in enumerate(work_type_states):
            employee = requesters[(i + 3) % len(requesters)]
            request = WorkTypeRequest.objects.create(
                employee_id=employee,
                work_type_id=other_work_type(employee),
                previous_work_type_id=works[employee.pk].work_type_id,
                requested_date=month_day(i + 1) + datetime.timedelta(days=2),
                requested_till=month_day(i + 1) + datetime.timedelta(days=20),
                description=reason(i + 2),
                **state,
            )
            stamp(WorkTypeRequest, request, month_day(i + 1))

        document_statuses = ["requested"] * DASHBOARD_PENDING_DOCUMENT_REQUESTS + [
            "approved",
            "rejected",
        ]
        for i, status in enumerate(document_statuses):
            document = Document.objects.create(
                title=DASHBOARD_DOCUMENT_TITLES[i % len(DASHBOARD_DOCUMENT_TITLES)],
                employee_id=requesters[(i + 5) % len(requesters)],
                status=status,
                reject_reason="Image is not legible." if status == "rejected" else None,
            )
            stamp(Document, document, month_day(i))

        self.stdout.write(
            f"  Employee dashboard: {len(joiners)} new joiners, "
            f"{len(shift_states)} shift requests, {len(allocation_states)} shift "
            f"allocations, {len(work_type_states)} work type requests, "
            f"{len(document_statuses)} documents"
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
        Approved reimbursement claims per branch, plus two pending, same shape as
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

        # Two still waiting for approval, so the Pending Approvals and
        # reimbursement screens have requests to act on.
        for offset, employee in enumerate(employees[12:14]):
            claim = Reimbursement(
                employee_id=employee,
                title="Client visit travel" if offset % 2 else "Team offsite meals",
                type="reimbursement",
                allowance_on=today - datetime.timedelta(days=12),
                amount=1800 if offset % 2 else 950,
                status="requested",
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

    # -- helpdesk ----------------------------------------------------------------

    def _helpdesk_for(self, company, employees, today):
        """Ticket types, tickets, comments, claims and FAQs laid over the branch's org chart."""
        from django.utils import timezone

        from base.models import Department, JobPosition, Tags
        from employee.models import EmployeeWorkInformation
        from helpdesk.models import (
            FAQ,
            ClaimRequest,
            Comment,
            DepartmentManager,
            FAQCategory,
            Ticket,
            TicketType,
        )

        works = {
            work.employee_id_id: work
            for work in EmployeeWorkInformation.objects.filter(
                employee_id__in=employees
            )
        }
        by_department = {}
        by_position = {}
        for employee in employees:
            work = works[employee.pk]
            by_department.setdefault(work.department_id_id, []).append(employee)
            by_position.setdefault(work.job_position_id_id, []).append(employee)

        departments = {
            d.department: d for d in Department.objects.filter(company_id=company)
        }
        positions = {
            p.job_position: p for p in JobPosition.objects.filter(company_id=company)
        }
        heads = {
            name: by_department[department.pk][0]
            for name, department in departments.items()
            if by_department.get(department.pk)
        }
        for name, head in heads.items():
            DepartmentManager.objects.create(
                manager=head, department=departments[name], company_id=company
            )

        tags = [
            Tags.objects.create(title=title, color=color, company_id=company)
            for title, color in HELPDESK_TAGS
        ]
        types = {
            title: TicketType.objects.create(
                title=title, type=kind, prefix=prefix, company_id=company
            )
            for title, kind, prefix, _routing, _target in HELPDESK_TYPES
        }

        routes = {}
        for title, _kind, _prefix, routing, target in HELPDESK_TYPES:
            if routing == "department":
                department = departments[target]
                routes[title] = (
                    routing,
                    department.pk,
                    by_department.get(department.pk, []),
                    department.pk,
                )
            elif routing == "job_position":
                position = positions[target]
                routes[title] = (
                    routing,
                    position.pk,
                    by_position.get(position.pk, []),
                    position.department_id_id,
                )
            else:
                person = heads[target]
                routes[title] = (routing, person.pk, [person], departments[target].pk)

        this_month_start = today.replace(day=1)
        next_month_start = _add_months(this_month_start, 1)
        open_count = 0
        for i in range(HELPDESK_TICKETS_PER_COMPANY):
            type_title = HELPDESK_TYPES[i % len(HELPDESK_TYPES)][0]
            title = HELPDESK_TITLES[type_title][(i // len(HELPDESK_TYPES)) % 5]
            routing, raised_on, pool, target_department = routes[type_title]

            bucket = HELPDESK_MONTH_BUCKETS[i % len(HELPDESK_MONTH_BUCKETS)]
            month_start = _add_months(this_month_start, bucket)
            if bucket == 0:
                created = month_start + datetime.timedelta(days=(i * 3) % today.day)
            else:
                created = month_start + datetime.timedelta(days=(i * 5) % 27)

            if bucket <= -2:
                statuses = HELPDESK_OLD_STATUSES
            elif bucket == -1:
                statuses = HELPDESK_LAST_STATUSES
            else:
                statuses = HELPDESK_CURRENT_STATUSES
            status = statuses[
                (i + (i // len(HELPDESK_MONTH_BUCKETS)) * 3) % len(statuses)
            ]

            resolved = None
            if status == "resolved":
                resolved = min(today, created + datetime.timedelta(days=1 + i % 6))

            if status == "canceled":
                deadline = None
            elif status == "resolved":
                deadline = created + datetime.timedelta(days=2 + i % 5)
            elif bucket <= -2:
                deadline = created + datetime.timedelta(days=10)
            elif (
                bucket == 0
                and status in HELPDESK_OPEN_STATUSES
                and i % 2 == 0
                and created < today
            ):
                # Past deadline, created this month -- these are what the
                # dashboard's Overdue Tickets list (current period) shows.
                deadline = created + datetime.timedelta(days=i % (today - created).days)
            elif bucket == -1 and i % 3 == 0:
                deadline = today - datetime.timedelta(days=1 + i % 9)
            elif i % 9 == 0:
                deadline = today
            elif i % 4 == 0:
                deadline = next_month_start + datetime.timedelta(days=i % 25)
            else:
                deadline = today + datetime.timedelta(days=2 + (i * 3) % 12)

            candidates = [
                e
                for e in employees
                if works[e.pk].department_id_id != target_department
            ]
            owner = candidates[(i * 7) % len(candidates)]
            if status in HELPDESK_OPEN_STATUSES and i % 6 == 1:
                assigned = []
            else:
                assigned = [e for e in pool[: 1 + i % 2] if e.pk != owner.pk]

            ticket = Ticket.objects.create(
                title=title,
                employee_id=owner,
                ticket_type=types[type_title],
                description=f"{title}. Raised from {works[owner.pk].department_id.department}.",
                priority=HELPDESK_PRIORITIES[i % len(HELPDESK_PRIORITIES)],
                assigning_type=routing,
                raised_on=str(raised_on),
                deadline=deadline,
                status=status,
                resolved_date=resolved,
            )
            Ticket.objects.filter(pk=ticket.pk).update(created_date=created)
            ticket.assigned_to.set(assigned)
            ticket.tags.set([tags[i % len(tags)]])
            if status in HELPDESK_OPEN_STATUSES:
                open_count += 1

            if status != "new":
                responder = assigned[0] if assigned else owner
                for k in range(1 + i % 2):
                    comment = Comment.objects.create(
                        ticket=ticket,
                        employee_id=responder if k else owner,
                        comment=HELPDESK_COMMENTS[(i + k) % len(HELPDESK_COMMENTS)],
                    )
                    day = min(created + datetime.timedelta(days=k), today)
                    Comment.objects.filter(pk=comment.pk).update(
                        date=timezone.make_aware(
                            datetime.datetime.combine(day, datetime.time(10 + k, 0))
                        )
                    )

            if status in ("new", "in_progress") and i % 5 == 2:
                claimers = [e for e in pool if e not in assigned and e.pk != owner.pk]
                if claimers:
                    ClaimRequest.objects.get_or_create(
                        ticket_id=ticket, employee_id=claimers[0]
                    )

        for category_title, entries in HELPDESK_FAQS:
            category = FAQCategory.objects.create(
                title=category_title, company_id=company
            )
            for question, answer in entries:
                FAQ.objects.create(
                    question=question,
                    answer=answer,
                    category=category,
                    company_id=company,
                )

        self.stdout.write(
            f"  Helpdesk: {len(types)} ticket types, {HELPDESK_TICKETS_PER_COMPANY} tickets "
            f"({open_count} open), {len(heads)} department managers"
        )
        return HELPDESK_TICKETS_PER_COMPANY, open_count

    # -- projects ----------------------------------------------------------------

    def _projects_for(self, company, employees, today):
        """Projects across every status with stages, tasks and timesheets for the branch."""
        from project.models import Project, ProjectStage, Task, TimeSheet

        weekdays = [
            d
            for d in (today - datetime.timedelta(days=n) for n in range(1, 40))
            if d.weekday() < 5
        ]
        tasks_created = timesheets_created = 0
        for p_index, (name, status, start_off, end_off, task_cycle) in enumerate(
            PROJECT_SPECS
        ):
            start = today + datetime.timedelta(days=start_off)
            end = today + datetime.timedelta(days=end_off)
            manager = employees[(p_index * 4) % len(employees)]
            project = Project.objects.create(
                title=f"{company.company} - {name}",
                status=status,
                start_date=start,
                end_date=end,
                description=f"{name} for {company.company}.",
                company_id=company,
            )
            project.managers.add(manager)

            # Project.save() already made the first "Todo" stage; add the rest.
            stages = {"to_do": ProjectStage.objects.get(project=project, title="Todo")}
            for title, is_end in PROJECT_STAGES:
                stages[title] = ProjectStage.objects.create(
                    project=project, title=title, is_end_stage=is_end
                )
            stage_for = {
                "to_do": stages["to_do"],
                "in_progress": stages["In Progress"],
                "completed": stages["Done"],
            }

            span = max((end - start).days, 1)
            for t_index in range(6):
                t_status = task_cycle[t_index % len(task_cycle)]
                t_start = start + datetime.timedelta(days=(span * t_index) // 8)
                t_end = min(end, t_start + datetime.timedelta(days=max(span // 4, 3)))
                members = [
                    employees[(p_index * 4 + t_index + k + 1) % len(employees)]
                    for k in range(3)
                ]
                task = Task.objects.create(
                    title=PROJECT_TASK_TITLES[
                        (p_index * 3 + t_index) % len(PROJECT_TASK_TITLES)
                    ],
                    project=project,
                    stage=stage_for[t_status],
                    status=t_status,
                    start_date=t_start,
                    end_date=t_end,
                    allocated_hours=f"{16 + 8 * (t_index % 4):02d}:00",
                    description=f"{PROJECT_TASK_TITLES[(p_index * 3 + t_index) % len(PROJECT_TASK_TITLES)]} for {name}.",
                    sequence=t_index,
                )
                task.task_managers.add(manager)
                task.task_members.set(members)
                tasks_created += 1

                if t_status == "to_do" or t_start > today:
                    continue
                for d_index, day in enumerate(weekdays[: 4 + t_index]):
                    if day < t_start:
                        continue
                    worker = members[d_index % len(members)]
                    TimeSheet.objects.create(
                        project_id=project,
                        task_id=task,
                        employee_id=worker,
                        date=day,
                        time_spent=f"{3 + (d_index + t_index) % 5:02d}:00",
                        status=(
                            "completed" if t_status == "completed" else "in_Progress"
                        ),
                        description=f"Worked on {task.title.lower()}.",
                    )
                    timesheets_created += 1

        self.stdout.write(
            f"  Projects: {len(PROJECT_SPECS)} projects, {tasks_created} tasks, "
            f"{timesheets_created} timesheets"
        )
        return len(PROJECT_SPECS)

    # -- turnover ----------------------------------------------------------------

    def _turnover_for(self, company, employees, today):
        """
        Hires and exits spread over the last few months, for the dashboard's
        Hire vs Turnover chart.

        Hires are read from each employee's joining date. Exits come from
        approved resignation letters: that source leaves the employee active, so
        payroll, attendance and everything else already loaded is untouched,
        where marking someone inactive would drop them from all of it. The
        letters are taken from employees other than the department heads and the
        ones given back-dated joining dates here.
        """
        from employee.models import EmployeeWorkInformation
        from offboarding.models import ResignationLetter

        hire_pool = employees[-len(TURNOVER_HIRE_MONTHS_AGO) :]
        for k, (employee, months_ago) in enumerate(
            zip(hire_pool, TURNOVER_HIRE_MONTHS_AGO)
        ):
            joined = _add_months(today.replace(day=1), -months_ago).replace(
                day=3 + k * 3
            )
            EmployeeWorkInformation.objects.filter(employee_id=employee).update(
                date_joining=joined
            )

        exit_pool = [employees[i] for i in (9, 12, 14, 16, 18, 20)]
        for k, (employee, months_ago) in enumerate(
            zip(exit_pool, TURNOVER_EXIT_MONTHS_AGO)
        ):
            leaves_on = _add_months(today.replace(day=1), -months_ago).replace(
                day=8 + k * 3
            )
            ResignationLetter.objects.create(
                employee_id=employee,
                title="Resignation",
                description="Moving on to a new opportunity.",
                planned_to_leave_on=leaves_on,
                status="approved",
            )

        self.stdout.write(
            f"  Turnover: {len(hire_pool)} hires, {len(exit_pool)} approved exits "
            f"over the last {max(TURNOVER_HIRE_MONTHS_AGO) + 1} months"
        )

    # -- assets ------------------------------------------------------------------

    def _assets_for(self, company, employees, today):
        """Branch-scoped asset categories, assets, allocations, requests and service requests."""
        from asset.models import (
            Asset,
            AssetAssignment,
            AssetCategory,
            AssetItem,
            AssetRequest,
            AssetServiceRequest,
        )

        categories = {}
        for name, _entries in ASSET_CATALOG:
            category = AssetCategory.objects.create(
                asset_category_name=f"{name} ({company.company})",
                asset_category_description=f"{name} issued to {company.company} employees.",
            )
            category.company_id.set([company])
            categories[name] = category

        flat = [
            (cat, item, cost)
            for cat, entries in ASSET_CATALOG
            for item, cost in entries
        ]
        item_status = {
            "In use": "In use",
            "Available": "Available",
            "Not-Available": "Damaged",
        }
        this_month_start = today.replace(day=1)
        manager = employees[0]
        open_assignments = []
        in_use = returned = 0
        for i in range(ASSETS_PER_COMPANY):
            cat, name, cost = flat[i % len(flat)]
            bucket = ASSET_MONTH_BUCKETS[i % len(ASSET_MONTH_BUCKETS)]
            month_start = _add_months(this_month_start, bucket)
            if bucket == 0:
                purchased = month_start + datetime.timedelta(days=(i * 3) % today.day)
            else:
                purchased = month_start + datetime.timedelta(days=(i * 5) % 27)

            if i % 6 == 0:
                expiry = today + datetime.timedelta(days=3 + (i * 2) % 26)
            elif i % 11 == 5:
                expiry = today - datetime.timedelta(days=3 + i % 20)
            elif i % 9 == 4:
                expiry = None
            else:
                expiry = today + datetime.timedelta(days=120 + (i * 17) % 600)

            holder = None if i % 3 == 2 else employees[(i * 3 + 1) % len(employees)]
            is_returned = holder is not None and i % 4 == 1
            if holder is not None and not is_returned:
                status = "In use"
            elif holder is None and i % 8 in (5, 7):
                status = "Not-Available"
            else:
                status = "Available"

            tracking_id = f"AST-{company.pk}-{i + 1:04d}"
            asset = Asset._base_manager.create(
                asset_name=name,
                asset_description=f"{name} issued by IT.",
                asset_tracking_id=tracking_id,
                asset_purchase_date=purchased,
                asset_purchase_cost=cost,
                asset_category_id=categories[cat],
                asset_status=status,
                expiry_date=expiry,
            )
            item = asset.asset_items.get()
            AssetItem._base_manager.filter(pk=item.pk).update(
                status=item_status[status]
            )
            asset.update_status_from_items()
            if holder is None:
                continue

            assigned = min(purchased + datetime.timedelta(days=1 + i % 3), today)
            assignment = AssetAssignment._base_manager.create(
                asset_id=asset,
                asset_item_id=item,
                assigned_to_employee_id=holder,
                assigned_by_employee_id=manager,
            )
            fields = {"assigned_date": assigned}
            if is_returned:
                fields.update(
                    return_date=min(
                        assigned + datetime.timedelta(days=5 + i % 20), today
                    ),
                    return_status=ASSET_RETURN_STATUSES[
                        returned % len(ASSET_RETURN_STATUSES)
                    ],
                    return_condition="Returned after the assignment ended.",
                )
                returned += 1
            else:
                in_use += 1
                open_assignments.append((assignment, assigned))
            AssetAssignment._base_manager.filter(pk=assignment.pk).update(**fields)

        for j in range(ASSET_REQUESTS_PER_COMPANY):
            bucket = ASSET_MONTH_BUCKETS[j % len(ASSET_MONTH_BUCKETS)]
            month_start = _add_months(this_month_start, bucket)
            if bucket == 0:
                requested_on = month_start + datetime.timedelta(
                    days=(j * 2) % today.day
                )
            else:
                requested_on = month_start + datetime.timedelta(days=(j * 4) % 27)
            status = ASSET_REQUEST_STATUSES[j % len(ASSET_REQUEST_STATUSES)]
            if bucket < 0 and status == "Requested":
                status = "Approved"
            request = AssetRequest._base_manager.create(
                requested_employee_id=employees[(j * 5 + 2) % len(employees)],
                asset_category_id=categories[ASSET_CATALOG[j % len(ASSET_CATALOG)][0]],
                description=ASSET_REQUEST_NOTES[j % len(ASSET_REQUEST_NOTES)],
                asset_request_status=status,
            )
            AssetRequest._base_manager.filter(pk=request.pk).update(
                asset_request_date=requested_on
            )

        service = 0
        for k, (assignment, assigned) in enumerate(open_assignments[::2]):
            status = ASSET_SERVICE_STATUSES[k % len(ASSET_SERVICE_STATUSES)]
            requested_on = min(assigned + datetime.timedelta(days=3 + k), today)
            fields = {"request_date": requested_on}
            extra = {}
            if status in ("Completed", "Rejected"):
                extra["resolved_by_employee_id"] = manager
                fields["resolved_date"] = min(
                    requested_on + datetime.timedelta(days=2), today
                )
            request = AssetServiceRequest._base_manager.create(
                assignment_id=assignment,
                requested_employee_id=assignment.assigned_to_employee_id,
                issue_description=ASSET_SERVICE_ISSUES[k % len(ASSET_SERVICE_ISSUES)],
                status=status,
                **extra,
            )
            AssetServiceRequest._base_manager.filter(pk=request.pk).update(**fields)
            service += 1

        self.stdout.write(
            f"  Assets: {ASSETS_PER_COMPANY} assets ({in_use} in use, {returned} returned), "
            f"{ASSET_REQUESTS_PER_COMPANY} requests, {service} service requests"
        )
        return ASSETS_PER_COMPANY, ASSET_REQUESTS_PER_COMPANY, service

    # -- recruitment -------------------------------------------------------------

    def _recruitment_for(self, company, employees, today):
        """Branch-scoped recruitments with stages, back-dated candidates and interviews."""
        from django.utils import timezone

        from base.models import JobPosition
        from recruitment.models import (
            Candidate,
            InterviewSchedule,
            Recruitment,
            SkillZone,
            SkillZoneCandidate,
            Stage,
        )

        positions = {
            p.job_position: p for p in JobPosition.objects.filter(company_id=company)
        }
        managers = employees[:3]
        this_month_start = today.replace(day=1)
        candidates_created = interviews_created = hired_total = 0
        pool_candidates = []

        for r, (position_name, vacancy, hire_target) in enumerate(RECRUITMENT_PLANS):
            position = positions[position_name]
            recruitment = Recruitment.default.create(
                title=f"{position_name} Hiring",
                description=f"Open hiring for {vacancy} {position_name} position(s) at {company.company}.",
                vacancy=vacancy,
                company_id=company,
                job_position_id=position,
                start_date=today - datetime.timedelta(days=75),
                is_published=True,
            )
            recruitment.open_positions.add(position)
            recruitment.recruitment_managers.set(managers)

            stages = {
                stage.stage_type: stage
                for stage in Stage._base_manager.filter(recruitment_id=recruitment)
            }
            for stage_name, stage_type, sequence in RECRUITMENT_EXTRA_STAGES:
                stages[stage_type] = Stage._base_manager.create(
                    recruitment_id=recruitment,
                    stage=stage_name,
                    stage_type=stage_type,
                    sequence=sequence,
                )
            for stage in stages.values():
                stage.stage_managers.set(managers)

            hires_left = hire_target
            for i, stage_type in enumerate(RECRUITMENT_STAGE_PATTERN):
                if stage_type == "hired":
                    if hires_left == 0:
                        stage_type = "interview"
                    else:
                        hires_left -= 1

                first = CANDIDATE_FIRST_NAMES[(r * 7 + i) % len(CANDIDATE_FIRST_NAMES)]
                last = CANDIDATE_LAST_NAMES[(r * 3 + i * 5) % len(CANDIDATE_LAST_NAMES)]
                referral_source = RECRUITMENT_REFERRAL_SOURCES[
                    (i * 3 + r) % len(RECRUITMENT_REFERRAL_SOURCES)
                ]
                if stage_type == "hired":
                    offer_status = ["accepted", "joined", "accepted"][hired_total % 3]
                elif stage_type == "interview":
                    offer_status = "sent" if i % 2 else "not_sent"
                elif stage_type == "cancelled":
                    offer_status = "rejected" if i % 2 else "not_sent"
                else:
                    offer_status = "not_sent"

                candidate = Candidate._base_manager.create(
                    name=f"{first} {last}",
                    recruitment_id=recruitment,
                    job_position_id=position,
                    stage_id=stages[stage_type],
                    email=f"{first}.{last}.{recruitment.pk}.{i}@example.com".lower(),
                    mobile=f"+1555{recruitment.pk % 100:02d}{i:02d}{(i * 37) % 1000:03d}",
                    gender="female" if (i + r) % 2 else "male",
                    source=RECRUITMENT_SOURCES[(i + r) % len(RECRUITMENT_SOURCES)],
                    referral_source=referral_source,
                    referral=(
                        employees[(i * 7 + r) % len(employees)]
                        if referral_source == "employee_referral"
                        else None
                    ),
                    offer_letter_status=offer_status,
                    city=CANDIDATE_CITIES[(r + i) % len(CANDIDATE_CITIES)],
                    country="United States",
                )

                bucket = RECRUITMENT_MONTH_BUCKETS[i]
                month_start = _add_months(this_month_start, bucket)
                if bucket == 0:
                    applied_on = month_start + datetime.timedelta(
                        days=(i * 2 + r) % today.day
                    )
                else:
                    applied_on = month_start + datetime.timedelta(days=(i * 3 + r) % 27)
                fields = {
                    "created_at": timezone.make_aware(
                        datetime.datetime.combine(applied_on, datetime.time(10, 0))
                    )
                }
                if stage_type == "hired":
                    hired_on = min(
                        applied_on + datetime.timedelta(days=8 + (i + r) % 9), today
                    )
                    fields["hired_date"] = hired_on
                    fields["joining_date"] = hired_on + datetime.timedelta(
                        days=14 + (i * 3) % 17
                    )
                    hired_total += 1
                Candidate._base_manager.filter(pk=candidate.pk).update(**fields)
                candidates_created += 1
                if stage_type in ("cancelled", "initial", "test"):
                    pool_candidates.append(candidate)

                if stage_type != "interview":
                    continue
                interview_date = max(
                    this_month_start,
                    today + datetime.timedelta(days=((i + r * 2) % 11) - 4),
                )
                interview = InterviewSchedule._base_manager.create(
                    candidate_id=candidate,
                    interview_date=interview_date,
                    interview_time=datetime.time(10 + (i + r) % 6, 30 if i % 2 else 0),
                    description=f"Panel round for the {position_name} opening.",
                    completed=interview_date < today,
                )
                interview.employee_id.set(managers[:2])
                interviews_created += 1

        pool_members = 0
        for p, (title, description) in enumerate(TALENT_POOLS):
            pool = SkillZone._base_manager.create(
                title=title, description=description, company_id=company
            )
            members = pool_candidates[p :: len(TALENT_POOLS)][:TALENT_POOL_MEMBERS]
            for m, member in enumerate(members):
                SkillZoneCandidate._base_manager.create(
                    skill_zone_id=pool,
                    candidate_id=member,
                    reason=TALENT_POOL_REASONS[(p + m) % len(TALENT_POOL_REASONS)],
                )
                pool_members += 1

        self.stdout.write(
            f"  Recruitment: {len(RECRUITMENT_PLANS)} recruitments, "
            f"{candidates_created} candidates ({hired_total} hired), "
            f"{interviews_created} interviews, "
            f"{len(TALENT_POOLS)} talent pools ({pool_members} members)"
        )
        return (
            len(RECRUITMENT_PLANS),
            candidates_created,
            hired_total,
            interviews_created,
            len(TALENT_POOLS),
            pool_members,
        )

    def _performance_for(self, company, employees, today, slot):
        """Objectives, employee key results, 360 feedback, meetings and bonus points for the branch."""
        from django.utils import timezone

        from pms.models import (
            EmployeeBonusPoint,
            EmployeeKeyResult,
            EmployeeObjective,
            Feedback,
            KeyResult,
            Meetings,
            Objective,
            Question,
            QuestionTemplate,
        )

        rng = random.Random(7 + slot)
        staff = employees[:PERFORMANCE_EMPLOYEES_PER_COMPANY]
        month_start = today.replace(day=1)

        template = QuestionTemplate.objects.create(
            question_template=f"{company.company} Performance Review"
        )
        template.company_id.add(company)
        for text, kind in PERFORMANCE_QUESTIONS:
            Question.objects.create(
                question=text, question_type=kind, template_id=template
            )

        first = sum(PERFORMANCE_OBJECTIVES_PER_COMPANY[:slot])
        count = PERFORMANCE_OBJECTIVES_PER_COMPANY[
            slot % len(PERFORMANCE_OBJECTIVES_PER_COMPANY)
        ]
        objectives = []
        for index, (title, kr_titles) in enumerate(
            PERFORMANCE_OBJECTIVES[first : first + count]
        ):
            objective = Objective.objects.create(
                title=title,
                description=f"{title} across {company.company}.",
                company_id=company,
            )
            objective.managers.add(
                *[
                    staff[(index + step) % len(staff)]
                    for step in range(PERFORMANCE_MANAGERS_PER_OBJECTIVE)
                ]
            )
            key_results = [
                KeyResult.objects.create(
                    title=kr_title,
                    description=kr_title,
                    progress_type="%",
                    target_value=100,
                    company_id=company,
                )
                for kr_title in kr_titles
            ]
            objective.key_result_id.add(*key_results)
            objectives.append((objective, key_results))

        employee_objectives = employee_key_results = 0
        for index, employee in enumerate(staff):
            objective, key_results = objectives[index % len(objectives)]
            status = PERFORMANCE_STATUSES[index % len(PERFORMANCE_STATUSES)]
            low, high = PERFORMANCE_PROGRESS_RANGE[status]
            progress = rng.randint(low, high)
            start = month_start - datetime.timedelta(days=rng.randint(5, 45))
            end = today + datetime.timedelta(days=rng.randint(20, 90))
            if status == "Closed":
                end = max(
                    month_start, today - datetime.timedelta(days=rng.randint(0, 6))
                )

            employee_objective = EmployeeObjective.objects.create(
                employee_id=employee,
                objective_id=objective,
                objective=objective.title,
                objective_description=objective.description,
                start_date=start,
                end_date=end,
                status=status,
                progress_percentage=progress,
            )
            employee_objective.key_result_id.add(*key_results)
            employee_objectives += 1
            for key_result in key_results:
                if status == "Closed":
                    kr_progress = 100
                elif status == "Not Started":
                    kr_progress = 0
                else:
                    kr_progress = max(0, min(100, progress + rng.randint(-12, 12)))
                EmployeeKeyResult.objects.create(
                    key_result=key_result.title,
                    key_result_description=key_result.description,
                    employee_objective_id=employee_objective,
                    key_result_id=key_result,
                    progress_type="%",
                    status=status,
                    start_value=0,
                    current_value=kr_progress,
                    target_value=100,
                    start_date=start,
                    end_date=end,
                    progress_percentage=kr_progress,
                )
                employee_key_results += 1
            EmployeeObjective.objects.filter(pk=employee_objective.pk).update(
                end_date=end
            )

        feedbacks = 0
        for index, employee in enumerate(staff[:PERFORMANCE_FEEDBACKS_PER_COMPANY]):
            feedback = Feedback.objects.create(
                review_cycle=PERFORMANCE_FEEDBACK_CYCLES[
                    index % len(PERFORMANCE_FEEDBACK_CYCLES)
                ],
                employee_id=employee,
                manager_id=staff[(index + 1) % len(staff)],
                question_template_id=template,
                status=PERFORMANCE_FEEDBACK_STATUSES[
                    index % len(PERFORMANCE_FEEDBACK_STATUSES)
                ],
                start_date=month_start - datetime.timedelta(days=rng.randint(0, 20)),
                end_date=today + datetime.timedelta(days=rng.randint(10, 40)),
            )
            feedback.colleague_id.add(
                *[staff[(index + step) % len(staff)] for step in (2, 3)]
            )
            feedbacks += 1

        now = timezone.make_aware(
            datetime.datetime.combine(today, datetime.time(11, 0))
        )
        meetings = 0
        for index, offset in enumerate(PERFORMANCE_MEETING_DAY_OFFSETS):
            meeting = Meetings.objects.create(
                title=PERFORMANCE_MEETING_TITLES[
                    index % len(PERFORMANCE_MEETING_TITLES)
                ],
                date=now + datetime.timedelta(days=offset, hours=index % 4),
                company_id=company,
            )
            meeting.employee_id.add(
                staff[index % len(staff)], staff[(index + 5) % len(staff)]
            )
            meeting.manager.add(staff[-(index + 1) % len(staff)])
            meetings += 1

        bonus_awards = 0
        for employee_objective in EmployeeObjective.objects.filter(
            status="Closed", employee_id__in=[employee.pk for employee in staff]
        ).select_related("employee_id"):
            EmployeeBonusPoint.objects.create(
                employee_id=employee_objective.employee_id,
                bonus_point=rng.choice([10, 15, 20]),
                instance=employee_objective.objective,
                based_on="objective",
            )
            bonus_awards += 1
        for employee in staff[:3]:
            EmployeeBonusPoint.objects.create(
                employee_id=employee,
                bonus_point=rng.choice([5, 10]),
                instance="Key result milestone",
                based_on="key result",
            )
            bonus_awards += 1

        self.stdout.write(
            f"  Performance: {len(objectives)} objectives, {employee_objectives} employee "
            f"objectives, {employee_key_results} key results, {feedbacks} feedbacks, "
            f"{meetings} meetings, {bonus_awards} bonus awards"
        )
        return (
            len(objectives),
            employee_objectives,
            employee_key_results,
            feedbacks,
            meetings,
            bonus_awards,
        )

    def _onboarding_for(self, company, employees, today):
        """Branch-scoped onboarding pipeline for this company's hired candidates.

        Walks every candidate _recruitment_for() left at the "hired" stage
        through ONBOARDING_PROGRESS_PLAN, cycling that plan across them so
        the onboarding dashboard has real pipeline/task/portal data to show
        instead of starting empty. None of these candidates get a
        converted_employee_id -- that flag marks a candidate as having left
        the pipeline for good, which the dashboard and pipeline board both
        treat as "no longer onboarding" and would just make them disappear.
        """
        import secrets

        from employee.models import Employee
        from onboarding.models import (
            CandidateStage,
            CandidateTask,
            OnboardingPortal,
            OnboardingStage,
            OnboardingTask,
        )
        from recruitment.models import Candidate

        managers = employees[:3]
        # The superuser (only ever on COMPANIES[0] -- see _superuser()) is
        # who actually logs in to check the dashboard, so their own "Managing
        # Tasks" sidebar panel (which reads OnboardingTask.employee_id, not
        # any stage/recruitment manager list) needs to carry at least some of
        # these tasks too, or it's empty for the one person demoing this.
        admin_employee = Employee._base_manager.filter(
            employee_user_id__username="admin"
        ).first()
        task_managers = managers + [admin_employee] if admin_employee else managers
        hired_candidates = list(
            Candidate._base_manager.filter(
                recruitment_id__company_id=company,
                stage_id__stage_type="hired",
            ).order_by("id")
        )
        if not hired_candidates:
            return 0, 0, 0

        onboarded = portal_sent = portal_incomplete = stuck_tasks = 0
        # recruitment_id -> ({stage_title: OnboardingStage}, {stage_title: OnboardingTask})
        pipeline_cache = {}

        for i, candidate in enumerate(hired_candidates):
            recruitment = candidate.recruitment_id
            if recruitment.pk not in pipeline_cache:
                stages = {
                    "Initial": OnboardingStage._base_manager.get(
                        recruitment_id=recruitment, stage_title="Initial"
                    )
                }
                for seq, stage_title in enumerate(ONBOARDING_STAGE_TITLES[1:], start=1):
                    stages[stage_title] = OnboardingStage._base_manager.create(
                        stage_title=stage_title,
                        recruitment_id=recruitment,
                        sequence=seq,
                        is_final_stage=(stage_title == ONBOARDING_STAGE_TITLES[-1]),
                    )
                for stage in stages.values():
                    stage.employee_id.set(managers)

                tasks = {}
                for stage_title, task_title in ONBOARDING_STAGE_TASKS.items():
                    task = OnboardingTask._base_manager.create(
                        task_title=task_title,
                        stage_id=stages[stage_title],
                        is_required=True,
                    )
                    task.employee_id.set(task_managers)
                    tasks[stage_title] = task
                pipeline_cache[recruitment.pk] = (stages, tasks)

            stages, tasks = pipeline_cache[recruitment.pk]
            current_stage_title, current_status, portal_used = ONBOARDING_PROGRESS_PLAN[
                i % len(ONBOARDING_PROGRESS_PLAN)
            ]
            current_index = ONBOARDING_STAGE_TITLES.index(current_stage_title)

            CandidateStage._base_manager.create(
                candidate_id=candidate,
                onboarding_stage_id=stages[current_stage_title],
            )
            onboarded += 1

            for stage_title in ONBOARDING_STAGE_TITLES[:current_index]:
                CandidateTask._base_manager.create(
                    candidate_id=candidate,
                    stage_id=stages[stage_title],
                    onboarding_task_id=tasks[stage_title],
                    status="done",
                )
            CandidateTask._base_manager.create(
                candidate_id=candidate,
                stage_id=stages[current_stage_title],
                onboarding_task_id=tasks[current_stage_title],
                status=current_status,
            )
            if current_status == "stuck":
                stuck_tasks += 1

            if portal_used is not None:
                OnboardingPortal._base_manager.create(
                    candidate_id=candidate,
                    token=secrets.token_hex(15),
                    used=portal_used,
                )
                # Mirrors what the real "Send Portal" action does (see
                # email_send in onboarding/views.py) -- flips once a portal
                # is actually sent, not just because the candidate is in the
                # pipeline.
                Candidate._base_manager.filter(pk=candidate.pk).update(
                    start_onboard=True
                )
                portal_sent += 1
                if not portal_used:
                    portal_incomplete += 1

        self.stdout.write(
            f"  Onboarding:  {onboarded} candidates in the pipeline, "
            f"{portal_sent} portals sent ({portal_incomplete} incomplete), "
            f"{stuck_tasks} stuck task(s)"
        )
        return onboarded, portal_sent, portal_incomplete


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
            self.GET = {}

    _thread_locals.request = _Request(user)
    try:
        yield
    finally:
        _thread_locals.request = previous
