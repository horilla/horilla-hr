"""Lightweight model factories for Horilla TestCase suites."""

from __future__ import annotations

from base.models import Company, Department, EmployeeShift, WorkType
from employee.models import Employee, EmployeeWorkInformation
from horilla_auth.models import HorillaUser


def make_company(name: str = "Test Corp", **overrides) -> Company:
    defaults = {
        "company": name,
        "hq": True,
        "address": "1 Test St",
        "country": "US",
        "state": "CA",
        "city": "LA",
        "zip": "90001",
    }
    defaults.update(overrides)
    return Company.objects.create(**defaults)


def make_user(
    username: str,
    *,
    password: str = "pass",
    email: str | None = None,
    is_superuser: bool = False,
) -> HorillaUser:
    email = email or f"{username}@test.horilla"
    if is_superuser:
        return HorillaUser.objects.create_superuser(
            username=username, email=email, password=password
        )
    return HorillaUser.objects.create_user(
        username=username, email=email, password=password
    )


def make_employee(
    *,
    company: Company,
    email: str,
    first_name: str = "Test",
    last_name: str = "Employee",
    phone: str = "9999999999",
    user: HorillaUser | None = None,
    shift: EmployeeShift | None = None,
    work_type: WorkType | None = None,
    department: Department | None = None,
    date_joining=None,
) -> Employee:
    """
    Create an Employee and attach work-info to ``company``.

    Employee.save() auto-creates a HorillaUser when none is set; pass
    ``user=`` to link an existing account instead (avoids orphan-user deletes).
    EmployeeWorkInformation is updated afterward — same pattern as leave/
    attendance holiday fixtures.
    """
    emp = Employee(
        employee_first_name=first_name,
        employee_last_name=last_name,
        email=email,
        phone=phone,
    )
    if user is not None:
        emp.employee_user_id = user
    emp.save()
    updates = {"company_id": company}
    # joiners/leavers and tenure metrics all read date_joining; leaving it
    # null makes an employee invisible to them.
    if date_joining is not None:
        updates["date_joining"] = date_joining
    if shift is not None:
        updates["shift_id"] = shift
    if work_type is not None:
        updates["work_type_id"] = work_type
    if department is not None:
        updates["department_id"] = department
    updated = EmployeeWorkInformation.objects.filter(employee_id=emp).update(**updates)
    if updated == 0:
        EmployeeWorkInformation.objects.create(employee_id=emp, **updates)
    # Avoid stale reverse OneToOne cache from create().
    return Employee.objects.select_related("employee_work_info").get(pk=emp.pk)


# ---------------------------------------------------------------------------
# Domain factories for report/analytics suites.
#
# Imports are deferred into each function so this module keeps importing when
# an optional app is not installed -- callers guard with apps.is_installed().
# Each factory takes the smallest set of arguments that produces a row the
# metric queries will actually pick up (dates inside the period, a status the
# filters accept), and leaves everything else on model defaults.
# ---------------------------------------------------------------------------


