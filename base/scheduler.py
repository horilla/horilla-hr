import calendar
from datetime import date, datetime, timedelta

from django.urls import reverse

from horilla.scheduling import register_job
from notifications.signals import notify


def update_rotating_work_type_assign(rotating_work_type, new_date):
    """
    Here will update the employee work information details and send notification
    """
    from horilla_auth.models import HorillaUser

    employee = rotating_work_type.employee_id
    employee_work_info = employee.employee_work_info
    work_type1 = rotating_work_type.rotating_work_type_id.work_type1
    work_type2 = rotating_work_type.rotating_work_type_id.work_type2
    additional_work_types = (
        rotating_work_type.rotating_work_type_id.additional_work_types()
    )
    if additional_work_types is None:
        total_rotate_work_types = [work_type1, work_type2]
    else:
        total_rotate_work_types = [work_type1, work_type2] + list(additional_work_types)
    next_work_type_index = rotating_work_type.additional_data.get(
        "next_work_type_index", 0
    )
    next_work_type = total_rotate_work_types[next_work_type_index]
    if next_work_type_index < len(total_rotate_work_types) - 1:
        next_work_type_index += 1
    else:
        next_work_type_index = 0

    rotating_work_type.additional_data["next_work_type_index"] = next_work_type_index
    employee_work_info.work_type_id = rotating_work_type.next_work_type
    employee_work_info.save()
    rotating_work_type.next_change_date = new_date
    rotating_work_type.current_work_type = rotating_work_type.next_work_type
    rotating_work_type.next_work_type = next_work_type
    rotating_work_type.save()
    bot = HorillaUser.objects.filter(username="Horilla Bot").first()
    if bot is not None:
        employee = rotating_work_type.employee_id
        notify.send(
            bot,
            recipient=employee.employee_user_id,
            verb="Your Work Type has been changed.",
            verb_ar="لقد تغير نوع عملك.",
            verb_de="Ihre Art der Arbeit hat sich geändert.",
            verb_es="Su tipo de trabajo ha sido cambiado.",
            verb_fr="Votre type de travail a été modifié.",
            icon="infinite",
            redirect=reverse("employee-profile"),
        )
    return


def work_type_rotate_after(rotating_work_work_type):
    """
    This method for rotate work type based on after day
    """
    date_today = datetime.now()
    switch_date = rotating_work_work_type.next_change_date
    if switch_date.strftime("%Y-%m-%d") == date_today.strftime("%Y-%m-%d"):
        new_date = date_today + timedelta(days=rotating_work_work_type.rotate_after_day)
        update_rotating_work_type_assign(rotating_work_work_type, new_date)
    return


def work_type_rotate_weekend(rotating_work_type):
    """
    This method for rotate work type based on weekend
    """
    date_today = datetime.now()
    switch_date = rotating_work_type.next_change_date
    if switch_date.strftime("%Y-%m-%d") == date_today.strftime("%Y-%m-%d"):
        day = datetime.now().strftime("%A").lower()
        switch_day = rotating_work_type.rotate_every_weekend
        if day == switch_day:
            new_date = date_today + timedelta(days=7)
            update_rotating_work_type_assign(rotating_work_type, new_date)
    return


def work_type_rotate_every(rotating_work_type):
    """
    This method for rotate work type based on every month
    """
    date_today = datetime.now()
    switch_date = rotating_work_type.next_change_date
    day_date = rotating_work_type.rotate_every
    if switch_date.strftime("%Y-%m-%d") == date_today.strftime("%Y-%m-%d"):
        if day_date == switch_date.strftime("%d").lstrip("0"):
            new_date = date_today.replace(month=date_today.month + 1)
            update_rotating_work_type_assign(rotating_work_type, new_date)
        elif day_date == "last":
            year = date_today.strftime("%Y")
            month = date_today.strftime("%m")
            last_day = calendar.monthrange(int(year), int(month) + 1)[1]
            new_date = datetime(int(year), int(month) + 1, last_day)
            update_rotating_work_type_assign(rotating_work_type, new_date)
    return


