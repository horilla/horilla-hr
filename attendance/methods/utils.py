"""
utils.py

This module is used write custom methods
"""

import calendar
from datetime import date, datetime, time, timedelta

import pandas as pd
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _

from base.methods import get_pagination
from base.models import WEEK_DAYS, CompanyLeaves, Holidays
from employee.models import Employee

MONTH_MAPPING = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def format_time(seconds):
    """
    this method is used to formate seconds to H:M and return it
    args:
        seconds : seconds
    """

    hour = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int((seconds % 3600) % 60)
    return f"{hour:02d}:{minutes:02d}"


def strtime_seconds(time):
    """
    this method is used reconvert time in H:M formate string back to seconds and return it
    args:
        time : time in H:M format
    """

    ftr = [3600, 60, 1]
    return sum(a * b for a, b in zip(ftr, map(int, time.split(":"))))


def get_diff_obj(first_instance, other_instance, exclude_fields=None):
    """
    Compare the fields of two instances and identify the changes.

    Args:
        first_instance: The first instance to compare.
        other_instance: The second instance to compare.
        exclude_fields: A list of field names to exclude from comparison (optional).

    Returns:
        A dictionary of changed fields with their old and new values.
    """
    difference = {}

    fields_to_compare = first_instance._meta.fields

    if exclude_fields:
        fields_to_compare = [
            field for field in fields_to_compare if field.name not in exclude_fields
        ]

    for field in fields_to_compare:
        old_value = getattr(first_instance, field.name)
        new_value = getattr(other_instance, field.name)

        if old_value != new_value:
            difference[field.name] = (old_value, new_value)

    return difference


def get_diff_dict(first_dict, other_dict, model=None):
    """
    Compare two dictionaries and identify differing key-value pairs.

    Args:
        first_dict: The first dictionary to compare.
        other_dict: The second dictionary to compare.
        model: The model class (optional, for verbose names and type-specific formatting)

    Returns:
        A dictionary of differing keys with their old and new values.
    """
    difference = {}

    for key, value in first_dict.items():
        other_value = other_dict.get(key)
        if value == other_value:
            continue  # Skip if values are the same

        if not model:
            difference[key] = (value, other_value)
            continue

        # Fetch the model field metadata
        field = model._meta.get_field(key)
        verbose_key = field.verbose_name

        # Handle specific field types
        if isinstance(field, models.DateField):
            value = (
                datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
                if value and value != "None"
                else value
            )
            other_value = (
                datetime.strptime(other_value, "%Y-%m-%d").strftime("%d %b %Y")
                if other_value and other_value != "None"
                else other_value
            )
        elif isinstance(field, models.TimeField):

            def format_time(val):
                if val and val != "None":
                    val += ":00" if len(val.split(":")) == 2 else ""
                    return datetime.strptime(val, "%H:%M:%S").strftime("%I:%M %p")
                return val

            value = format_time(value)
            other_value = format_time(other_value)
        elif isinstance(field, models.ForeignKey):
            value = (
                field.related_model.objects.get(id=value)
                if value and str(value).isdigit()
                else value
            )
            other_value = (
                field.related_model.objects.get(id=other_value)
                if other_value and str(other_value).isdigit()
                else other_value
            )

        # Add the difference
        difference[verbose_key] = (value, other_value)

    return difference


def employee_exists(request):
    """
    This method return the employee instance and work info if not exists return None instead
    """
    employee, employee_work_info = None, None
    try:
        employee = request.user.employee_get
        employee_work_info = employee.employee_work_info
    except Exception:
        # Either attribute is absent for an AnonymousUser or a user with no
        # Employee/EmployeeWorkInformation row; callers expect None rather
        # than an exception. `except Exception` instead of a bare `finally`
        # so KeyboardInterrupt and SystemExit still propagate.
        pass
    return (employee, employee_work_info)


