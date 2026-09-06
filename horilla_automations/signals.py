"""
horilla_automation/signals.py

"""

import copy
import logging
import threading
import types

from bs4 import BeautifulSoup
from django import template
from django.core.mail import EmailMessage
from django.db import models, transaction
from django.db.models.query import QuerySet
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from base.methods import build_safe_template_request, sanitize_mail_template_body
from horilla.horilla_middlewares import _thread_locals
from horilla.models import has_xss
from horilla.signals import post_bulk_update, pre_bulk_update
from notifications.signals import notify

logger = logging.getLogger(__name__)


@classmethod
def from_list(cls, object_list):
    # Create a queryset-like object from the list
    queryset_like_object = cls(model=object_list[0].__class__)
    queryset_like_object._result_cache = list(object_list)
    queryset_like_object._prefetch_related_lookups = ()
    return queryset_like_object


setattr(QuerySet, "from_list", from_list)

SIGNAL_HANDLERS = []
INSTANCE_HANDLERS = []
REFRESH_METHODS = {}


def start_automation():
    """
    Automation signals
    """
    from base.models import HorillaMailTemplate
    from horilla_automations.methods.methods import get_model_class, split_query_string
    from horilla_automations.models import MailAutomation

    @receiver(post_delete, sender=MailAutomation)
    @receiver(post_save, sender=MailAutomation)
    def automation_signal(sender, instance, **kwargs):
        """
        signal method to handle automation post save
        """
        start_connection()
        track_previous_instance()

    @receiver(post_delete, sender=HorillaMailTemplate)
    @receiver(post_save, sender=HorillaMailTemplate)
    def template_signal(sender, instance, **kwargs):
        """
        signal method to handle automation post save
        """
        start_connection()
        track_previous_instance()

    def clear_connection():
        """
        Method to clear signals handlers
        """
        for handler in SIGNAL_HANDLERS:
            post_save.disconnect(handler, sender=handler.model_class)
            post_bulk_update.disconnect(handler, sender=handler.model_class)
        SIGNAL_HANDLERS.clear()

    REFRESH_METHODS["clear_connection"] = clear_connection

    def create_post_bulk_update_handler(automation, model_class, query_strings):
        def post_bulk_update_handler(sender, queryset, *args, **kwargs):
            def _bulk_update_thread_handler(
                queryset, previous_queryset_copy, automation
            ):
                request = getattr(queryset, "request", None)

                if request:
                    for index, instance in enumerate(queryset):
                        previous_instance = previous_queryset_copy[index]
                        send_automated_mail(
                            request,
                            False,
                            automation,
                            query_strings,
                            instance,
                            previous_instance,
                        )

            previous_bulk_record = getattr(_thread_locals, "previous_bulk_record", None)
            previous_queryset_copy = []
            if previous_bulk_record:
                previous_queryset = previous_bulk_record.get("queryset", None)
                previous_queryset_copy = previous_bulk_record.get("queryset_copy", [])

            # Deferred for the same reason as the post_save handler above:
            # the thread reads the rows back on its own connection.
            transaction.on_commit(
                lambda: threading.Thread(
                    target=_bulk_update_thread_handler,
                    args=(queryset, previous_queryset_copy, automation),
                ).start()
            )

        func_name = f"{automation.method_title}_post_bulk_signal_handler"

        # Dynamically create a function with a unique name
        handler = types.FunctionType(
            post_bulk_update_handler.__code__,
            globals(),
            name=func_name,
            argdefs=post_bulk_update_handler.__defaults__,
            closure=post_bulk_update_handler.__closure__,
        )

        # Set additional attributes on the function
        handler.model_class = model_class
        handler.automation = automation

        return handler

    def start_connection():
        """
        Method to start signal connection accordingly to the automation
        """
        clear_connection()
        automations = MailAutomation.objects.filter(is_active=True)
        for automation in automations:

            condition_querystring = automation.condition_querystring.replace(
                "automation_multiple_", ""
            )

            query_strings = split_query_string(condition_querystring)

            model_path = automation.model
            model_class = get_model_class(model_path)

            handler = create_post_bulk_update_handler(
                automation, model_class, query_strings
            )
            SIGNAL_HANDLERS.append(handler)

            post_bulk_update.connect(handler, sender=model_class)

            def create_signal_handler(name, automation, query_strings, model_class):
                def signal_handler(sender, instance, created, **kwargs):
                    """
                    Signal handler for post-save events of the model instances.
                    """
                    request = getattr(_thread_locals, "request", None)
                    previous_record = getattr(_thread_locals, "previous_record", None)
                    previous_instance = None
                    if previous_record:
                        previous_instance = previous_record["instance"]

                    args = (
                        request,
                        created,
                        automation,
                        query_strings,
                        instance,
                        previous_instance,
                    )
                    # Deferred to on_commit rather than started here: the
                    # thread gets its own DB connection, so if this save is
                    # inside an open transaction (fixture loads and the demo
                    # data backfills wrap large batches in transaction.atomic)
                    # the row is not visible to it yet and send_mail's
                    # re-read raises DoesNotExist. on_commit runs the thread
                    # once the row is durable, and never runs at all if the
                    # transaction rolls back -- which is also correct, since
                    # a mail should not go out for a save that was undone.
                    # Outside a transaction on_commit runs immediately.
                    transaction.on_commit(
                        lambda: threading.Thread(
                            target=lambda: send_automated_mail(*args),
                        ).start()
                    )

                signal_handler.__name__ = name
                signal_handler.model_class = model_class
                signal_handler.automation = automation
                return signal_handler

            # Create and connect the signal handler
            handler_name = f"{automation.method_title}_signal_handler"
            # model_class is passed in rather than read from the enclosing
            # loop: the handler outlives the iteration, so a closure over the
            # loop variable would make every handler use the last model.
            dynamic_signal_handler = create_signal_handler(
                handler_name, automation, query_strings, model_class
            )
            SIGNAL_HANDLERS.append(dynamic_signal_handler)
            post_save.connect(
                dynamic_signal_handler, sender=dynamic_signal_handler.model_class
            )

    REFRESH_METHODS["start_connection"] = start_connection

    def create_pre_bulk_update_handler(automation, model_class):
        def pre_bulk_update_handler(sender, queryset, *args, **kwargs):
            request = getattr(_thread_locals, "request", None)
            if request:
                queryset_copy = queryset.none()
                if queryset.count():
                    queryset_copy = QuerySet.from_list(copy.deepcopy(list(queryset)))
                _thread_locals.previous_bulk_record = {
                    "automation": automation,
                    "queryset": queryset,
                    "queryset_copy": queryset_copy,
                }

        func_name = f"{automation.method_title}_pre_bulk_signal_handler"

        # Dynamically create a function with a unique name
        handler = types.FunctionType(
            pre_bulk_update_handler.__code__,
            globals(),
            name=func_name,
            argdefs=pre_bulk_update_handler.__defaults__,
            closure=pre_bulk_update_handler.__closure__,
        )

        # Set additional attributes on the function
        handler.model_class = model_class
        handler.automation = automation

        return handler

    def track_previous_instance():
        """
        method to add signal to track the automations model previous instances
        """

        def clear_instance_signal_connection():
            """
            Method to clear instance handler signals
            """
            for handler in INSTANCE_HANDLERS:
                pre_save.disconnect(handler, sender=handler.model_class)
                pre_bulk_update.disconnect(handler, sender=handler.model_class)
            INSTANCE_HANDLERS.clear()

        clear_instance_signal_connection()
        automations = MailAutomation.objects.filter(is_active=True)
        for automation in automations:
            model_class = get_model_class(automation.model)

            handler = create_pre_bulk_update_handler(automation, model_class)
            INSTANCE_HANDLERS.append(handler)
            pre_bulk_update.connect(handler, sender=model_class)

            # _model/_automation are bound as defaults rather than read from
            # the enclosing loop: the handler stays connected after the loop
            # ends, so a closure would make every handler use the last
            # iteration's values. Django only passes sender/instance/**kwargs.
            @receiver(pre_save, sender=model_class)
            def instance_handler(
                sender, instance, _model=model_class, _automation=automation, **kwargs
            ):
                """
                Signal handler for pres-save events of the model instances.
                """
                # prevented storing the scheduled activities
                request = getattr(_thread_locals, "request", None)
                if instance.pk:
                    # to get the previous instance
                    instance = _model.objects.filter(id=instance.pk).first()
                if request:
                    _thread_locals.previous_record = {
                        "automation": _automation,
                        "instance": instance,
                    }

            instance_handler.__name__ = f"{automation.method_title}_instance_handler"
            instance_handler.model_class = model_class
            instance_handler.automation = automation

            INSTANCE_HANDLERS.append(instance_handler)

    track_previous_instance()
    start_connection()