def rotate_work_type():
    """
    This method will identify the based on condition to the rotating shift assign
    and redirect to the chunk method to execute.
    """
    from base.models import RotatingWorkTypeAssign

    rotating_work_types = RotatingWorkTypeAssign.objects.filter(is_active=True)
    for rotating_work_type in rotating_work_types:
        based_on = rotating_work_type.based_on
        if based_on == "after":
            work_type_rotate_after(rotating_work_type)
        elif based_on == "weekly":
            work_type_rotate_weekend(rotating_work_type)
        elif based_on == "monthly":
            work_type_rotate_every(rotating_work_type)
    return


def update_rotating_shift_assign(rotating_shift, new_date):
    """
    Here will update the employee work information and send notification
    """
    from horilla_auth.models import HorillaUser

    next_shift_index = 0
    employee = rotating_shift.employee_id
    employee_work_info = employee.employee_work_info
    rotating_shift_id = rotating_shift.rotating_shift_id
    shift1 = rotating_shift_id.shift1
    shift2 = rotating_shift_id.shift2
    additional_shifts = rotating_shift_id.additional_shifts()
    if additional_shifts is None:
        total_rotate_shifts = [shift1, shift2]
    else:
        total_rotate_shifts = [shift1, shift2] + list(additional_shifts)
    next_shift_index = rotating_shift.additional_data.get("next_shift_index")
    next_shift = total_rotate_shifts[next_shift_index]
    if next_shift_index < len(total_rotate_shifts) - 1:
        next_shift_index += 1
    else:
        next_shift_index = 0  # Wrap around to the beginning of the list
    rotating_shift.additional_data["next_shift_index"] = next_shift_index
    employee_work_info.shift_id = rotating_shift.next_shift
    employee_work_info.save()
    rotating_shift.next_change_date = new_date
    rotating_shift.current_shift = rotating_shift.next_shift
    rotating_shift.next_shift = next_shift
    rotating_shift.save()
    bot = HorillaUser.objects.filter(username="Horilla Bot").first()
    if bot is not None:
        employee = rotating_shift.employee_id
        notify.send(
            bot,
            recipient=employee.employee_user_id,
            verb="Your shift has been changed.",
            verb_ar="تم تغيير التحول الخاص بك.",
            verb_de="Ihre Schicht wurde geändert.",
            verb_es="Tu turno ha sido cambiado.",
            verb_fr="Votre quart de travail a été modifié.",
            icon="infinite",
            redirect=reverse("employee-profile"),
        )
    return


def shift_rotate_after_day(rotating_shift, today):
    """
    This method for rotate shift based on after day
    """
    switch_date = rotating_shift.next_change_date
    if switch_date == today:
        new_date = today + timedelta(days=rotating_shift.rotate_after_day)
        update_rotating_shift_assign(rotating_shift, new_date)
    return


def shift_rotate_weekend(rotating_shift, today):
    """
    This method for rotate shift based on weekend
    """
    switch_date = rotating_shift.next_change_date
    if switch_date == today:
        day = today.strftime("%A").lower()
        switch_day = rotating_shift.rotate_every_weekend
        if day == switch_day:
            new_date = today + timedelta(days=7)
            update_rotating_shift_assign(rotating_shift, new_date)
    return


def shift_rotate_every(rotating_shift, today):
    """
    This method for rotate shift based on every month
    """
    switch_date = rotating_shift.next_change_date
    day_date = rotating_shift.rotate_every
    if switch_date == today:
        if day_date == switch_date.strftime("%d").lstrip("0"):
            new_date = today.replace(month=today.month + 1)
            update_rotating_shift_assign(rotating_shift, new_date)
        elif day_date == "last":
            year = today.year
            month = today.month
            last_day = calendar.monthrange(int(year), int(month) + 1)[1]
            new_date = datetime(int(year), int(month) + 1, last_day)
            update_rotating_shift_assign(rotating_shift, new_date)
    return


