"""
Management command: seed_dashboard_demo_data
--------------------------------------------
ADDS demo rows so the dashboard charts have something to show and to test
against. It never deletes or rewrites existing data (unlike
create_branch_demo_fixtures / load_demo_data --flush). Re-running never
doubles up a leave type, ticket or employee-day, but attendance picks a fresh
random set of employees each time, so it keeps adding coverage:

* Leave: every leave type gets requests in a mix of statuses, spread over this
  year and this month and a few days ahead, across all departments. Requests
  are tagged "[demo]" in their description and a type that already has enough
  of them is left alone.
* Departments: a handful of extra departments, each given a share of the
  existing employees (moved out of the big departments, so this one does
  change existing rows). Gives per-department charts more than six bars.
* Leave trend: for every department, this month's leave requests in all three
  statuses (tag "[demo-trend]") with a different count per department and
  status, which is what the Leave Request Trends chart plots.
* Attendance: the last working days up to today, for most active employees,
  with some late arrivals and early departures (and their late/early rows).
  Days an employee already has a row for, or is on approved leave, are skipped.
* Helpdesk: tickets across every ticket type, priority and status
  (title prefix "[demo]").
* Recruitment: candidates with no source get one, so Source of Hire has a
  spread (only rows where it is empty are touched).
* Rejections: open-recruitment candidates are rejected (moved to their
  cancelled stage) with one or more rejection reasons, a few with none, so
  Rejected Candidates by Reason has many bars of different heights. Rows are
  tagged "[demo]" in their description and re-runs only top up to the target.

    python manage.py seed_dashboard_demo_data
    python manage.py seed_dashboard_demo_data --only leave attendance
    python manage.py seed_dashboard_demo_data --only departments leave_trend
    python manage.py seed_dashboard_demo_data --only rejections
    python manage.py seed_dashboard_demo_data --only attendance --days 1   # today only
"""

import datetime
import random

from django.core.management.base import BaseCommand
from django.db import transaction

SECTIONS = (
    "leave",
    "departments",
    "leave_trend",
    "attendance",
    "helpdesk",
    "recruitment",
    "rejections",
)
TAG = "[demo]"
LEAVE_PER_TYPE = 6  # demo requests each leave type should hold
ATTENDANCE_DAYS = 10  # working days back from today
TICKETS = 80
NEW_DEPARTMENTS = [
    "Engineering",
    "Operations",
    "Customer Support",
    "Legal",
    "Design",
    "Procurement",
    "IT Infrastructure",
    "Research & Development",
]
EMPLOYEES_PER_NEW_DEPARTMENT = 14
TREND_TAG = "[demo-trend]"
# "How did you hear about us?" demo mix. Hired candidates lean towards the sources
# that tend to convert (career site, recruiters, campuses), the rest towards the
# high-volume ones (job boards, social media), so the hire rates differ per source.
SOURCE_MIX_HIRED = {
    "company_career_site": 6,
    "recruiter_headhunter": 6,
    "college_university": 4,
    "job_board": 4,
    "search_engine": 3,
    "social_media": 2,
    "advertisement_event": 2,
    "other": 1,
}
SOURCE_MIX_OTHER = {
    "job_board": 9,
    "social_media": 7,
    "search_engine": 5,
    "advertisement_event": 4,
    "company_career_site": 3,
    "college_university": 3,
    "recruiter_headhunter": 2,
    "other": 2,
}
REFERRED_CANDIDATES = 30  # candidates given a referring employee
REJECTED_TARGET = 45  # demo-rejected candidates to hold in total
# (reason title, weight): the heavier a reason, the taller its bar. Titles that do
# not exist in this database are skipped.
REJECTION_REASONS = [
    ("Failed technical assessment", 9),
    ("Not enough experience", 8),
    ("Salary expectation mismatch", 7),
    ("Did not respond to follow-up", 6),
    ("Position filled internally", 5),
    ("Cultural fit concerns", 5),
    ("Candidate withdrew application", 4),
    ("Poor communication skills", 4),
    ("Notice period too long", 3),
    ("Overqualified for role", 3),
    ("Location mismatch", 2),
    ("Failed background check", 2),
    ("Visa sponsorship unavailable", 1),
    ("Budget constraints", 1),
]


