"""Background export delivery for heavy standard-report downloads (Phase 8)."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from django.core.mail import EmailMessage
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

# The view promises the user an email, so a concurrency ceiling is needed: an
# unbounded thread pool each building a 5000-row workbook in memory is a
# denial-of-service vector. Requests over the limit are refused up front so
# the user is told immediately instead of waiting for a mail that never
# arrives.
# ponytail: a plain semaphore, not a task queue -- report/scheduler.py or a
# real broker is the upgrade path if this needs retries or restart survival.
MAX_CONCURRENT_EXPORTS = 4
_export_slots = threading.BoundedSemaphore(MAX_CONCURRENT_EXPORTS)


class ExportQueueFull(RuntimeError):
    """Raised when too many async exports are already running."""


def queue_export_email(
    *,
    user_id: int,
    to_email: str,
    slug: str,
    fmt: str,
    filters_dict: dict,
    meta: dict,
    filename: str = "",
    company_id: Optional[int] = None,
) -> None:
    """Spawn a daemon thread that builds the export and emails it.

    ``company_id`` is the caller's selected company. It has to be passed in
    explicitly: the worker runs outside the request, so neither the session
    nor the ``current_company_id`` ContextVar that HorillaCompanyManager
    scopes on is available to it. Without it the emailed workbook spans every
    company while its letterhead names one.
    """

    def _run():
        try:
            import report.metrics  # noqa: F401
            from base.backends import ConfiguredEmailBackend
            from horilla.horilla_middlewares import set_selected_company
            from report.engine import filters_from_dict
            from report.export import export_csv, export_pdf, export_xlsx
            from report.registry import get_report, run_report

            # Restore tenant scope inside this thread before running any
            # query. Company-scoped managers no-op when this is unset, and
            # filters_from_dict only reaches metrics that call
            # apply_org_filters -- so both halves are needed.
            if company_id is not None:
                set_selected_company(company_id)

            definition = get_report(slug)
            if not definition:
                logger.warning("Async export: unknown report %s", slug)
                return

            filters = filters_from_dict(filters_dict, default_company_id=company_id)
            filters.extra["row_limit"] = 5000
            payload = run_report(slug, filters)
            safe = slug.replace("/", "-")
            fmt_local = (fmt or "xlsx").lower()
            if fmt_local == "csv":
                filename_local = filename or f"{safe}.csv"
                response = export_csv(payload, filename=filename_local, meta=meta)
                content_type = "text/csv"
            elif fmt_local == "pdf":
                filename_local = filename or f"{safe}.pdf"
                response = export_pdf(payload, filename=filename_local, meta=meta)
                content_type = "application/pdf"
            else:
                fmt_local = "xlsx"
                filename_local = filename or f"{safe}.xlsx"
                response = export_xlsx(payload, filename=filename_local, meta=meta)
                content_type = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            backend = ConfiguredEmailBackend()
            from_email = (
                getattr(backend, "dynamic_from_email_with_display_name", None) or ""
            )
            if not from_email:
                logger.warning(
                    "Async export for %s skipped — email server not configured", slug
                )
                return

            subject = _("Horilla report ready: %(name)s") % {
                "name": str(definition.name)
            }
            body = _(
                "Your requested export is attached.\n\nReport: %(name)s\nFormat: %(fmt)s"
            ) % {"name": str(definition.name), "fmt": fmt_local}
            msg = EmailMessage(
                subject=subject,
                body=body,
                from_email=from_email,
                to=[to_email],
                connection=backend,
            )
            msg.attach(filename_local, response.content, content_type)
            sent = msg.send(fail_silently=False)
            logger.info(
                "Async export emailed user_id=%s slug=%s fmt=%s sent=%s",
                user_id,
                slug,
                fmt_local,
                sent,
            )
        except Exception:
            logger.exception(
                "Async export failed for slug=%s user_id=%s", slug, user_id
            )
            # The user was told an email was coming; silence leaves them
            # waiting indefinitely for a download that will never arrive.
            _notify_failure(to_email, slug)
        finally:
            _export_slots.release()

    if not _export_slots.acquire(blocking=False):
        raise ExportQueueFull(
            "Too many report exports already running; try again shortly."
        )
    thread = threading.Thread(target=_run, name=f"report-export-{slug}", daemon=True)
    thread.start()


def _notify_failure(to_email: str, slug: str) -> None:
    """Best-effort 'your export failed' mail. Never raises."""
    try:
        from base.backends import ConfiguredEmailBackend
        from report.registry import get_report

        backend = ConfiguredEmailBackend()
        from_email = (
            getattr(backend, "dynamic_from_email_with_display_name", None) or ""
        )
        if not from_email or not to_email:
            return
        definition = get_report(slug)
        name = str(definition.name) if definition else slug
        EmailMessage(
            subject=_("Horilla report export failed: %(name)s") % {"name": name},
            body=_(
                "Your requested export could not be generated.\n\n"
                "Report: %(name)s\n\n"
                "Please try again, or narrow the filters if the report is "
                "very large."
            )
            % {"name": name},
            from_email=from_email,
            to=[to_email],
            connection=backend,
        ).send(fail_silently=True)
    except Exception:
        logger.exception("Could not send async export failure notice for %s", slug)
