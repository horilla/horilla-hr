"""The sample company of the user guide: Lakeside Works Ltd.

Every example and screenshot of the user guide comes from this one installation,
so that a name in a sentence is the name in the picture. See
documentation/11-user-guide-structure.md (STR-07) in the guidelines repository.

The dataset is meant for a throwaway database: reset it with
`manage.py seed_docs_sample --flush`. It is built around a fixed anchor date
(`ANCHOR_DATE`), not the day it runs, so a page written once keeps matching the
data on every later reset. Pass `--today` to move the anchor.

This first slice covers the company, its people and roles, and leave: types,
balances, holidays and requests in each state. Attendance, payroll and the other
modules are added in later slices.
"""

from __future__ import annotations

import json
import logging
from datetime import date, time, timedelta

from django.contrib.auth.models import Group
from django.db import transaction

logger = logging.getLogger(__name__)

COMPANY = "Lakeside Works Ltd"
DEFAULT_PASSWORD = "Lakeside-docs-1"  # a documentation login on a throwaway database
ANCHOR_DATE = date(2026, 11, 18)  # the "today" of every documentation scenario
DOMAIN = "lakesideworks.example"  # a reserved domain: mail to it goes nowhere

DEPARTMENTS = {
    "Engineering": ["Developer", "Engineering Manager"],
    "Design": ["Designer"],
    "Sales": ["Sales Executive", "Sales Manager"],
    "Finance": ["Accountant", "Finance Manager"],
    "People": ["HR Administrator", "HR Manager", "People Coordinator"],
}

# first, last, department, position, group, reports to (last name), days since joining
CAST = [
    ("Daniel", "Okafor", "People", "HR Manager", "HR Manager", None, 2100),
    ("Maya", "Chen", "People", "HR Administrator", None, "Okafor", 1500),
    ("Sofia", "Rossi", "Engineering", "Engineering Manager", None, "Okafor", 1800),
    ("Ravi", "Menon", "Engineering", "Developer", None, "Rossi", 900),
    ("Lena", "Fischer", "Design", "Designer", None, "Rossi", 700),
    ("Omar", "Haddad", "Sales", "Sales Executive", None, "Weber", 600),
    ("Priya", "Nair", "Engineering", "Developer", None, "Rossi", 10),
    ("Tom", "Becker", "Finance", "Finance Manager", "Payroll Manager", "Okafor", 1200),
]

# Colleagues who fill the company out: first, last, department, position
STAFF = [
    ("Jonas", "Weber", "Sales", "Sales Manager"),
    ("Aisha", "Khan", "Engineering", "Developer"),
    ("Mateo", "Silva", "Engineering", "Developer"),
    ("Hana", "Sato", "Engineering", "Developer"),
    ("Liam", "Murphy", "Engineering", "Developer"),
    ("Zara", "Ali", "Engineering", "Developer"),
    ("Erik", "Larsen", "Engineering", "Developer"),
    ("Nia", "Mensah", "Engineering", "Developer"),
    ("Pavel", "Novak", "Engineering", "Developer"),
    ("Chloe", "Dubois", "Engineering", "Developer"),
    ("Yuki", "Tanaka", "Design", "Designer"),
    ("Isla", "Reid", "Design", "Designer"),
    ("Kofi", "Boateng", "Design", "Designer"),
    ("Marta", "Kowal", "Sales", "Sales Executive"),
    ("Diego", "Torres", "Sales", "Sales Executive"),
    ("Fatima", "Noor", "Sales", "Sales Executive"),
    ("Oscar", "Lindqvist", "Sales", "Sales Executive"),
    ("Elena", "Petrova", "Sales", "Sales Executive"),
    ("Samir", "Hassan", "Sales", "Sales Executive"),
    ("Greta", "Holm", "Sales", "Sales Executive"),
    ("Noor", "Rahman", "Finance", "Accountant"),
    ("Ben", "Walsh", "Finance", "Accountant"),
    ("Clara", "Moreau", "People", "People Coordinator"),
    ("Hugo", "Martin", "People", "People Coordinator"),
    ("Anika", "Bose", "People", "People Coordinator"),
    ("Theo", "Berg", "People", "People Coordinator"),
    ("Lucia", "Romano", "Engineering", "Developer"),
    ("Arman", "Sadiq", "Engineering", "Developer"),
    ("Freya", "Olsen", "Design", "Designer"),
    ("Jamal", "Brooks", "Sales", "Sales Executive"),
]

