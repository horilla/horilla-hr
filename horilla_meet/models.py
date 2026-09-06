from datetime import timedelta
from itertools import chain

from django.apps import apps
from django.db import models
from django.db.models import Q
from django.forms import ValidationError
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from google.oauth2.credentials import Credentials

from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company
from employee.models import Employee
from horilla.horilla_middlewares import _thread_locals
from horilla.models import HorillaModel, NoPermissionModel
from horilla_views.cbv_methods import render_template
from recruitment.models import Candidate


# Create your models here.
class GoogleCloudCredential(models.Model):
    """
    Model representing Google Cloud credentials associated with a specific company.
    Stores the client ID, client secret, redirect URIs, and the project ID for each set of credentials.
    """

    project_id = models.CharField(max_length=255, blank=True, null=True)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    redirect_uris = models.TextField(help_text=_("Comma separated URIs"))
    company_id = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Company",
    )
    objects = HorillaCompanyManager("company_id")

    @property
    def redirect_uri_list(self):
        """
        Property that returns a list of redirect URIs by splitting the
        comma-separated string in the `redirect_uris` field and stripping
        any surrounding whitespace from each URI.

        Returns:
            list: A list of redirect URIs (strings).
        """
        url_list = [uri.strip() for uri in self.redirect_uris.split(",")]
        return url_list

    def get_update_url(self):
        """
        Returns the URL for updating the Google Cloud credentials instance.

        Returns:
            str: The URL for updating the credentials instance.
        """
        return reverse_lazy("update-gmeet-credentials", kwargs={"pk": self.pk})

    def get_delete_url(self):
        """
        Returns the URL for deleting the Google Cloud credentials instance.

        Returns:
            str: The URL for deleting the credentials instance.
        """
        return reverse_lazy("delete-gmeet-credentials", kwargs={"obj_id": self.pk})

    def get_instance_id(self):
        """
        Returns the unique identifier (primary key) of the GoogleCloudCredential instance.

        Returns:
            int: The primary key (ID) of the credential instance.
        """
        return self.pk

    def get_client_id_col(self):
        """
        Returns an HTML snippet that hides the actual client ID value and displays
        a placeholder (masked version) for the client ID in a UI table column.

        Returns:
            str: An HTML string to represent a masked client ID.
        """
        col = f"""
        <span class="oh-hidden-item" data-value={self.client_id}>********************</span>
        """
        return col

    def get_client_secret_col(self):
        """
        Returns an HTML snippet that hides the actual client secret value and displays
        a placeholder (masked version) for the client secret in a UI table column.

        Returns:
            str: An HTML string to represent a masked client secret.
        """
        col = f"""
        <span class="oh-hidden-item" data-value={self.client_secret}>********************</span>
        """
        return col

    def get_redirect_url(self):
        """
        Returns an HTML snippet that returns the redirect urls as the points

        Returns:
            str: An HTML string to represent the redirect url list.
        """
        url_list = self.redirect_uri_list

        col = "<br /> <br />".join(f"{url}" for url in url_list)

        return col

    class Meta:
        """
        Metadata for the GoogleCloudCredential model.
        Defines the verbose name for display and sets a unique constraint
        on the combination of `project_id` and `company_id`.
        """

        verbose_name = "Google Cloud Credential"
        verbose_name_plural = "Google Cloud Credentials"
        unique_together = ["project_id", "company_id"]


class GoogleCredential(HorillaModel, NoPermissionModel):
    """
    Model representing Google credentials for an employee, including
    token information, client ID, client secret, scopes, and expiration time.
    """

    employee_id = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name="google_credential"
    )
    token = models.TextField()
    refresh_token = models.TextField()
    token_uri = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    scopes = models.TextField()
    expires_at = models.DateTimeField()

    def to_google_credentials(self):
        """
        Converts the GoogleCredential model instance into a Google `Credentials` object.

        This method is useful for using the stored credentials to authenticate
        requests to Google APIs.

        Returns:
            Credentials: A `Credentials` object populated with the data
            from the model instance.
        """
        return Credentials(
            token=self.token,
            refresh_token=self.refresh_token,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes.split(","),
            expiry=self.expires_at,
        )

    @classmethod
    def from_google_credentials(cls, employee, credentials):
        """
        Creates or updates a GoogleCredential instance from a Google `Credentials` object.

        This method is typically used to persist or refresh the credentials
        of an employee by extracting the relevant information from a `Credentials`
        object and storing it in the database.

        Args:
            employee (Employee): The employee to associate with the credentials.
            credentials (Credentials): A Google `Credentials` object containing the
            token, refresh_token, client_id, client_secret, and other related fields.

        """
        cls.objects.update_or_create(
            employee_id=employee,
            defaults={
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": ",".join(credentials.scopes),
                "expires_at": credentials.expiry,
            },
        )

    def __str__(self):
        """
        Returns a string representation of the GoogleCredential instance,
        typically used for displaying the object in the admin interface or logs.

        Returns:
            str: A string that represents the GoogleCredential instance with
            the associated employee's ID.
        """
        return f"Google credential - {self.employee_id}"