def rotate_shift():
    """
    This method will identify the based on condition to the rotating shift assign
    and redirect to the chunk method to execute.
    """
    from base.models import RotatingShiftAssign

    rotating_shifts = RotatingShiftAssign.objects.filter(is_active=True)
    today = datetime.now().date()
    r_shifts = rotating_shifts.filter(start_date__lte=today)
    rotating_shifts_modified = None
    for r_shift in r_shifts:
        emp_shift = rotating_shifts.filter(
            employee_id=r_shift.employee_id, start_date__lte=today
        ).exclude(id=r_shift.id)
        rotating_shifts_modified = rotating_shifts.exclude(
            id__in=emp_shift.values_list("id", flat=True)
        )
        emp_shift.update(is_active=False)

    for rotating_shift in rotating_shifts_modified:
        based_on = rotating_shift.based_on
        # after day condition
        if based_on == "after":
            shift_rotate_after_day(rotating_shift, today)
        # weekly condition
        elif based_on == "weekly":
            shift_rotate_weekend(rotating_shift, today)
        # monthly condition
        elif based_on == "monthly":
            shift_rotate_every(rotating_shift, today)

    return


def switch_shift():
    """
    This method change employees shift information regards to the shift request
    """
    from base.models import ShiftRequest
    from horilla_auth.models import HorillaUser

    today = date.today()

    shift_requests = ShiftRequest.objects.filter(
        canceled=False, approved=True, requested_date__exact=today, shift_changed=False
    )
    if shift_requests:
        for request in shift_requests:
            work_info = request.employee_id.employee_work_info
            # updating requested shift to the employee work information.
            work_info.shift_id = request.shift_id
            work_info.save()
            request.approved = True
            request.shift_changed = True
            request.save()
            bot = HorillaUser.objects.filter(username="Horilla Bot").first()
            if bot is not None:
                employee = request.employee_id
                notify.send(
                    bot,
                    recipient=employee.employee_user_id,
                    verb="Shift Changes notification",
                    verb_ar="التحول تغيير الإخطار",
                    verb_de="Benachrichtigung über Schichtänderungen",
                    verb_es="Notificación de cambios de turno",
                    verb_fr="Notification des changements de quart de travail",
                    icon="refresh",
                    redirect=reverse("employee-profile"),
                )
    return


def undo_shift():
    """
    This method undo previous employees shift information regards to the shift request
    """
    from base.models import ShiftRequest
    from horilla_auth.models import HorillaUser

    today = date.today()
    # here will get all the active shift requests
    shift_requests = ShiftRequest.objects.filter(
        canceled=False,
        approved=True,
        requested_till__lt=today,
        is_active=True,
        shift_changed=True,
    )
    if shift_requests:
        for request in shift_requests:
            work_info = request.employee_id.employee_work_info
            work_info.shift_id = request.previous_shift_id
            work_info.save()
            # making the instance in-active
            request.is_active = False
            request.save()
            bot = HorillaUser.objects.filter(username="Horilla Bot").first()
            if bot is not None:
                employee = request.employee_id
                notify.send(
                    bot,
                    recipient=employee.employee_user_id,
                    verb="Shift changes notification, Requested date expired.",
                    verb_ar="التحول يغير الإخطار ، التاريخ المطلوب انتهت صلاحيته.",
                    verb_de="Benachrichtigung über Schichtänderungen, gewünschtes Datum abgelaufen.",
                    verb_es="Notificación de cambios de turno, Fecha solicitada vencida.",
                    verb_fr="Notification de changement d'équipe, la date demandée a expiré.",
                    icon="refresh",
                    redirect=reverse("employee-profile"),
                )
    return


def switch_work_type():
    """
    This method change employees work type information regards to the work type request
    """
    from base.models import WorkTypeRequest
    from horilla_auth.models import HorillaUser

    today = date.today()
    work_type_requests = WorkTypeRequest.objects.filter(
        canceled=False,
        approved=True,
        requested_date__exact=today,
        work_type_changed=False,
    )
    for request in work_type_requests:
        work_info = request.employee_id.employee_work_info
        # updating requested work type to the employee work information.
        work_info.work_type_id = request.work_type_id
        work_info.save()
        request.approved = True
        request.work_type_changed = True
        request.save()
        bot = HorillaUser.objects.filter(username="Horilla Bot").first()
        if bot is not None:
            employee = request.employee_id
            notify.send(
                bot,
                recipient=employee.employee_user_id,
                verb="Work Type Changes notification",
                verb_ar="إخطار تغييرات نوع العمل",
                verb_de="Benachrichtigung über Änderungen des Arbeitstyps",
                verb_es="Notificación de cambios de tipo de trabajo",
                verb_fr="Notification de changement de type de travail",
                icon="swap-horizontal",
                redirect=reverse("employee-profile"),
            )
    return


