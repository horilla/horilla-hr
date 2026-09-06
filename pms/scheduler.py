from datetime import datetime, timedelta

from apscheduler.triggers.cron import CronTrigger

from horilla.scheduling import register_job
from notifications.signals import notify


def cyclic_feedback_creation():
    from pms.models import Feedback

    feedbacks = Feedback.objects.filter(cyclic_next_start_date=datetime.today().date())
    for feedback in feedbacks:
        if feedback.cyclic_feedback:
            feedback_obj = Feedback()
            for field in feedback._meta.fields:
                if field.name not in [
                    "id",
                    "cyclic_next_start_date",
                    "cyclic_next_end_date",
                ]:
                    setattr(feedback_obj, field.name, getattr(feedback, field.name))
            title = (
                f"{feedback_obj.review_cycle.split('- cyclic')[0]} - cyclic {feedback_obj.start_date}"
                if "- cyclic" in feedback_obj.review_cycle
                else f"{feedback_obj.review_cycle} - cyclic {feedback_obj.start_date}"
            )
            feedback_obj.review_cycle = title
            feedback_obj.status = "Not Started"
            feedback_obj.start_date = feedback.cyclic_next_start_date
            feedback_obj.end_date = feedback.cyclic_next_end_date
            feedback_obj.save()

            feedback.cyclic_feedback = False
            feedback.save()

    return


cron_trigger = CronTrigger(hour=8)
grace_time_seconds = int(timedelta(days=1).total_seconds())
register_job(
    cyclic_feedback_creation, cron_trigger, misfire_grace_time=grace_time_seconds
)
