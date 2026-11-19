"""
threading.py

This module is used handle mail sent in thread
"""

import logging
from threading import Thread

from django.contrib import messages
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from base.backends import ConfiguredEmailBackend
from base.models import Department
from employee.models import EmployeeWorkInformation
from helpdesk.models import Ticket

logger = logging.getLogger(__name__)


class TicketSendThread(Thread):
    """
    MailSend
    """

    def __init__(self, request, ticket, type):
        Thread.__init__(self)
        self.ticket = ticket
        self.type = type
        self.request = request
        self.assignees = ticket.assigned_to.all()
        self.host = request.get_host()
        self.protocol = "https" if request.is_secure() else "http"
        raised_on = ticket.get_raised_on_object()
        self.department_manager = None
        if isinstance(raised_on, Department):
            if raised_on.dept_manager.all():
                self.department_manager = raised_on.dept_manager.all().first().manager

    def send_email(self, subject, content, recipients, ticket_id="#"):
        host = self.host
        protocol = self.protocol
        link = "#"
        email_backend = ConfiguredEmailBackend()

        display_email_name = email_backend.dynamic_from_email_with_display_name
        if self.request:
            try:
                sender = self.request.user.employee_get
                if sender.email:
                    display_email_name = f"{sender.get_full_name()} <{sender.email}>"
            except:
                logger.error(Exception)

        if ticket_id != "#":
            link = f"{protocol}://{host}/helpdesk/ticket-detail/{ticket_id}/"
        for recipient in recipients:
            if not recipient.get_mail():
                continue
            html_message = render_to_string(
                "helpdesk/mail_templates/ticket_mail.html",
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

            email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=display_email_name,
                to=[recipient.get_mail()],
                reply_to=[display_email_name],
            )
            email.content_subtype = "html"
            try:
                email.send()
            except:
                messages.error(
                    self.request,
                    _("Mail not sent to %(employee)s")
                    % {"employee": recipient.get_full_name()},
                )

    def run(self) -> None:
        super().run()

        if self.type == "create":
            owner = self.ticket.employee_id
            manager = self.department_manager

            if manager:
                content_manager = f"This is to inform you that a ticket has been raised on your department. Take the necessary actions to address the issue or request outlined in the ticket. Should you have any additional information or updates, please feel free to communicate directly with the {owner}."
                subject_manager = "Ticket created raised on your department"

                self.send_email(
                    subject_manager, content_manager, [manager], self.ticket.id
                )

            content_owner = "This is to inform you that the ticket you created has been successfully logged into our system. The assigned team/individual will now take the necessary actions to address the issue or request outlined in the ticket. Should you have any additional information or updates, please feel free to communicate directly with the Support/Helpdesk team."
            subject_owner = "Ticket created successfully"

            self.send_email(subject_owner, content_owner, [owner], self.ticket.id)

        elif self.type == "status_change":
            assignees = set(self.assignees or [])
            owner = self.ticket.employee_id
            manager = self.department_manager
            recipients = assignees | {x for x in [owner, manager] if x}

            tracking = self.ticket.tracking()
            updated_by = tracking[0]["updated_by"]
            new_status = tracking[0]["changes"][0]["new"]
            old_status = tracking[0]["changes"][0]["old"]

            subject = "The Status of the Ticket has been updated"
            content = f"This is to inform you that the status of the following ticket has been updated by {updated_by} from {old_status} to {new_status}. If you have any questions or require further information, feel free to reach out to the Support/Helpdesk team."

            self.send_email(subject, content, recipients, self.ticket.id)

        elif self.type == "delete":
            assignees = set(self.assignees or [])
            owner = self.ticket.employee_id
            manager = self.department_manager
            recipients = assignees | {x for x in [owner, manager] if x}

            subject = "The Ticket has been deleted"
            content = f'This is to inform you that the Ticket "{self.ticket.title}" has been deleted. If you have any questions or require further information, feel free to reach out to the Support/Helpdesk team.'

            self.send_email(subject, content, recipients)

        return


class AddAssigneeThread(Thread):
    """
    MailSend
    """

    def __init__(self, request, ticket, recipient):
        Thread.__init__(self)
        self.ticket = ticket
        self.recipients = recipient
        self.request = request
        self.host = request.get_host()
        self.protocol = "https" if request.is_secure() else "http"

    def run(self) -> None:
        super().run()

        content = "Please review the ticket details and take appropriate action accordingly. If you have any questions or require further information, feel free to reach out to the owner or the Support/Helpdesk team."
        subject = "You have been assigned to a Ticket"

        host = self.host
        protocol = self.protocol
        email_backend = ConfiguredEmailBackend()
        display_email_name = email_backend.dynamic_from_email_with_display_name
        if self.request:
            try:
                sender = self.request.user.employee_get
                if sender.email:
                    display_email_name = f"{sender.get_full_name()} <{sender.email}>"
            except:
                pass
        link = f"{protocol}://{host}/helpdesk/ticket-detail/{self.ticket.id}/"
        for recipient in self.recipients:
            if not recipient.get_mail():
                continue
            html_message = render_to_string(
                "helpdesk/mail_templates/ticket_mail.html",
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

            email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=display_email_name,
                to=[recipient.get_mail()],
                reply_to=[display_email_name],
            )
            email.content_subtype = "html"
            try:
                email.send()
            except:
                messages.error(
                    self.request,
                    _("Mail not sent to %(employee)s")
                    % {"employee": recipient.get_full_name()},
                )


class RemoveAssigneeThread(Thread):
    """
    MailSend
    """

    def __init__(self, request, ticket, recipient):
        Thread.__init__(self)
        self.ticket = ticket
        self.recipients = recipient
        self.request = request
        self.host = request.get_host()
        self.protocol = "https" if request.is_secure() else "http"

    def run(self) -> None:
        super().run()

        content = "Please review the ticket details and take appropriate action accordingly. If you have any questions or require further information, feel free to reach out to the owner or the Support/Helpdesk team."
        subject = "You have been removed from a Ticket"
        email_backend = ConfiguredEmailBackend()

        display_email_name = email_backend.dynamic_from_email_with_display_name
        if self.request:
            try:
                sender = self.request.user.employee_get
                if sender.email:
                    display_email_name = f"{sender.get_full_name()} <{sender.email}>"
            except:
                pass
        host = self.host
        protocol = self.protocol
        link = f"{protocol}://{host}/helpdesk/ticket-detail/{self.ticket.id}/"
        for recipient in self.recipients:
            if not recipient.get_mail():
                continue
            html_message = render_to_string(
                "helpdesk/mail_templates/ticket_mail.html",
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

            email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=display_email_name,
                to=[recipient.get_mail()],
                reply_to=[display_email_name],
            )
            email.content_subtype = "html"
            try:
                email.send()
            except:
                messages.error(
                    self.request,
                    _("Mail not sent to %(employee)s")
                    % {"employee": recipient.get_full_name()},
                )