def undo_work_type():
    """
    This method undo previous employees work type information regards to the work type request
    """
    from base.models import WorkTypeRequest
    from horilla_auth.models import HorillaUser

    today = date.today()
    # here will get all the active work type requests
    work_type_requests = WorkTypeRequest.objects.filter(
        canceled=False,
        approved=True,
        requested_till__lt=today,
        is_active=True,
        work_type_changed=True,
    )
    for request in work_type_requests:
        work_info = request.employee_id.employee_work_info
        # updating employee work information's work type to previous work type
        work_info.work_type_id = request.previous_work_type_id
        work_info.save()
        # making the instance is in-active
        request.is_active = False
        request.save()
        bot = HorillaUser.objects.filter(username="Horilla Bot").first()
        if bot is not None:
            employee = request.employee_id
            notify.send(
                bot,
                recipient=employee.employee_user_id,
                verb="Work type changes notification, Requested date expired.",
                verb_ar="إعلام بتغيير نوع العمل ، انتهاء صلاحية التاريخ المطلوب.",
                verb_de="Benachrichtigung über Änderungen des Arbeitstyps, angefordertes Datum abgelaufen.",
                verb_es="Notificación de cambios de tipo de trabajo, fecha solicitada vencida.",
                verb_fr="Notification de changement de type de travail, la date demandée a expiré.",
                icon="swap-horizontal",
                redirect=reverse("employee-profile"),
            )
    return


def recurring_holiday():
    from .models import Holidays

    recurring_holidays = Holidays.objects.filter(recurring=True)
    today = datetime.now()
    # Looping through all recurring holiday
    for recurring_holiday in recurring_holidays:
        start_date = recurring_holiday.start_date
        end_date = recurring_holiday.end_date
        new_start_date = date(start_date.year + 1, start_date.month, start_date.day)
        new_end_date = date(end_date.year + 1, end_date.month, end_date.day)
        # Checking that end date is not none
        if end_date is None:
            # checking if that start date is day before today
            if start_date == (today - timedelta(days=1)).date():
                recurring_holiday.start_date = new_start_date
        elif end_date == (today - timedelta(days=1)).date():
            recurring_holiday.start_date = new_start_date
            recurring_holiday.end_date = new_end_date
        recurring_holiday.save()


def sync_roster_shifts():
    """
    Daily at 00:05 — sync published roster entries to employee work info.
    For each employee with a published non-off roster entry dated today,
    update their EmployeeWorkInformation.shift_id to match.
    """
    from base.models import Roster
    from employee.models import EmployeeWorkInformation

    today = date.today()
    entries = (
        Roster.objects.filter(date=today, is_published=True, is_off=False)
        .select_related("employee", "shift")
        .exclude(shift__isnull=True)
    )
    for entry in entries:
        try:
            work_info = EmployeeWorkInformation.objects.filter(
                employee_id=entry.employee
            ).first()
            if work_info and work_info.shift_id != entry.shift:
                work_info.shift_id = entry.shift
                work_info.save(update_fields=["shift_id"])
        except Exception:
            pass


# The job1..job6 ids are historical and deliberately preserved so existing
# jobstore rows are replaced rather than duplicated. Note job5/job6 are swapped
# relative to declaration order -- that is how they have always been persisted.
# These registrations were previously wrapped in bare `except: pass`, which made
# a failed registration indistinguishable from a working one.
register_job(rotate_shift, "interval", job_id="job1", hours=4)
register_job(rotate_work_type, "interval", job_id="job2", hours=4)
register_job(undo_shift, "interval", job_id="job3", hours=4)
register_job(switch_shift, "interval", job_id="job4", hours=4)
register_job(undo_work_type, "interval", job_id="job6", hours=4)
register_job(switch_work_type, "interval", job_id="job5", hours=4)
register_job(recurring_holiday, "interval", hours=4)
register_job(sync_roster_shifts, "interval", hours=4)