def send_automated_mail(
    request,
    created,
    automation,
    query_strings,
    instance,
    previous_instance,
):
    from horilla_automations.methods.methods import evaluate_condition, operator_map
    from horilla_views.templatetags.generic_template_filters import getattribute

    applicable = False
    and_exists = False
    false_exists = False
    instance_values = []
    previous_instance_values = []
    for condition in query_strings:
        if condition.getlist("condition"):
            attr = condition.getlist("condition")[0]
            operator = condition.getlist("condition")[1]
            value = condition.getlist("condition")[2]

            if value == "on":
                value = True
            elif value == "off":
                value = False
            instance_value = getattribute(instance, attr)
            previous_instance_value = getattribute(previous_instance, attr)
            # The send mail method only trigger when actually any changes
            # b/w the previous, current instance's `attr` field's values and
            # if applicable for the automation
            if getattr(instance_value, "pk", None) and isinstance(
                instance_value, models.Model
            ):
                instance_value = str(getattr(instance_value, "pk", None))
                previous_instance_value = str(
                    getattr(previous_instance_value, "pk", None)
                )
            elif isinstance(instance_value, QuerySet):
                instance_value = list(instance_value.values_list("pk", flat=True))
                previous_instance_value = list(
                    previous_instance_value.values_list("pk", flat=True)
                )

            instance_values.append(instance_value)

            previous_instance_values.append(previous_instance_value)

            if not condition.get("logic"):

                applicable = evaluate_condition(instance_value, operator, value)
            logic = condition.get("logic")
            if logic:
                applicable = operator_map[logic](
                    applicable,
                    evaluate_condition(instance_value, operator, value),
                )
            if not applicable:
                false_exists = True
            if logic == "and":
                and_exists = True
            if false_exists and and_exists:
                applicable = False
                break
    if applicable:
        if created and automation.trigger == "on_create":
            send_mail(request, automation, instance)
        elif (automation.trigger == "on_update") and (
            set(previous_instance_values) != set(instance_values)
        ):

            send_mail(request, automation, instance)