def shift_schedule_today(day, shift):
    """
    This function is used to find shift schedules for the day,
    it will returns min hour,start time seconds  end time seconds
    args:
        shift   : shift instance
        day     : shift day object
    """
    schedule_today = day.day_schedule.filter(shift_id=shift)
    start_time_sec, end_time_sec, minimum_hour = 0, 0, "00:00"
    if schedule_today.exists():
        schedule_today = schedule_today[0]
        minimum_hour = schedule_today.minimum_working_hour
        start_time_sec = strtime_seconds(schedule_today.start_time.strftime("%H:%M"))
        end_time_sec = strtime_seconds(schedule_today.end_time.strftime("%H:%M"))
    return (minimum_hour, start_time_sec, end_time_sec)


def overtime_calculation(attendance):
    """
    This method is used to calculate overtime of the attendance, it will
    return difference between attendance worked hour and minimum hour if
    and only worked hour greater than minimum hour, else return 00:00
    args:
        attendance : attendance instance
    """

    minimum_hour = attendance.minimum_hour
    at_work = attendance.attendance_worked_hour
    at_work_sec = strtime_seconds(at_work)
    minimum_hour_sec = strtime_seconds(minimum_hour)
    if at_work_sec > minimum_hour_sec:
        return format_time((at_work_sec - minimum_hour_sec))
    return "00:00"


def is_reportingmanger(request, instance):
    """
    if the instance have employee id field then you can use this method to know the
    request user employee is the reporting manager of the instance
    args :
        request : request
        instance : an object or instance of any model contain employee_id foreign key field
    """

    manager = request.user.employee_get
    try:
        employee_workinfo_manager = (
            instance.employee_id.employee_work_info.reporting_manager_id
        )
    except Exception:
        return HttpResponse("This Employee Dont Have any work information")
    return manager == employee_workinfo_manager


def validate_hh_mm_ss_format(value):
    timeformat = "%H:%M:%S"
    try:
        validtime = datetime.strptime(value, timeformat)
        return validtime.time()  # Return the time object if needed
    except ValueError as e:
        raise ValidationError(_("Invalid format, it should be HH:MM:SS format"))


def validate_time_format(value):
    """
    this method is used to validate the format of duration like fields.
    """
    if value.count(":") == 2:
        # If the format is "H:MM:SS", check if it can be reduced to "HH:MM"
        # Django's DurationField internally converts it to a timedelta object, it becomes "0:00:00"
        value = ":".join(value.split(":")[:2])

    if len(value) > 6:
        raise ValidationError(_("Invalid format, it should be HH:MM format"))
    try:
        hour, minute = value.split(":")
        if len(hour) > 3 or len(minute) > 2:
            raise ValidationError(_("Invalid time"))
        hour = int(hour)
        minute = int(minute)
        if len(str(hour)) > 3 or len(str(minute)) > 2 or minute not in range(60):
            raise ValidationError(_("Invalid time, excepted MM:SS"))
    except ValueError as error:
        raise ValidationError(_("Invalid format")) from error


def attendance_date_validate(date):
    """
    Validates if the provided date is not a future date.

    :param date: The date to validate.
    :raises ValidationError: If the provided date is in the future.
    """
    today = datetime.today().date()
    if not date:
        raise ValidationError(_("Check date format."))
    elif date > today:
        raise ValidationError(_("You cannot choose a future date."))


def activity_datetime(attendance_activity):
    """
    This method is used to convert clock-in and clock-out of activity as datetime object
    args:
        attendance_activity : attendance activity instance
    """

    # in
    in_year = attendance_activity.clock_in_date.year
    in_month = attendance_activity.clock_in_date.month
    in_day = attendance_activity.clock_in_date.day
    in_hour = attendance_activity.clock_in.hour
    in_minute = attendance_activity.clock_in.minute
    # out
    out_year = attendance_activity.clock_out_date.year
    out_month = attendance_activity.clock_out_date.month
    out_day = attendance_activity.clock_out_date.day
    out_hour = attendance_activity.clock_out.hour
    out_minute = attendance_activity.clock_out.minute
    return datetime(in_year, in_month, in_day, in_hour, in_minute), datetime(
        out_year, out_month, out_day, out_hour, out_minute
    )


def get_week_start_end_dates(week):
    """
    This method is use to return the start and end date of the week
    """
    # Parse the ISO week date
    year, week_number = map(int, week.split("-W"))

    # Get the date of the first day of the week
    start_date = date.fromisocalendar(year, week_number, 1)

    # Calculate the end date by adding 6 days to the start date
    end_date = start_date + timedelta(days=6)

    return start_date, end_date