class GoogleMeeting(HorillaModel):
    """
    Model representing a Google meeting scheduled by an employee.
    Stores information about the meeting's title, description, start time,
    duration, attendees, and related event data.

    The model also includes methods for generating URLs for update/delete operations
    and handling attendees, as well as calculating the meeting's end time.
    """

    employee_id = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="meetings"
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    start_time = models.DateTimeField()
    meet_url = models.URLField()
    event_id = models.CharField(max_length=255, null=True)
    duration = models.PositiveIntegerField(
        default=60, help_text=_("Duration in minutes")
    )
    attendees = models.JSONField(default=list, blank=True, null=True)

    class Meta:
        """
        Metadata for GoogleMeeting model.
        Orders meetings by start time in descending order and creates indexes
        on `employee_id` and `start_time`, as well as `event_id` for optimized queries.
        """

        ordering = ["-start_time"]
        indexes = [
            models.Index(fields=["employee_id", "start_time"]),
            models.Index(fields=["event_id"]),
        ]

    def __str__(self):
        """
        Returns a string representation of the GoogleMeeting instance, typically used
        for displaying the meeting's title and formatted start time in the admin interface or logs.

        Returns:
            str: A string combining the meeting's title and start time in 'YYYY-MM-DD HH:MM' format.
        """
        return f"{self.title} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"

    @property
    def end_time(self):
        """
        Calculates the end time of the meeting based on its start time and duration.

        The end time is computed by adding the meeting's duration (in minutes) to the start time.

        Returns:
            datetime: The calculated end time of the meeting.
        """
        return self.start_time + timedelta(minutes=self.duration)

    def start_time_str(self):
        """
        Provides a custom HTML representation of the meeting's start time,
        splitting the date and time into separate spans for easier styling or manipulation.

        Returns:
            str: HTML string containing the start date and time in separate spans.
        """
        start_time = timezone.localtime(self.start_time)

        col = f"""
            <span class="oh-hidden-item dateformat_changer" >{start_time.date()}</span>,
            <span class="oh-hidden-item timeformat_changer" >{start_time.time()}</span>
        """
        return col

    def get_title_column(self):
        """
        Generates a custom HTML representation of the meeting's title column.
        This includes a button for collapsing/expanding the section and displays the title of the meeting.
        The method separates the date and time into different spans to allow easier styling or manipulation if required.

        The HTML output includes:
        - A button to toggle between collapsed and expanded states (using `ion-icon` for the up/down chevron).
        - The title of the meeting, displayed inside a span with the class `oh-permission-table__user`.

        Returns:
            str: An HTML string representing the meeting's title column with collapse functionality.
        """

        col = f"""
            <div class="oh-permission-table--toggle" onclick="event.stopPropagation()"
                >
                <div class="d-flex align-items-center">
                    <button class="oh-permission-table__collapse me-2">
                        <span title="Reveal"><ion-icon class="oh-permission-table__collapse-down" name="chevron-down-outline"></ion-icon></span>
                        <span title="Collapse"><ion-icon class="oh-permission-table__collapse-up" name="chevron-up-outline"></ion-icon></span>
                    </button>
                    <span class="oh-permission-table__user">{self.title}</span>
                </div>
            </div>
        """
        return col

    def get_attendees(self):

        employees = Employee.objects.filter(
            Q(employee_work_info__email__in=self.attendees)
            | Q(email__in=self.attendees)
        )
        candidates = Candidate.objects.filter(email__in=self.attendees)

        return list(chain(employees, candidates))

    def get_attendees_column(self):
        """
        Returns a custom HTML representation of the meeting's attendees column by rendering a template.

        This is used to display attendees in a specific format or style on a web page.

        Returns:
            str: Rendered HTML for displaying the attendees.
        """

        return render_template(
            path="gmeet/attendees_custom_column.html",
            context={"instance": self},
        )

    def get_update_url(self):
        """
        Returns the URL for updating the GoogleMeeting instance.

        The URL is dynamically generated to include the primary key of the meeting instance.

        Returns:
            str: The URL to update the meeting.
        """
        return reverse_lazy("update-gmeet", kwargs={"pk": self.pk})

    def get_delete_url(self):
        """
        Returns the URL for deleting the GoogleMeeting instance.

        The URL is a generic delete view, allowing for the deletion of the meeting instance.

        Returns:
            str: The URL to delete the meeting.
        """
        url = reverse_lazy("delete-google-meet", kwargs={"id": self.pk})
        return url

    def detailed_url(self):
        return reverse_lazy("gmeet-detail-view", kwargs={"pk": self.pk})

    def save(self, *args, **kwargs):
        """
        Saves the GoogleMeeting instance to the database.

        Before saving, checks if the `event_id` already exists in the database for another meeting.
        If so, raises a validation error to prevent duplicate meetings with the same event.

        Args:
            *args: Additional positional arguments passed to the parent save method.
            **kwargs: Additional keyword arguments passed to the parent save method.

        Raises:
            ValidationError: If a meeting with the same `event_id` already exists.
        """
        request = getattr(_thread_locals, "request")
        self.employee_id = request.user.employee_get

        if (
            not self.pk
            and self.event_id
            and GoogleMeeting.objects.filter(event_id=self.event_id).exists()
        ):
            raise ValidationError(_("Meeting with this Event already exists"))
        super().save(*args, **kwargs)


if apps.is_installed("recruitment"):
    from recruitment.models import InterviewSchedule

    class InterviewMeetingLink(models.Model, NoPermissionModel):
        interview = models.OneToOneField(
            InterviewSchedule,
            on_delete=models.CASCADE,
            related_name="google_interviews",
        )
        meeting = models.OneToOneField(GoogleMeeting, on_delete=models.CASCADE)


if apps.is_installed("pms"):
    from pms.models import Meetings

    class PmsMeetingLink(models.Model, NoPermissionModel):
        meeting = models.OneToOneField(
            Meetings, on_delete=models.CASCADE, related_name="google_meeting"
        )
        google_meeting = models.OneToOneField(GoogleMeeting, on_delete=models.CASCADE)
