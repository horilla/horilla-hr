import logging
import os
from email.mime.image import MIMEImage
from threading import Thread

from django.contrib import messages
from django.contrib.staticfiles import finders
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from base.backends import ConfiguredEmailBackend

logger = logging.getLogger(__name__)


class LeaveMailSendThread(Thread):

    def __init__(self, request, leave_request, type):
        Thread.__init__(self)
        self.request = request
        self.leave_request = leave_request
        self.type = type
        self.host = request.get_host()
        self.protocol = "https" if request.is_secure() else "http"

    # def send_email(self, subject, content, recipients, leave_request_id="#"):
    #     email_backend = ConfiguredEmailBackend()
    #     display_email_name = email_backend.dynamic_from_email_with_display_name

    #     host = self.host
    #     protocol = self.protocol
    #     if leave_request_id != "#":
    #         link = int(leave_request_id)
    #     for recipient in recipients:
    #         if recipient:
    #             html_message = render_to_string(
    #                 "base/mail_templates/leave_request_template.html",
    #                 {
    #                     "link": link,
    #                     "instance": recipient,
    #                     "host": host,
    #                     "protocol": protocol,
    #                     "subject": subject,
    #                     "content": content,
    #                 },
    #                 request=self.request,
    #             )

    #             email = EmailMessage(
    #                 subject=subject,
    #                 body=html_message,
    #                 from_email=display_email_name,
    #                 to=[recipient.get_mail()],
    #                 reply_to=[display_email_name],
    #             )
    #             email.content_subtype = "html"
    #             try:
    #                 email.send()
    #             except:
    #                 messages.error(
    #                     self.request, f"Mail not sent to {recipient.get_full_name()}"
    #                 )

    def send_email(self, subject, content, recipients, leave_request_id="#"):
        email_backend = ConfiguredEmailBackend()
        display_email_name = email_backend.dynamic_from_email_with_display_name

        host = self.host
        protocol = self.protocol

        link = None
        if leave_request_id != "#":
            link = int(leave_request_id)

        for recipient in recipients:
            if not recipient or not recipient.get_mail():
                continue

            company = recipient.get_company()

            html_message = render_to_string(
                "base/mail_templates/leave_request_template.html",
                {
                    "link": link,
                    "instance": recipient,
                    "host": host,
                    "protocol": protocol,
                    "subject": subject,
                    "content": content,
                },
                request=self.request,
            )

            email = EmailMultiAlternatives(
                subject=subject,
                body=html_message,
                from_email=display_email_name,
                to=[recipient.get_mail()],
                reply_to=[display_email_name],
            )

            email.attach_alternative(html_message, "text/html")

            # Attach company logo inline, fall back to static Horilla logo if file missing
            if company and company.icon and os.path.exists(company.icon.path):
                image_path = company.icon.path
            else:
                image_path = finders.find("images/ui/horilla-sticker-round.png")

            if image_path:
                with open(image_path, "rb") as f:
                    logo = MIMEImage(f.read())
                    logo.add_header("Content-ID", "<company_logo>")
                    logo.add_header(
                        "Content-Disposition",
                        "inline",
                        filename=os.path.basename(image_path),
                    )
                    email.attach(logo)

            # Attach static leave icon inline if available
            leave_icon_path = finders.find("images/ui/leave_types.png")

            if leave_icon_path:
                with open(leave_icon_path, "rb") as f:
                    leave_icon = MIMEImage(f.read())
                    leave_icon.add_header("Content-ID", "<leave_icon>")
                    leave_icon.add_header(
                        "Content-Disposition",
                        "inline",
                        filename="leave_types.png",
                    )
                    email.attach(leave_icon)

            email.send()

    def run(self) -> None:
        super().run()
        if self.type == "request":
            owner = self.leave_request.employee_id
            reporting_manager = self.leave_request.employee_id.get_reporting_manager()

            content_manager = f"This is to inform you that a new leave request has been submitted by {owner}. Take the necessary actions for the leave request. Should you have any additional information or updates, please feel free to communicate directly with the {owner}."
            subject_manager = f"Leave request has been submitted by {owner}"

            self.send_email(
                subject_manager,
                content_manager,
                [reporting_manager],
                self.leave_request.id,
            )

            content_owner = f"This is to inform you that the leave request you created has been successfully logged into our system. The manager will now take the necessary actions to address leave request. Should you have any additional information or updates, please feel free to communicate directly with the {reporting_manager}."
            subject_owner = "Leave request created successfully"

            self.send_email(
                subject_owner, content_owner, [owner], self.leave_request.id
            )

        elif self.type == "approve":
            owner = self.leave_request.employee_id
            reporting_manager = self.leave_request.employee_id.get_reporting_manager()

            subject = "The Leave request has been successfully approved"
            content = f"This is to inform you that the leave request has been approved. If you have any questions or require further information, feel free to reach out to the {reporting_manager}."

            self.send_email(subject, content, [owner], self.leave_request.id)

        elif self.type == "reject":
            owner = self.leave_request.employee_id
            reporting_manager = self.leave_request.employee_id.get_reporting_manager()

            subject = "The Leave request has been rejected"
            content = f"This is to inform you that the leave request has been rejected. If you have any questions or require further information, feel free to reach out to the {reporting_manager}."

            self.send_email(subject, content, [owner], self.leave_request.id)

        elif self.type == "cancel":
            owner = self.leave_request.employee_id
            reporting_manager = self.leave_request.employee_id.get_reporting_manager()

            content_manager = f"This is to inform you that a leave request has been requested to cancel by {owner}. Take the necessary actions for the leave request. Should you have any additional information or updates, please feel free to communicate directly with the {owner}."
            subject_manager = f"Leave request cancellation"

            self.send_email(
                subject_manager,
                content_manager,
                [reporting_manager],
                self.leave_request.id,
            )

            content_owner = f"This is to inform you that a cancellation request created for your leave request has been successfully logged into our system. The manager will now take the necessary actions to address the leave request. Should you have any additional information or updates, please feel free to communicate directly with the {reporting_manager}."
            subject_owner = "Leave request cancellation requested"

            self.send_email(
                subject_owner, content_owner, [owner], self.leave_request.id
            )

        elif self.type in ("cancel_approve", "cancel_reject"):
            owner = self.leave_request.employee_id
            reporting_manager = owner.get_reporting_manager()
            outcome = "approved" if self.type == "cancel_approve" else "rejected"
            subject = f"The Leave cancellation request has been {outcome}"
            content = f"This is to inform you that your leave cancellation request has been {outcome}. If you have any questions or require further information, feel free to reach out to the {reporting_manager}."

            self.send_email(subject, content, [owner], self.leave_request.id)

        return


class LeaveClashThread(Thread):

    def __init__(self, leave_request):
        Thread.__init__(self)
        self.leave_request = leave_request

    def count_leave_clashes(self):
        from leave.models import LeaveRequest

        """
        Method to count leave clashes where this employee's leave request overlaps
        with other employees' requested dates.
        """
        overlapping_requests = LeaveRequest.objects.exclude(
            id=self.leave_request.id
        ).filter(
            Q(
                employee_id__employee_work_info__department_id=self.leave_request.employee_id.employee_work_info.department_id
            )
            | Q(
                employee_id__employee_work_info__job_position_id=self.leave_request.employee_id.employee_work_info.job_position_id
            ),
            start_date__lte=self.leave_request.end_date,
            end_date__gte=self.leave_request.start_date,
        )

        return overlapping_requests.count()

    def run(self) -> None:
        from leave.models import LeaveRequest

        super().run()
        dates = self.leave_request.requested_dates()
        leave_requests_to_update = LeaveRequest.objects.filter(
            Q(start_date__in=dates) | Q(end_date__in=dates)
        )

        for leave_request in leave_requests_to_update:
            leave_request.leave_clashes_count = self.count_leave_clashes()
            leave_request.save()