# Reporting line by department, for people who are not in CAST: the last name of the head
DEPARTMENT_HEAD = {
    "Engineering": "Rossi",
    "Design": "Rossi",
    "Sales": "Weber",
    "Finance": "Becker",
    "People": "Okafor",
}
STAFF_HEADS_REPORT_TO = {"Weber": "Okafor"}


def weekday_on_or_after(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def monday_of_week(day: date, weeks_ahead: int) -> date:
    return day - timedelta(days=day.weekday()) + timedelta(weeks=weeks_ahead)


def last_weekday(day: date, weekday: int) -> date:
    """The most recent given weekday (0 = Monday) before `day`."""
    delta = (day.weekday() - weekday) % 7 or 7
    return day - timedelta(days=delta)


def _slug(first: str, last: str) -> str:
    return f"{first}.{last}".lower()


DAY_START, DAY_END = time(9, 0), time(17, 30)
EVENING_START, EVENING_END = time(14, 0), time(22, 30)
DAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _clock(start: time, minutes: int) -> time:
    total = start.hour * 60 + start.minute + minutes
    return time(total // 60, total % 60)


def _hours(start: time, end: time) -> str:
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def seed_shifts_and_attendance(company, people_by_last, shift, work_type, today):
    """Shift schedules and four weeks of attendance for the sample company.

    The schedule is Monday to Friday, 09:00 to 17:30, with Omar Haddad on an
    evening shift. Every other number is derived from the employee's row, so a
    second run of the seeder gives the same pages. Stories the guides use:
    Lena Fischer arrives late on three days of the last week (three Late Arrival
    records), Ravi Menon forgot to check out yesterday (one Early Departure
    record) and has a pending correction request, and the
    latest working day is left unvalidated for the approval guide.
    """
    from attendance.models import Attendance, AttendanceLateComeEarlyOut
    from base.models import EmployeeShift, EmployeeShiftDay, EmployeeShiftSchedule
    from employee.models import Employee

    days = {}
    for name in DAY_NAMES:
        day, _ = EmployeeShiftDay.objects.get_or_create(day=name)
        day.company_id.add(company)
        days[name] = day
    evening, _ = EmployeeShift.objects.get_or_create(employee_shift="Evening Shift")
    evening.company_id.add(company)
    shift.company_id.add(company)
    for owner, start, end in (
        (shift, DAY_START, DAY_END),
        (evening, EVENING_START, EVENING_END),
    ):
        for name in DAY_NAMES[:5]:
            EmployeeShiftSchedule.objects.get_or_create(
                day=days[name],
                shift_id=owner,
                defaults=dict(
                    minimum_working_hour="08:00", start_time=start, end_time=end
                ),
            )
    omar = people_by_last["Haddad"]
    omar.employee_work_info.shift_id = evening
    omar.employee_work_info.save(update_fields=["shift_id"])

    working_days = []
    cursor = today - timedelta(days=1)
    while len(working_days) < 20:
        if cursor.weekday() < 5:
            working_days.append(cursor)
        cursor -= timedelta(days=1)
    working_days.reverse()
    last_week = set(working_days[-5:])
    latest = working_days[-1]
    created = 0
    for employee in Employee.objects.filter(employee_work_info__company_id=company):
        own_shift = employee.employee_work_info.shift_id
        start, end = (
            (EVENING_START, EVENING_END)
            if own_shift == evening
            else (DAY_START, DAY_END)
        )
        for day in working_days:
            seed = employee.pk * 7 + day.toordinal()
            minutes_in = (seed % 9) - 6  # between 6 minutes early and 2 late
            minutes_out = (seed // 3) % 12  # up to 11 minutes after the end
            if (
                employee.employee_last_name == "Fischer"
                and day in last_week
                and day.weekday() in (0, 2, 3)
            ):
                minutes_in = 25
            clock_in, clock_out = _clock(start, minutes_in), _clock(end, minutes_out)
            row = Attendance(
                employee_id=employee,
                attendance_date=day,
                shift_id=own_shift,
                work_type_id=work_type,
                attendance_day=days[DAY_NAMES[day.weekday()]],
                attendance_clock_in_date=day,
                attendance_clock_in=clock_in,
                attendance_clock_out_date=day,
                attendance_clock_out=clock_out,
                attendance_worked_hour=_hours(clock_in, clock_out),
                minimum_hour="08:00",
                attendance_validated=day != latest,
            )
            if employee.employee_last_name == "Menon" and day == latest:
                row.attendance_clock_out = _clock(
                    DAY_START, 5 * 60
                )  # 14:00, forgot to check out
                row.attendance_worked_hour = _hours(clock_in, row.attendance_clock_out)
                row.attendance_validated = False
            row.save()
            created += 1
            # (save(), not create(): the model saves twice and create() forces an insert)
            # the clock-in and clock-out screens record these when someone is
            # late or leaves early; a seeded row has to record them itself
            if minutes_in >= 15:
                AttendanceLateComeEarlyOut(
                    attendance_id=row, employee_id=employee, type="late_come"
                ).save()
            if employee.employee_last_name == "Menon" and day == latest:
                AttendanceLateComeEarlyOut(
                    attendance_id=row, employee_id=employee, type="early_out"
                ).save()
            if employee.employee_last_name == "Menon" and day == latest:
                # the correction the employee asked for: check out at 17:30
                wanted = Attendance.objects.get(pk=row.pk)
                wanted.attendance_clock_out = DAY_END
                wanted.attendance_worked_hour = _hours(
                    wanted.attendance_clock_in, DAY_END
                )
                requested = json.dumps(wanted.serialize())
                pending = Attendance.objects.get(pk=row.pk)
                pending.requested_data = requested
                pending.request_description = (
                    "I forgot to check out when I left the office."
                )
                pending.is_validate_request = True
                pending.save()
    return created


@transaction.atomic
def seed_docs_sample(
    today: date | None = None, password: str = DEFAULT_PASSWORD
) -> dict:
    """Create the sample company; a second call does nothing."""
    from base.models import (
        Company,
        CompanyGroupAssignment,
        Department,
        EmployeeShift,
        Holidays,
        JobPosition,
        WorkType,
    )
    from employee.models import Employee, EmployeeWorkInformation
    from horilla_auth.models import HorillaUser
    from leave.models import AvailableLeave, LeaveRequest, LeaveType

    today = today or ANCHOR_DATE
    if Company.objects.filter(company=COMPANY).exists():
        return {"skipped": f"{COMPANY} already exists; reset with --flush"}

    company = Company.objects.create(
        company=COMPANY,
        hq=True,
        address="12 Harbour Road",
        country="US",
        state="CA",
        city="Lakeside",
        zip="90210",
    )
    work_type, _ = WorkType.objects.get_or_create(work_type="Office")
    work_type.company_id.add(company)
    shift, _ = EmployeeShift.objects.get_or_create(employee_shift="Day Shift")

    departments, positions = {}, {}
    for name, titles in DEPARTMENTS.items():
        department = Department.objects.create(department=name)
        department.company_id.add(company)
        departments[name] = department
        for title in titles:
            positions[(name, title)] = JobPosition.objects.create(
                job_position=title, department_id=department
            )

    people, by_last = [], {}
    rows = [(f, l, d, p, g, r, ago) for f, l, d, p, g, r, ago in CAST]
    for index, (first, last, department, position) in enumerate(STAFF):
        head = DEPARTMENT_HEAD[department]
        report = STAFF_HEADS_REPORT_TO.get(last, None if last == head else head)
        rows.append((first, last, department, position, None, report, 200 + index * 83))

    for first, last, department, position, group, report, ago in rows:
        email = f"{_slug(first, last)}@{DOMAIN}"
        user = HorillaUser.objects.create_user(
            username=email, email=email, password=password
        )
        employee = Employee(
            employee_first_name=first,
            employee_last_name=last,
            email=email,
            phone="5550100",
            employee_user_id=user,
        )
        employee.save()
        by_last[last] = employee
        people.append((employee, user, department, position, group, report, ago))
        if last == "Chen":
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=["is_superuser", "is_staff"])
        elif (first, last) not in {(c[0], c[1]) for c in CAST}:
            # colleagues have no login: only the cast signs in to the guide
            user.set_unusable_password()
            user.save(update_fields=["password"])

    for employee, user, department, position, group, report, ago in people:
        values = {
            "company_id": company,
            "department_id": departments[department],
            "job_position_id": positions[(department, position)],
            "shift_id": shift,
            "work_type_id": work_type,
            "date_joining": today - timedelta(days=ago),
            "reporting_manager_id": by_last[report] if report else None,
        }
        if not EmployeeWorkInformation.objects.filter(employee_id=employee).update(
            **values
        ):
            EmployeeWorkInformation.objects.create(employee_id=employee, **values)
        if group:
            group_row = Group.objects.filter(name=group).first()
            if group_row:
                CompanyGroupAssignment.objects.get_or_create(
                    user=user, group=group_row, company=company
                )
                CompanyGroupAssignment.sync_user_group_membership(user, group_row)

    # --- leave -------------------------------------------------------------
    annual = LeaveType.objects.create(
        name="Annual Leave",
        payment="paid",
        payment_type="paid",
        count=18,
        total_days=18,
        reset=True,
        reset_based="yearly",
        reset_month="1",
        reset_day="1",
        carryforward_type="carryforward",
        carryforward_max=5,
    )
    sick = LeaveType.objects.create(
        name="Sick Leave",
        payment="paid",
        payment_type="paid",
        count=10,
        total_days=10,
    )
    # 100000 days is what the Create Leave Type form stores when Limit Leave Days
    # is off, so an assigned balance behaves like one made through the screen
    LeaveType.objects.create(
        name="Unpaid Leave",
        payment="unpaid",
        payment_type="unpaid",
        limit_leave=False,
        total_days=100000,
    )

    employees = [row[0] for row in people]
    balances = {}
    for leave_type in (annual, sick):
        for employee in employees:
            leave = AvailableLeave(
                leave_type_id=leave_type,
                employee_id=employee,
                available_days=leave_type.total_days,
            )
            if leave.reset_date is None and leave_type.reset:
                leave.reset_date = leave.set_reset_date(
                    assigned_date=leave.assigned_date, available_leave=leave
                )
            leave.expired_date = leave_type.initial_expiry_date(leave.assigned_date)
            leave.total_leave_days = max(
                leave.available_days + leave.carryforward_days, 0
            )
            leave.carryforward_days = max(leave.carryforward_days, 0)
            balances[(leave_type.pk, employee.pk)] = leave
    AvailableLeave.objects.bulk_create(list(balances.values()))

    year = today.year
    for name, month, day_of_month in (
        ("New Year's Day", 1, 1),
        ("Summer Bank Holiday", 8, 25),
        ("Founders' Day", 10, 14),
        ("Winter Break", 12, 25),
    ):
        Holidays.objects.create(
            name=name,
            start_date=date(year, month, day_of_month),
            end_date=date(year, month, day_of_month),
            recurring=True,
            company_id=company,
        )

    def request_leave(employee, leave_type, start, days, status, reason="", note=""):
        end = start
        while days > 1:
            end += timedelta(days=1)
            if end.weekday() < 5:
                days -= 1
        leave_request = LeaveRequest(
            employee_id=employee,
            leave_type_id=leave_type,
            start_date=start,
            end_date=end,
            requested_days=sum(
                1
                for n in range((end - start).days + 1)
                if (start + timedelta(days=n)).weekday() < 5
            ),
            description=note or "Booked in advance",
            status="requested",
        )
        leave_request.save()
        if status == "approved":
            balance = AvailableLeave.objects.get(
                leave_type_id=leave_type, employee_id=employee
            )
            # the same bookkeeping as the Approve action: carried days first
            used = leave_request.requested_days
            from_carry = min(balance.carryforward_days, used)
            balance.carryforward_days -= from_carry
            balance.available_days -= used - from_carry
            leave_request.approved_carryforward_days = from_carry
            leave_request.approved_available_days = used - from_carry
            leave_request.status = "approved"
            leave_request.save()
            balance.save()
        elif status == "rejected":
            leave_request.status = "rejected"
            leave_request.reject_reason = reason
            leave_request.save()
        return leave_request

    next_monday = monday_of_week(today, 1)
    request_leave(
        by_last["Menon"], annual, next_monday, 2, "requested", note="Family visit"
    )
    request_leave(
        by_last["Rossi"],
        annual,
        monday_of_week(today, 2),
        5,
        "requested",
        note="Summer trip",
    )
    request_leave(
        by_last["Fischer"], sick, last_weekday(today, 3), 1, "approved", note="Flu"
    )
    request_leave(
        by_last["Haddad"],
        annual,
        monday_of_week(today, -3),
        3,
        "approved",
        note="Wedding",
    )
    request_leave(
        by_last["Becker"],
        annual,
        weekday_on_or_after(today + timedelta(days=2)),
        1,
        "rejected",
        reason="Month-end close",
        note="Personal errand",
    )

    attendance_rows = seed_shifts_and_attendance(
        company, by_last, shift, work_type, today
    )

    summary = {
        "company": COMPANY,
        "employees": len(people),
        "logins": [f"{_slug(c[0], c[1])}@{DOMAIN}" for c in CAST],
        "leave_requests": LeaveRequest.objects.count(),
        "attendance_rows": attendance_rows,
    }
    logger.info("Docs sample seeded: %s", summary)
    return summary