def get_month_start_end_dates(year_month):
    """
    This method is use to return the start and end date of the month
    """
    # split year and month separately
    year, month = map(int, year_month.split("-"))
    # Get the first day of the month
    start_date = datetime(year, month, 1).date()

    # Get the last day of the month
    _, last_day = calendar.monthrange(year, month)
    end_date = datetime(year, month, last_day).date()

    return start_date, end_date


def month_date_range(year, month):
    """Return (first_day, last_day) for a month as real dates.

    Exists so queries can say ``attendance_date__range=(...)`` instead of
    ``attendance_date__month=`` / ``__year=``. Those two wrap the column in a
    database function, which makes a plain B-tree index on the column
    unusable -- so the range form is what lets an index be used at all.

    ``get_month_start_end_dates`` above does the same thing from a "YYYY-MM"
    string; this takes the parts separately, which is what the model methods
    have to hand.
    """
    year = int(year)
    month = int(month)
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, 1), date(year, month, last_day)


def worked_hour_data(labels, records):
    """
    To find all the worked hours
    """
    data = {
        "label": "Worked Hours",
        "backgroundColor": "rgba(75, 192, 192, 0.6)",
    }
    dept_records = []
    for dept in labels:
        total_sum = records.filter(
            employee_id__employee_work_info__department_id__department=dept
        ).aggregate(total_sum=Sum("hour_account_second"))["total_sum"]
        dept_records.append(total_sum / 3600 if total_sum else 0)
    data["data"] = dept_records
    return data


def pending_hour_data(labels, records):
    """
    To find all the pending hours
    """
    data = {
        "label": "Pending Hours",
        "backgroundColor": "rgba(255, 99, 132, 0.6)",
    }
    dept_records = []
    for dept in labels:
        total_sum = records.filter(
            employee_id__employee_work_info__department_id__department=dept
        ).aggregate(total_sum=Sum("hour_pending_second"))["total_sum"]
        dept_records.append(total_sum / 3600 if total_sum else 0)
    data["data"] = dept_records
    return data


def get_employee_last_name(attendance):
    """
    This method is used to return the last name
    """
    if attendance.employee_id.employee_last_name:
        return attendance.employee_id.employee_last_name
    return ""


