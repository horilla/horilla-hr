"""
This page handles the cbv methods for Biometric app
"""

from typing import Any
from venv import logger

from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from zk import ZK

from biometric.filters import BiometricDeviceFilter
from biometric.forms import BiometricDeviceForm, BiometricDeviceSchedulerForm
from biometric.models import BiometricDevices
from biometric.views import (
    anviz_biometric_attendance_scheduler,
    cosec_biometric_attendance_scheduler,
    str_time_seconds,
    zk_biometric_attendance_scheduler,
)
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaCardView,
    HorillaFormView,
    HorillaNavView,
)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="biometric.view_biometricdevices"), name="dispatch"
)
class BiometricNavBar(HorillaNavView):
    """
    nav bar of the page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("biometric-card-view")
        if self.request.user.has_perm("biometric.add_biometricdevices"):
            self.create_attrs = f"""
                                data-toggle="oh-modal-toggle"
                                data-target="#genericModal"
                                hx-target="#genericModalBody"
                                hx-get="{reverse('biometric-device-add')}"
                                """
        self.actions = [
            {
                "action": _("Fetch Logs"),
                "attrs": f"""
                    hx-on:click="updateSelectedDevices()"
                    hx-get="{reverse('biometric-device-bulk-fetch-logs')}"
                    hx-include="#selectedDevicesContainer"
                    hx-trigger="click delay:1s"
                    hx-target="#BiometricDeviceTestFormTarget"
                    hx-request='{{"timeout": 60000}}'
                    data-toggle="oh-modal-toggle"
                    data-target="#BiometricDeviceTestModal"
                    style="cursor: pointer;"
                    """,
            },
        ]

    nav_title = _("Biometric Devices")
    filter_body_template = "cbv/biometric_filter.html"
    filter_instance = BiometricDeviceFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="biometric.view_biometricdevices"), name="dispatch"
)
class BiometricCardView(HorillaCardView):
    """
    card view of the page
    """

    model = BiometricDevices
    filter_class = BiometricDeviceFilter
    custom_empty_template = "biometric/empty_view_biometric.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("biometric-card-view")
        archive_confirm = _("Do you want to %(status)s this device?") % {
            "status": "{archive_status}",
        }
        delete_confirm = _("Do you want to delete this device?")

        self.actions = [
            {
                "action": _("Edit"),
                "attrs": """
                    class="oh-dropdown__link"
                    hx-get="{get_update_url}"
                    hx-target="#genericModalBody"
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    """,
            },
            {
                "action": _("Fetch Logs"),
                "attrs": """
                    hx-get="{get_fetch_url}"
                    class="oh-dropdown__link"
                    data-toggle="oh-modal-toggle"
                    data-target="#BiometricDeviceTestModal"
                    hx-target="#BiometricDeviceTestFormTarget"
                    """,
            },
            {
                "action": "archive_status",
                "attrs": f"""
                    hx-confirm="{archive_confirm}"
                    hx-post="{{get_archive_url}}"
                    class="oh-dropdown__link"
                    hx-target="#listContainer"
                    hx-swap="none"
                    hx-on-htmx-after-request="$('.reload-record').click()"
                    """,
            },
            {
                "action": _("Delete"),
                "attrs": f"""
                    hx-confirm="{delete_confirm}"
                    hx-post="{{get_delete_url}}"
                    class="oh-dropdown__link oh-dropdown__link--danger"
                    hx-target="#biometricDeviceList"
                    hx-swap="none"
                    hx-on-htmx-after-request="$('.reload-record').click()"
                    """,
            },
        ]

    details = {
        "title": "{name}",
        "subtitle": format_lazy(
            "{} : {} <br> {} <br> {} <br> {}",
            _("Device Type"),
            "{get_machine_type}",
            "{get_card_details}",
            "{render_live_capture_html}",
            "{render_actions_html}",
        ),
    }

    card_status_class = (
        "oh-kanban-card--biometric is_scheduler-{is_scheduler} is_live-{is_live}"
    )

    card_status_indications = [
        (
            "notconnected--dot",
            _("Not-Connected"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=hired]').val('false');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "sheduled--dot",
            _("Scheduled"),
            """
            onclick="$('#applyFilter').closest('form').find('[name=is_scheduler]').val('true');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "live--dot",
            _("Live Capture"),
            """
            onclick="$('#applyFilter').closest('form').find('[name=is_live]').val('true');
                $('#applyFilter').click();
            "
            """,
        ),
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        active = (
            True
            if self.request.GET.get("is_active", True)
            in ["unknown", "True", "true", True]
            else False
        )
        queryset = queryset.filter(is_active=active)
        return queryset


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="biometric.add_biometricdevices"), name="dispatch"
)
class BiometricFormView(HorillaFormView):
    """
    from view for create and update biometric devices
    """

    model = BiometricDevices
    form_class = BiometricDeviceForm
    template_name = "cbv/biometric_form.html"
    new_display_title = _("Add Biometric Device")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.form.instance.pk:
            self.form_class.verbose_name = _("Edit Biometric Devices")
        context["form"] = self.form
        return context

    def form_valid(self, form: BiometricDeviceForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Biometric device updated successfully.")
            else:
                message = _("Biometric device added successfully.")
            form.save()

            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="biometric.change_biometricdevices"), name="dispatch"
)
class BiometricSheduleForm(HorillaFormView):
    """
    form view for shedule biometric device
    """

    model = BiometricDevices
    form_class = BiometricDeviceSchedulerForm
    # new_display_title = _("Schedule Biometric Device..")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form.verbose_name = _("Schedule Biometric Device..")
            device = BiometricDevices.objects.get(id=self.form.instance.pk)
            self.form.fields["scheduler_duration"].initial = device.scheduler_duration

        return context

    def form_valid(self, form: BiometricDeviceSchedulerForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Biometric device updated successfully.")
                device = BiometricDevices.objects.get(id=self.form.instance.pk)

                if device.machine_type == "zk":
                    try:
                        port_no = device.port
                        machine_ip = device.machine_ip
                        conn = None
                        zk_device = ZK(
                            machine_ip,
                            port=port_no,
                            timeout=5,
                            password=0,
                            force_udp=False,
                            ommit_ping=False,
                        )
                        conn = zk_device.connect()
                        conn.test_voice(index=0)
                        duration = self.request.POST.get("scheduler_duration")
                        device = BiometricDevices.objects.get(id=self.form.instance.pk)
                        device.scheduler_duration = duration
                        device.is_scheduler = True
                        device.is_live = False
                        device.save()
                        scheduler = BackgroundScheduler()
                        scheduler.add_job(
                            lambda: zk_biometric_attendance_scheduler(device.id),
                            "interval",
                            seconds=str_time_seconds(device.scheduler_duration),
                        )
                        scheduler.start()
                        return HorillaRedirect(self.request)
                    except Exception as error:
                        logger.error(
                            "An error comes in biometric_device_schedule ", error
                        )
                        script = """
                        <script>
                            Swal.fire({
                            title : "Schedule Attendance unsuccessful",
                            text: "Please double-check the accuracy of the provided IP Address and Port Number for correctness",
                            icon: "warning",
                            showConfirmButton: false,
                            timer: 3500,
                            timerProgressBar: true,
                            didClose: () => {
                                location.reload();
                                },
                            });
                        </script>
                        """
                        return HttpResponse(script)
                elif device.machine_type == "anviz":
                    duration = self.request.POST.get("scheduler_duration")
                    device.is_scheduler = True
                    device.scheduler_duration = duration
                    device.save()
                    scheduler = BackgroundScheduler()
                    scheduler.add_job(
                        lambda: anviz_biometric_attendance_scheduler(device.id),
                        "interval",
                        seconds=str_time_seconds(device.scheduler_duration),
                    )
                    scheduler.start()
                    return HorillaRedirect(self.request)
                else:
                    duration = self.request.POST.get("scheduler_duration")
                    device.is_scheduler = True
                    device.is_live = False
                    device.scheduler_duration = duration
                    device.save()
                    scheduler = BackgroundScheduler()
                    existing_thread = settings.BIO_DEVICE_THREADS.get(device.id)
                    if existing_thread:
                        existing_thread.stop()
                        del settings.BIO_DEVICE_THREADS[device.id]
                    scheduler.add_job(
                        lambda: cosec_biometric_attendance_scheduler(device.id),
                        "interval",
                        seconds=str_time_seconds(device.scheduler_duration),
                    )
                    scheduler.start()
                    return HorillaRedirect(self.request)
            # else:
            #     message = _("Biometric device added successfully.")
            form.save()

            messages.success(self.request, message)
            # return self.HttpResponse("<script>location.reload();</script>")
        return super().form_valid(form)
