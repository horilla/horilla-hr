import calendar
import datetime as dt
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from horilla.scheduling import register_job

today = datetime.now()


def recruitment_close():
    """
    Closes recruitment campaigns that have reached their end date.

    """
    from recruitment.models import Recruitment

    today_date = today.date()

    recruitments = Recruitment.objects.filter(closed=False)

    for rec in recruitments:
        if rec.end_date:
            if rec.end_date == today_date:
                rec.closed = True
                rec.is_published = False
                rec.save()


def candidate_convert():
    """
    Converts candidates to a "converted" state if they already exist as users.
    """
    from horilla_auth.models import HorillaUser
    from recruitment.models import Candidate

    mails = list(
        Candidate.objects.filter(is_active=True).values_list("email", flat=True)
    )
    existing_emails = list(
        HorillaUser.objects.filter(email__in=mails).values_list("email", flat=True)
    )
    Candidate.objects.filter(
        is_active=True,
        email__in=existing_emails,
        converted=False,
    ).update(converted=True)


register_job(candidate_convert, "interval", minutes=5)
register_job(recruitment_close, "interval", hours=1)