def attendance_day_checking(attendance_date, minimum_hour, employee=None):
    # Convert the string to a datetime object
    attendance_datetime = datetime.strptime(attendance_date, "%Y-%m-%d")

    # Extract name of the day
    attendance_day = attendance_datetime.strftime("%A")

    # Taking all holidays into a list
    leaves = []
    holidays = Holidays.objects.all()
    if employee is not None:
        holidays = holidays.filter(Q(is_specific=False) | Q(employees=employee))
    else:
        holidays = holidays.filter(is_specific=False)
    for holi in holidays:
        start_date = holi.start_date
        end_date = holi.end_date

        # Convert start_date and end_date to datetime objects
        start_date = datetime.strptime(str(start_date), "%Y-%m-%d")
        end_date = datetime.strptime(str(end_date), "%Y-%m-%d")

        # Add dates in between start date and end date including both
        current_date = start_date
        while current_date <= end_date:
            leaves.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

    # Checking attendance date is in holiday list, if found making the minimum hour to 00:00
    for leave in leaves:
        if str(leave) == str(attendance_date):
            minimum_hour = "00:00"
            break

    # Making a dictonary contains week day value and leave day pairs
    company_leaves = {}
    company_leave = CompanyLeaves.objects.all()
    for com_leave in company_leave:
        a = dict(WEEK_DAYS).get(com_leave.based_on_week_day)
        b = com_leave.based_on_week
        company_leaves[b] = a

    # Checking the attendance date is in which week
    week_in_month = str(((attendance_datetime.day - 1) // 7 + 1) - 1)

    # Checking the attendance date is in the company leave or not
    for pairs in company_leaves.items():
        # For all weeks based_on_week is None
        if str(pairs[0]) == "None":
            if str(pairs[1]) == str(attendance_day):
                minimum_hour = "00:00"
                break
        # Checking with based_on_week and attendance_date week
        if str(pairs[0]) == week_in_month:
            if str(pairs[1]) == str(attendance_day):
                minimum_hour = "00:00"
                break
    return minimum_hour


def paginator_qry(qryset, page_number):
    """
    This method is used to paginate queryset
    """
    paginator = Paginator(qryset, get_pagination())
    qryset = paginator.get_page(page_number)
    return qryset


def monthly_leave_days(month, year):
    leave_dates = []
    holidays = Holidays.objects.filter(start_date__month=month, start_date__year=year)
    leave_dates += list(holidays.values_list("start_date", flat=True))

    company_leaves = CompanyLeaves.objects.all()
    for company_leave in company_leaves:
        year = year
        month = month
        based_on_week = company_leave.based_on_week
        based_on_week_day = company_leave.based_on_week_day
        if based_on_week != None:
            calendar.setfirstweekday(6)
            month_calendar = calendar.monthcalendar(year, month)
            weeks = month_calendar[int(based_on_week)]
            weekdays_in_weeks = [day for day in weeks if day != 0]
            for day in weekdays_in_weeks:
                date_name = datetime.strptime(
                    f"{year}-{month:02}-{day:02}", "%Y-%m-%d"
                ).date()
                if (
                    date_name.weekday() == int(based_on_week_day)
                    and date_name not in leave_dates
                ):
                    leave_dates.append(date_name)
        else:
            calendar.setfirstweekday(0)
            month_calendar = calendar.monthcalendar(year, month)
            for week in month_calendar:
                if week[int(based_on_week_day)] != 0:
                    date_name = datetime.strptime(
                        f"{year}-{month:02}-{week[int(based_on_week_day)]:02}",
                        "%Y-%m-%d",
                    ).date()
                    if date_name not in leave_dates:
                        leave_dates.append(date_name)
    return leave_dates


def validate_time_in_minutes(value):
    """
    this method is used to validate the format of duration like fields.
    """
    if len(value) > 5:
        raise ValidationError(_("Invalid format, it should be MM:SS format"))
    try:
        minutes, sec = value.split(":")
        if len(minutes) > 2 or len(sec) > 2:
            raise ValidationError(_("Invalid time, excepted MM:SS"))
        minutes = int(minutes)
        sec = int(sec)
        if minutes not in range(60) or sec not in range(60):
            raise ValidationError(_("Invalid time, excepted MM:SS"))
    except ValueError as e:
        raise ValidationError(_("Invalid format,  excepted MM:SS")) from e


class Session(dict):
    """
    Fake session object that mimics Django's session for biometric requests.
    Provides session_key attribute and dict-like access for context processors.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Generate a unique session key for this fake session
        import uuid

        self.session_key = str(uuid.uuid4())


class Request:
    """
    Represents a request for clock-in or clock-out.

    Attributes:
    - user: The user associated with the request.
    - date: The date of the request.
    - time: The time of the request.
    - path: The path associated with the request (default: "/").
    - session: The session data associated with the request (default: Session with title=None).
    """

    def __init__(
        self,
        user,
        date,
        time,
        datetime,
    ) -> None:
        self.user = user
        self.path = "/"
        self.session = Session({"title": None})
        self.date = date
        self.time = time
        self.datetime = datetime
        self.META = META()

    def build_absolute_uri(self, location=None):
        """
        Build an absolute URI from the location and the variables available in
        this request. Mimics Django's HttpRequest.build_absolute_uri() for
        context processors that need it (e.g. breadcrumbs).
        """
        if location is None:
            location = "/"
        # For fake requests from biometric devices, return a simple default URL
        # The actual URL doesn't matter since this is just for template rendering
        return f"http://localhost{location}"

    def is_secure(self):
        """
        Returns True if the request was made over HTTPS, False otherwise.
        For fake requests from biometric devices, always returns False.
        """
        return False

    def get_host(self):
        """
        Returns the host from the request. Mimics Django's HttpRequest.get_host()
        for context processors that need it.
        """
        return "localhost"


class META:
    """
    Provides access to HTTP metadata keys.
    Dict-like interface so Django context processors (e.g. debug) work when
    this fake request is used (e.g. from ZK biometric punch processing).
    """

    @classmethod
    def keys(cls):
        """
        Retrieve the list of available HTTP metadata keys.

        Returns:
            list: A list of HTTP metadata keys.
        """
        return ["HTTP_HX_REQUEST"]

    def get(self, key, default=None):
        """
        Return the value for key if key is in the metadata, else default.
        Required for Django context processors that call request.META.get().
        """
        return default


def parse_time(time_str):
    if isinstance(time_str, time):  # Check if it's already a time object
        return time_str

    if isinstance(time_str, str):
        for format_str in settings.HORILLA_TIME_FORMATS.values():
            try:
                return datetime.strptime(time_str, format_str).time()
            except ValueError:
                continue
    return None


def parse_date(date_str, error_key, activity):
    try:
        return pd.to_datetime(date_str).date()
    except (pd.errors.ParserError, ValueError):
        activity[error_key] = f"Invalid date format for {error_key.split()[-1]}"
        return None


def parse_datetime(date_str, time_str):
    return (
        datetime.strptime(f"{date_str} {time_str[:5]}", "%Y-%m-%d %H:%M")
        if date_str and time_str
        else None
    )


def get_date(date):
    if isinstance(date, datetime):
        return date
    elif isinstance(date, str):
        for format_name, format_str in settings.HORILLA_DATE_FORMATS.items():
            try:
                return datetime.strptime(date, format_str)
            except ValueError:
                continue
    return None


def sort_activity_dicts(activity_dicts):

    for activity in activity_dicts:
        activity["Attendance Date"] = get_date(activity["Attendance Date"])

    # Filter out any entries where the date could not be parsed
    activity_dicts = [
        activity
        for activity in activity_dicts
        if activity["Attendance Date"] is not None
    ]
    sorted_activity_dicts = sorted(activity_dicts, key=lambda x: x["Attendance Date"])
    return sorted_activity_dicts


def get_employee_attendance_summary(employees, from_date, to_date):
    """
    Return per-employee attendance summary for a date range.

    Intended for use by other apps (e.g. payroll) without importing views.

    Args:
        employees  : Employee queryset, list of Employee instances, or list of PKs
        from_date  : datetime.date — range start (inclusive)
        to_date    : datetime.date — range end   (inclusive)

    Returns:
        dict keyed by employee PK::

            {
                emp_pk: {
                    "employee"             : Employee,
                    "present"              : float,   # 1.0 full day, 0.5 half day
                    "paid_leave"           : int,
                    "unpaid_leave"         : int,
                    "absent"               : float,
                    "week_off"             : int,
                    "holiday"              : int,
                    "total_working"        : int,     # working days in range
                    "conflict_days"        : int,
                    "resolved_conflicts"   : int,
                    "unresolved_conflicts" : int,
                }
            }

    Example::

        from attendance.methods.utils import get_employee_attendance_summary
        import datetime

        summary = get_employee_attendance_summary(
            employees=Employee.objects.filter(department_id=dept),
            from_date=datetime.date(2026, 6, 1),
            to_date=datetime.date(2026, 6, 30),
        )
        emp_data = summary[emp.pk]
        print(emp_data["present"], emp_data["absent"])
    """
    # Local import keeps this callable from any app; avoids circular imports
    # between attendance.methods and attendance.views.
    from attendance.views.summary import build_monthly_summary

    # Coerce str/datetime to date — handles "2026-06-01" and "2026-6-1"
    def _to_date(val):
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        y, m, d = str(val).split("-")
        return date(int(y), int(m), int(d))

    from_date = _to_date(from_date)
    to_date = _to_date(to_date)

    # Normalise employees to a queryset
    if not hasattr(employees, "model"):
        pks = [e.pk if hasattr(e, "pk") else int(e) for e in employees]
        employees = Employee.objects.filter(pk__in=pks)

    rows, _total_working, _totals = build_monthly_summary(from_date, to_date, employees)
    result = {}
    for row in rows:
        row["paid_days"] = (
            row["present"] + row["paid_leave"] + row["holiday"] + row["week_off"]
        )
        row["unpaid_days"] = row["absent"] + row["unpaid_leave"]
        result[row["employee"].pk] = row
    return result