def _weekdays_between(start, end):
    day, count = start, 0
    while day <= end:
        if day.weekday() < 5:
            count += 1
        day += datetime.timedelta(days=1)
    return max(count, 1)


class Command(BaseCommand):
    help = "Add demo data for the dashboard charts (additive and re-runnable)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only", nargs="+", choices=SECTIONS, default=list(SECTIONS)
        )
        parser.add_argument(
            "--seed", type=int, default=7, help="Random seed (same seed, same data)."
        )
        parser.add_argument(
            "--days",
            type=int,
            default=ATTENDANCE_DAYS,
            help="Attendance: how many working days back from today to fill (1 = today only).",
        )

    def handle(self, *args, **options):
        self.base_seed = options["seed"]
        self.attendance_days = max(options["days"], 1)
        self.rng = random.Random(self.base_seed)
        self.today = datetime.date.today()
        for section in SECTIONS:
            if section not in options["only"]:
                continue
            # Reloaded per section: "departments" changes what the later ones see.
            self.employees = self.load_employees()
            if not self.employees:
                self.stdout.write(
                    self.style.WARNING(
                        "No active employees with work info; nothing to seed."
                    )
                )
                return
            with transaction.atomic():
                getattr(self, f"seed_{section}")()

    def load_employees(self):
        from employee.models import Employee

        return list(
            Employee.objects.filter(
                is_active=True, employee_work_info__isnull=False
            ).select_related("employee_work_info", "employee_work_info__department_id")
        )

    # -- leave ----------------------------------------------------------------

    def seed_leave(self):
        from leave.models import LeaveRequest, LeaveType

        rng, today = self.rng, self.today
        statuses = ["approved"] * 5 + ["requested"] * 3 + ["rejected", "cancelled"]
        created = 0
        for leave_type in LeaveType.objects.all():
            have = LeaveRequest.objects.filter(
                leave_type_id=leave_type, description__startswith=TAG
            ).count()
            for n in range(LEAVE_PER_TYPE - have):
                employee = rng.choice(self.employees)
                # Roughly half land this month so "This Month" views fill up too.
                if rng.random() < 0.5:
                    start = today.replace(day=1) + datetime.timedelta(
                        days=rng.randint(0, max(today.day - 1, 0) + 14)
                    )
                else:
                    start = today - datetime.timedelta(days=rng.randint(30, 280))
                if start.weekday() >= 5:
                    start += datetime.timedelta(days=7 - start.weekday())
                end = start + datetime.timedelta(days=rng.choice([0, 0, 1, 2]))
                clash = LeaveRequest.objects.filter(
                    employee_id=employee, start_date__lte=end, end_date__gte=start
                ).exclude(status__in=["rejected", "cancelled"])
                if clash.exists():
                    continue
                status = rng.choice(statuses)
                LeaveRequest.objects.create(
                    employee_id=employee,
                    leave_type_id=leave_type,
                    start_date=start,
                    end_date=end,
                    start_date_breakdown="full_day",
                    end_date_breakdown="full_day",
                    requested_days=_weekdays_between(start, end),
                    description=f"{TAG} {leave_type.name}",
                    status=status,
                    reject_reason=(
                        "Not enough cover that week" if status == "rejected" else ""
                    ),
                )
                created += 1
        self.stdout.write(f"Leave: {created} requests added.")

    # -- departments ------------------------------------------------------------

    def seed_departments(self):
        from base.models import Company, Department
        from employee.models import EmployeeWorkInformation

        rng = self.rng
        companies = list(
            Company.objects.filter(
                pk__in=EmployeeWorkInformation.objects.values("company_id").distinct()
            )
        )
        new_names = set(NEW_DEPARTMENTS)
        # Employees still sitting in the original departments are the pool to draw from.
        pool = [
            e
            for e in self.employees
            if e.employee_work_info.department_id_id
            and e.employee_work_info.department_id.department not in new_names
        ]
        rng.shuffle(pool)
        moved = 0
        for name in NEW_DEPARTMENTS:
            department, _ = Department.objects.get_or_create(department=name)
            if companies:
                department.company_id.add(*companies)
            have = EmployeeWorkInformation.objects.filter(
                department_id=department
            ).count()
            for employee in pool[: max(EMPLOYEES_PER_NEW_DEPARTMENT - have, 0)]:
                EmployeeWorkInformation.objects.filter(employee_id=employee).update(
                    department_id=department
                )
                moved += 1
            pool = pool[max(EMPLOYEES_PER_NEW_DEPARTMENT - have, 0) :]
        self.stdout.write(
            f"Departments: {len(NEW_DEPARTMENTS)} ensured, {moved} employees moved in."
        )

    # -- leave trend (requests per department) ----------------------------------

    def seed_leave_trend(self):
        from base.models import Department
        from employee.models import EmployeeWorkInformation
        from leave.models import LeaveRequest, LeaveType

        today = self.today
        month_start = today.replace(day=1)
        next_month = (month_start + datetime.timedelta(days=32)).replace(day=1)
        month_end = next_month - datetime.timedelta(days=1)
        leave_types = list(LeaveType.objects.all()[:6])
        created = 0
        for department in Department.objects.all():
            members = [
                e
                for e in self.employees
                if e.employee_work_info.department_id_id == department.pk
            ]
            if not members or not leave_types:
                continue
            for status, low, high in (
                ("approved", 4, 24),
                ("rejected", 1, 8),
                ("requested", 2, 12),
            ):
                # Same department + status -> same target on every run, but different between them.
                target = random.Random(
                    f"{self.base_seed}-{department.pk}-{status}"
                ).randint(low, high)
                have = LeaveRequest.objects.filter(
                    description__startswith=TREND_TAG,
                    status=status,
                    employee_id__in=members,
                    start_date__gte=month_start,
                    start_date__lte=month_end,
                ).count()
                for _ in range(max(target - have, 0)):
                    for _attempt in range(40):
                        employee = self.rng.choice(members)
                        start = month_start + datetime.timedelta(
                            days=self.rng.randint(0, (month_end - month_start).days)
                        )
                        if start.weekday() >= 5:
                            continue
                        end = start + datetime.timedelta(
                            days=self.rng.choice([0, 0, 1])
                        )
                        if (
                            LeaveRequest.objects.filter(
                                employee_id=employee,
                                start_date__lte=end,
                                end_date__gte=start,
                            )
                            .exclude(status__in=["rejected", "cancelled"])
                            .exists()
                        ):
                            continue
                        leave_type = self.rng.choice(leave_types)
                        LeaveRequest.objects.create(
                            employee_id=employee,
                            leave_type_id=leave_type,
                            start_date=start,
                            end_date=end,
                            start_date_breakdown="full_day",
                            end_date_breakdown="full_day",
                            requested_days=_weekdays_between(start, end),
                            description=f"{TREND_TAG} {department.department}",
                            status=status,
                            reject_reason=(
                                "Not enough cover that week"
                                if status == "rejected"
                                else ""
                            ),
                        )
                        created += 1
                        break
        self.stdout.write(f"Leave trend: {created} requests added across departments.")

    # -- attendance ---------------------------------------------------------

    def seed_attendance(self):
        from attendance.models import Attendance, AttendanceLateComeEarlyOut
        from base.models import EmployeeShiftDay
        from leave.models import LeaveRequest

        rng, today = self.rng, self.today
        days, day = [], today
        while len(days) < self.attendance_days:
            if day.weekday() < 5:
                days.append(day)
            day -= datetime.timedelta(days=1)
        created = late = early = 0
        shift_days = {d.day: d for d in EmployeeShiftDay.objects.all()}
        day_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        for day in days:
            on_leave = set(
                LeaveRequest.objects.filter(
                    status="approved", start_date__lte=day, end_date__gte=day
                ).values_list("employee_id", flat=True)
            )
            have = set(
                Attendance.objects.filter(attendance_date=day).values_list(
                    "employee_id", flat=True
                )
            )
            now = datetime.datetime.now()
            for employee in self.employees:
                if (
                    employee.pk in on_leave
                    or employee.pk in have
                    or rng.random() > 0.78
                ):
                    continue
                info = employee.employee_work_info
                is_late = rng.random() < 0.18
                is_early = not is_late and rng.random() < 0.12
                clock_in = datetime.datetime.combine(day, datetime.time(9, 0))
                clock_out = datetime.datetime.combine(day, datetime.time(18, 0))
                if is_late:
                    clock_in += datetime.timedelta(minutes=rng.randint(15, 70))
                if is_early:
                    clock_out -= datetime.timedelta(minutes=rng.randint(30, 90))
                clock_out += datetime.timedelta(minutes=rng.choice([0, 0, 0, 30, 60]))
                if day == today and clock_out > now:
                    clock_out = max(clock_in, now.replace(second=0, microsecond=0))
                worked = int((clock_out - clock_in).total_seconds())
                attendance = Attendance.objects.create(
                    employee_id=employee,
                    attendance_date=day,
                    shift_id=info.shift_id,
                    work_type_id=info.work_type_id,
                    attendance_day=shift_days.get(day_names[day.weekday()]),
                    attendance_clock_in_date=day,
                    attendance_clock_in=clock_in.time(),
                    attendance_clock_out_date=day,
                    attendance_clock_out=clock_out.time(),
                    attendance_worked_hour=f"{worked // 3600:02d}:{worked % 3600 // 60:02d}",
                    minimum_hour="08:00",
                    attendance_validated=True,
                )
                created += 1
                # Plain save(), as the clock-in views do: create() would double-insert.
                for flag, kind in ((is_late, "late_come"), (is_early, "early_out")):
                    if flag:
                        AttendanceLateComeEarlyOut(
                            attendance_id=attendance, type=kind
                        ).save()
                late += is_late
                early += is_early
        self.stdout.write(
            f"Attendance: {created} rows added ({late} late, {early} early out)."
        )

    # -- helpdesk -------------------------------------------------------------

    def seed_helpdesk(self):
        from helpdesk.models import Ticket, TicketType

        rng, today = self.rng, self.today
        have = Ticket.objects.filter(title__startswith=TAG).count()
        types = list(TicketType.objects.all())
        if not types:
            return
        statuses = (
            ["new"] * 3
            + ["in_progress"] * 3
            + ["on_hold", "resolved", "resolved", "canceled"]
        )
        created = 0
        for n in range(have, TICKETS):
            ticket_type = types[n % len(types)]
            employee = rng.choice(self.employees)
            raised = today - datetime.timedelta(days=rng.randint(0, 180))
            status = rng.choice(statuses)
            Ticket.objects.create(
                title=f"{TAG} {ticket_type.title} #{n + 1}",
                employee_id=employee,
                ticket_type=ticket_type,
                description=f"Demo ticket for {ticket_type.title}.",
                priority=rng.choice(["low", "medium", "high"]),
                created_date=raised,
                resolved_date=(
                    raised + datetime.timedelta(days=rng.randint(1, 10))
                    if status == "resolved"
                    else None
                ),
                deadline=raised + datetime.timedelta(days=rng.randint(3, 21)),
                assigning_type="individual",
                raised_on=str(employee.pk),
                status=status,
            )
            created += 1
        self.stdout.write(f"Helpdesk: {created} tickets added.")

    # -- recruitment --------------------------------------------------------

    def seed_recruitment(self):
        from recruitment.models import Candidate

        sources = [c[0] for c in Candidate._meta.get_field("source").choices]
        blank = list(Candidate.objects.filter(source__isnull=True))
        for i, candidate in enumerate(blank):
            Candidate.objects.filter(pk=candidate.pk).update(
                source=sources[i % len(sources)]
            )
        self.stdout.write(f"Recruitment: {len(blank)} candidates given a source.")

        # Some candidates are referred by an employee: give a few one when nobody has yet
        # (existing referrals are left alone). Done first, so they count as Employee Referral.
        if not Candidate.objects.filter(referral__isnull=False).exists():
            rng = random.Random(self.base_seed)
            referrers = [e for e in self.employees if e.is_active]
            pool = list(Candidate.objects.filter(is_active=True))
            rng.shuffle(pool)
            for candidate in pool[:REFERRED_CANDIDATES]:
                Candidate.objects.filter(pk=candidate.pk).update(
                    referral=rng.choice(referrers)
                )
            self.stdout.write(
                f"Recruitment: {min(REFERRED_CANDIDATES, len(pool))} candidates given a referring employee."
            )

        # "How did you hear about us?" is what Source Conversion Rate groups by. Fill it
        # only where it is empty. Candidates with a referring employee are Employee
        # Referrals; the rest follow the mixes above.
        from django.db.models import Q

        rng = random.Random(self.base_seed)
        unanswered = list(
            Candidate.objects.filter(
                Q(referral_source__isnull=True) | Q(referral_source="")
            ).select_related("stage_id")
        )
        for candidate in unanswered:
            hired = candidate.hired or (
                candidate.stage_id and candidate.stage_id.stage_type == "hired"
            )
            if candidate.referral_id:
                key = "employee_referral"
            else:
                mix = SOURCE_MIX_HIRED if hired else SOURCE_MIX_OTHER
                key = rng.choices(list(mix), weights=list(mix.values()))[0]
            Candidate.objects.filter(pk=candidate.pk).update(
                referral_source=key,
                referral_source_other="Walk-in" if key == "other" else None,
            )
        self.stdout.write(
            f"Recruitment: {len(unanswered)} candidates given a 'how did you hear about us' source."
        )

    # -- rejections ---------------------------------------------------------

    def seed_rejections(self):
        from recruitment.models import Candidate, RejectedCandidate, RejectReason

        rng = self.rng
        reasons = {r.title: r for r in RejectReason.objects.all()}
        pool = [(reasons[t], w) for t, w in REJECTION_REASONS if t in reasons]
        if not pool:
            self.stdout.write(
                self.style.WARNING(
                    "Rejections: no matching rejection reasons; skipped."
                )
            )
            return

        have = RejectedCandidate.objects.filter(description__startswith=TAG).count()
        missing = REJECTED_TARGET - have
        if missing <= 0:
            self.stdout.write(f"Rejections: {have} demo rejections already there.")
            return

        # Open-recruitment candidates still in the running (not hired, not already rejected).
        candidates = list(
            Candidate.objects.filter(
                is_active=True,
                canceled=False,
                hired=False,
                converted=False,
                recruitment_id__closed=False,
            ).exclude(rejected_candidate__isnull=False)
        )
        rng.shuffle(candidates)

        created = 0
        for candidate in candidates:
            if created >= missing:
                break
            # Mostly one reason, sometimes two, a few with none.
            roll = rng.random()
            count = 0 if roll < 0.06 else 2 if roll < 0.28 else 1
            chosen, left = [], list(pool)
            for _ in range(count):
                pick = rng.choices(left, weights=[w for _, w in left])[0]
                chosen.append(pick[0])
                left.remove(pick)
            try:
                with transaction.atomic():
                    # save() moves a canceled candidate to its recruitment's cancelled stage.
                    candidate.canceled = True
                    candidate.save()
                    rejected = RejectedCandidate.objects.create(
                        candidate_id=candidate,
                        description=f"{TAG} Rejected for dashboard testing",
                    )
                    rejected.reject_reason_id.set(chosen)
            except (
                Exception
            ) as exc:  # a candidate that fails validation is simply skipped
                self.stdout.write(
                    self.style.WARNING(
                        f"Rejections: skipped candidate {candidate.pk}: {exc}"
                    )
                )
                continue
            created += 1
        self.stdout.write(f"Rejections: {created} candidates rejected with reasons.")