def send_mail(request, automation, instance):
    """
    mail sending method
    """
    from base.backends import ConfiguredEmailBackend
    from base.methods import eval_validate, generate_pdf
    from employee.models import Employee
    from horilla_automations.methods.methods import (
        get_model_class,
        get_related_field_model,
    )
    from horilla_views.templatetags.generic_template_filters import getattribute

    mail_template = automation.mail_template
    employees = []
    to_emails = []

    if instance.pk:
        # Re-read so m2m fields are populated -- they are not yet attached on
        # the instance the post_save signal hands over.
        #
        # filter().first() rather than get(): the row can legitimately be
        # gone by the time this runs, because the caller is a thread with its
        # own DB connection. A row created and then deleted inside the same
        # transaction, or an object deleted between the save and this read,
        # both land here. get() raised DoesNotExist into a bare thread, which
        # printed a traceback nobody could act on and sent no mail either
        # way; returning quietly has the same effect without the noise.
        refreshed = instance._meta.model.objects.filter(pk=instance.pk).first()
        if refreshed is None:
            logger.debug(
                "Skipping automation %s: %s pk=%s no longer exists",
                automation.method_title,
                instance._meta.label,
                instance.pk,
            )
            return
        instance = refreshed

    pk_or_text = getattribute(instance, automation.mail_details)
    model_class = get_model_class(automation.model)
    model_class = get_related_field_model(model_class, automation.mail_details)
    context_instance = None
    if isinstance(pk_or_text, int):
        context_instance = model_class.objects.filter(pk=pk_or_text).first()

    for mapping in eval_validate(automation.mail_to):
        result = getattribute(instance, mapping)
        if isinstance(result, list):
            to_emails.extend(result)
        else:
            to_emails.append(result)

    to_emails = list(filter(None, set(to_emails)))

    employees = Employee.objects.filter(
        models.Q(email__in=to_emails)
        | models.Q(employee_work_info__email__in=to_emails)
    ).select_related("employee_work_info")

    employees = list(employees)
    try:
        also_sent_to = automation.also_sent_to.select_related(
            "employee_work_info"
        ).all()
        if also_sent_to.exists():
            employees.extend(emp for emp in also_sent_to if emp)
    except Exception as e:
        logger.error(e)

    cc_emails = [str(emp.get_mail()) for emp in also_sent_to if emp and emp.get_mail()]
    user_ids = [emp.employee_user_id for emp in employees]

    to = to_emails
    cc = cc_emails

    email_backend = ConfiguredEmailBackend()
    default_email = email_backend.dynamic_from_email_with_display_name

    from_email = default_email
    reply_to = [default_email]

    if request and hasattr(request, "user") and hasattr(request.user, "employee_get"):
        try:
            user = request.user.employee_get
            display_email_name = f"{user.get_full_name()} <{user.get_mail()}>"  # 983
            from_email = display_email_name
            reply_to = [display_email_name]
        except Exception as e:
            logger.error(f"Error generating user-based email display name: {e}")

    if pk_or_text and request and to_emails:
        attachments = []
        try:
            sender = request.user.employee_get
        except:
            sender = None
        # Automation bodies/titles are admin-authored Django template source
        # stored in the DB, rendered here with real employee/instance data and
        # (for attachments) fed to wkhtmltopdf. sanitize_mail_template_body()
        # strips forbidden attribute access (password, META, session, ...) and
        # forbidden tags; build_safe_template_request() keeps `request` usable
        # in templates without exposing its sensitive internals.
        safe_request = build_safe_template_request(request)
        if context_instance:
            if template_attachments := automation.template_attachments.all():
                for template_attachment in template_attachments:
                    template_bdy = template.Template(
                        sanitize_mail_template_body(template_attachment.body)
                    )
                    context = template.Context(
                        {
                            "instance": context_instance,
                            "self": sender,
                            "model_instance": instance,
                            "request": safe_request,
                        }
                    )
                    render_bdy = template_bdy.render(context)
                    # A blocklist over the raw template source can be bypassed
                    # by splitting a dangerous tag across separate {{ }}
                    # expressions that only combine into e.g. "<script>" once
                    # rendered. Re-check the actual rendered HTML -- the thing
                    # that's about to reach wkhtmltopdf (which runs with
                    # local-file-access enabled) -- not just the source.
                    if has_xss(render_bdy):
                        logger.error(
                            "Automation '%s': rendered attachment body failed "
                            "the post-render XSS check; skipping this PDF "
                            "attachment.",
                            automation.title,
                        )
                        continue
                    attachments.append(
                        (
                            "Document",
                            generate_pdf(
                                render_bdy, {}, path=False, title="Document"
                            ).content,
                            "application/pdf",
                        )
                    )

            template_bdy = template.Template(
                sanitize_mail_template_body(mail_template.body)
            )
        else:
            template_bdy = template.Template(sanitize_mail_template_body(pk_or_text))
        context = template.Context(
            {
                "instance": context_instance,
                "self": sender,
                "model_instance": instance,
                "request": safe_request,
            }
        )
        render_bdy = template_bdy.render(context)

        title_template = template.Template(
            sanitize_mail_template_body(automation.title)
        )
        title_context = template.Context(
            {"instance": instance, "self": sender, "request": safe_request}
        )
        render_title = title_template.render(title_context)
        soup = BeautifulSoup(render_bdy, "html.parser")
        plain_text = soup.get_text(separator="\n")

        email = EmailMessage(
            subject=render_title,
            body=render_bdy,
            to=to,
            cc=cc,
            from_email=from_email,
            reply_to=reply_to,
        )
        email.content_subtype = "html"

        email.attachments = attachments

        def _send_mail(email):
            try:
                email.send()
                logger.info(
                    f"Automation <Mail> {automation.title} is triggered by {request.user.employee_get}"
                )
            except Exception as e:
                logger.error(e)

        def _send_notification(text):
            notify.send(
                sender,
                recipient=user_ids,
                verb=f"{text}",
                icon="person-remove",
                redirect="",
            )
            logger.info(
                f"Automation <Notification> {automation.title} is triggered by {request.user.employee_get}"
            )

        if automation.delivery_channel != "notification":
            thread = threading.Thread(
                target=lambda: _send_mail(email),
            )
            thread.start()

        if automation.delivery_channel != "email":
            thread = threading.Thread(
                target=lambda: _send_notification(plain_text),
            )
            thread.start()
        logger.info(
            f"Automation Triggered | {automation.get_delivery_channel_display()} | {automation}"
        )