def make_attendance(
    *,
    employee,
    attendance_date,
    at_work_second: int = 8 * 3600,
    overtime_second: int = 0,
    minimum_hour: str = "08:00",
    validated: bool = True,
    clock_in="09:00:00",
    clock_out="18:00:00",
):
    """One validated Attendance row with explicit worked/overtime seconds.

    Attendance.save() derives everything from the "HH:MM" strings:

        attendance_overtime = attendance_worked_hour - minimum_hour
        overtime_second     = strtime_seconds(attendance_overtime)
        at_work_second      = strtime_seconds(attendance_worked_hour)

    so passing overtime_second (or at_work_second) directly is silently
    discarded. To get the requested overtime, worked_hour is set to
    minimum_hour plus that many seconds.
    """
    from attendance.models import Attendance

    def _to_seconds(text: str) -> int:
        parts = [int(p) for p in str(text).split(":")[:2]]
        while len(parts) < 2:
            parts.append(0)
        return parts[0] * 3600 + parts[1] * 60

    def _to_hhmm(seconds: int) -> str:
        hours, minutes = divmod(max(0, int(seconds)) // 60, 60)
        return f"{hours:02d}:{minutes:02d}"

    worked_seconds = _to_seconds(minimum_hour) + max(0, int(overtime_second))
    return Attendance.objects.create(
        employee_id=employee,
        attendance_date=attendance_date,
        attendance_clock_in_date=attendance_date,
        attendance_clock_in=clock_in,
        attendance_clock_out_date=attendance_date,
        attendance_clock_out=clock_out,
        attendance_worked_hour=_to_hhmm(worked_seconds),
        minimum_hour=minimum_hour,
        attendance_overtime_approve=bool(overtime_second),
        attendance_validated=validated,
    )


def make_leave_type(name: str = "Annual", total_days: float = 20):
    from leave.models import LeaveType

    return LeaveType.objects.create(name=name, total_days=total_days)


def make_leave_request(
    *,
    employee,
    leave_type,
    start_date,
    end_date,
    status: str = "approved",
    requested_days: float = 1,
):
    """A leave request. ``status`` matters: several metrics count only
    approved rows, so tests need to be able to seed both sides."""
    from leave.models import LeaveRequest

    return LeaveRequest.objects.create(
        employee_id=employee,
        leave_type_id=leave_type,
        start_date=start_date,
        end_date=end_date,
        requested_days=requested_days,
        description="Test leave",
        status=status,
    )


def make_available_leave(*, employee, leave_type, available: float = 10):
    from leave.models import AvailableLeave

    return AvailableLeave.objects.create(
        employee_id=employee,
        leave_type_id=leave_type,
        available_days=available,
    )


def make_payslip(
    *,
    employee,
    start_date,
    end_date,
    gross_pay: float = 5000,
    net_pay: float = 4000,
    status: str = "paid",
):
    from payroll.models.models import Payslip

    return Payslip.objects.create(
        employee_id=employee,
        start_date=start_date,
        end_date=end_date,
        basic_pay=gross_pay,
        gross_pay=gross_pay,
        deduction=gross_pay - net_pay,
        net_pay=net_pay,
        status=status,
        pay_head_data={},
    )


def make_contract(
    *,
    employee,
    start_date,
    wage: float = 60000,
    name: str = "Test Contract",
    end_date=None,
):
    from payroll.models.models import Contract

    return Contract.objects.create(
        contract_name=name,
        employee_id=employee,
        contract_start_date=start_date,
        contract_end_date=end_date,
        wage=wage,
    )


def make_job_position(
    *, title: str = "Test Position", department: Department | None = None
):
    from base.models import JobPosition

    if department is None:
        department, _created = Department.objects.get_or_create(
            department="Test Department"
        )
    position, _created = JobPosition.objects.get_or_create(
        job_position=title, department_id=department
    )
    return position


def make_recruitment(
    *,
    company=None,
    title: str = "Test Opening",
    closed=False,
    job_position=None,
    vacancy: int = 2,
):
    """A recruitment with a usable job position.

    Candidate.save() falls back to the recruitment's ``job_position_id`` when
    the candidate leaves it blank, then rejects it unless it is also in
    ``open_positions`` -- so both have to be set here or every candidate
    insert raises ValidationError({"job_position_id": "Choose valid choice"}).
    """
    from recruitment.models import Recruitment

    if job_position is None:
        job_position = make_job_position()

    rec = Recruitment.objects.create(
        title=title,
        closed=closed,
        job_position_id=job_position,
        vacancy=vacancy,
    )
    rec.open_positions.add(job_position)
    if company is not None:
        rec.company_id = company
        rec.save(update_fields=["company_id"])
    return rec


def make_stage(*, recruitment, stage: str = "Initial", stage_type: str = "initial"):
    """A stage on ``recruitment``.

    Recruitment has a post_save signal that seeds its own default stages
    ("Initial", plus a hired stage), and (recruitment, stage) is unique --
    so get_or_create, not create, or the common case collides.
    """
    from recruitment.models import Stage

    obj, _created = Stage.objects.get_or_create(
        recruitment_id=recruitment,
        stage=stage,
        defaults={"stage_type": stage_type},
    )
    return obj


def get_hired_stage(*, recruitment):
    """The hired stage the Recruitment signal creates, if present."""
    from recruitment.models import Stage

    return Stage.objects.filter(recruitment_id=recruitment, stage_type="hired").first()


def make_candidate(
    *,
    recruitment,
    email: str,
    stage=None,
    name: str = "Test Candidate",
    hired: bool = False,
):
    from recruitment.models import Candidate

    return Candidate.objects.create(
        name=name,
        email=email,
        recruitment_id=recruitment,
        stage_id=stage,
        hired=hired,
    )


def make_resignation(
    *,
    employee,
    planned_to_leave_on,
    status: str = "approved",
    title: str = "Resignation",
):
    """An approved resignation, which report.metrics._exits counts as an exit.

    Only ``status="approved"`` rows are treated as exits, so the default
    matches what the reports actually read.
    """
    from offboarding.models import ResignationLetter

    return ResignationLetter.objects.create(
        employee_id=employee,
        title=title,
        description="Test resignation",
        planned_to_leave_on=planned_to_leave_on,
        status=status,
    )
