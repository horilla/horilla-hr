from datetime import date, datetime, time, timedelta

from horilla.scheduling import register_job


def update_experience():
    from employee.models import EmployeeWorkInformation

    """
    This scheduled task to trigger the experience calculator
    to update the employee work experience
    """
    queryset = EmployeeWorkInformation.objects.filter(employee_id__is_active=True)
    for instance in queryset:
        instance.experience_calculator()
    return


def block_unblock_disciplinary():
    """
    Scheduled task to apply disciplinary actions and block/unblock employee accounts.
    """
    from base.models import EmployeeShiftSchedule
    from employee.models import DisciplinaryAction
    from horilla_auth.models import HorillaUser

    today = date.today()
    now = datetime.now().time()

    dis_actions = DisciplinaryAction.objects.select_related("action").prefetch_related(
        "employee_id"
    )

    for dis in dis_actions:
        if not dis.action.block_option:
            continue

        employees = dis.employee_id.exclude(employee_user_id__isnull=True)
        user_ids = list(employees.values_list("employee_user_id", flat=True))
        if not user_ids:
            continue

        if dis.action.action_type == "suspension":
            active = None

            if dis.days:
                start_date = dis.start_date
                end_date = start_date + timedelta(days=dis.days)
                if today >= end_date:
                    active = True
                elif today >= start_date:
                    active = False

            if dis.hours:
                if today != dis.start_date:
                    continue
                hour_str = dis.hours + ":00"
                hour_time = datetime.strptime(hour_str, "%H:%M:%S").time()

                for emp in employees:
                    if not emp.employee_work_info:
                        continue

                    shift = emp.employee_work_info.shift_id
                    shift_today = EmployeeShiftSchedule.objects.filter(
                        shift_id=shift, day__day=datetime.today().strftime("%A").lower()
                    ).first()
                    if not shift_today:
                        continue

                    st_time = shift_today.start_time
                    suspension_end_datetime = datetime.combine(
                        today, st_time
                    ) + timedelta(
                        hours=hour_time.hour,
                        minutes=hour_time.minute,
                        seconds=hour_time.second,
                    )
                    suspension_end_time = suspension_end_datetime.time()

                    if now >= suspension_end_time:
                        active = True
                    elif now >= st_time:
                        active = False

                    user = emp.employee_user_id
                    if user:
                        user.is_active = active
                        user.save()

            if dis.days and active is not None:
                HorillaUser.objects.filter(id__in=user_ids).update(is_active=active)

        elif dis.action.action_type == "dismissal":
            if today >= dis.start_date:
                active = False
                HorillaUser.objects.filter(id__in=user_ids).update(is_active=active)


register_job(update_experience, "interval", hours=4)
register_job(block_unblock_disciplinary, "interval", seconds=60)
