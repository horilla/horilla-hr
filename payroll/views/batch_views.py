"""
The payroll run wizard, and what happens to a run afterwards.

Generation used to be a single modal: a name, a list of employees, two dates,
and a button that wrote payslips. Nothing was checked first and nothing was
recorded about the run, so a mistake was only visible as a wrong payslip.

Three steps instead, which is how payroll is actually run:

  1. **Scope** — which period, and who is in it.
  2. **Review** — the attendance each person's pay will be worked out from,
     and what is wrong with it. Blocking problems must be fixed before the run
     can start; warnings are shown and passed.
  3. **Generate** — in slices, with real progress, resumable if the request
     dies.

The employee list survives between steps in the session rather than being
re-derived, so the set reviewed is exactly the set generated. Anything else
and a contract activated between the two steps would silently join a run
nobody reviewed.
"""

import logging
from datetime import date, timedelta

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from base.methods import paginator_qry
from employee.models import Employee
from horilla.decorators import hx_request_required, login_required, permission_required
from horilla.http.response import HorillaRedirect
from payroll.forms.batch_forms import PayPeriodSettingsForm, PayrollBatchScopeForm
from payroll.methods import batch_run
from payroll.models.models import (
    PayPeriodSettings,
    PayrollBatch,
    PayrollBatchLine,
    Payslip,
)

logger = logging.getLogger(__name__)

SESSION_KEY = "payroll_batch_wizard"


def _settings_for(request):
    return PayPeriodSettings.for_company(
        getattr(
            getattr(request.user, "employee_get", None), "get_company", lambda: None
        )()
    )


def _wizard_state(request):
    return request.session.get(SESSION_KEY) or {}


# ---------------------------------------------------------------------------
# The list, and one run
# ---------------------------------------------------------------------------


@login_required
@permission_required("payroll.view_payslip")
def batch_home(request):
    """
    Every run, newest first, with the totals across the ones on screen.

    The figures at the top are the denormalised counters on each run rather
    than an aggregate over payslips — twenty runs would otherwise mean twenty
    aggregate queries to draw one row of numbers.
    """
    batches = PayrollBatch.objects.all()

    period = _settings_for(request).period_for(date.today())
    return render(
        request,
        "payroll/batch/batch_home.html",
        {
            "batches": paginator_qry(batches, request.GET.get("page")),
            "kpi": _kpis(batches),
            "period": period,
            "pd": request.GET.urlencode(),
        },
    )


def _kpis(batches):
    """Headline figures for the runs listed."""
    from django.db.models import Count, Q, Sum

    figures = batches.aggregate(
        runs=Count("id"),
        employees=Sum("generated_count"),
        net=Sum("total_net"),
        gross=Sum("total_gross"),
        flagged=Sum("flagged_count"),
        failed=Sum("failed_count"),
        unpaid=Count("id", filter=~Q(status=PayrollBatch.PAID)),
    )
    figures = {key: value or 0 for key, value in figures.items()}
    # Payslips counted for active employees only, as each run shows them.
    from payroll.models.models import Payslip

    figures["employees"] = Payslip.objects.filter(
        payroll_batch__in=batches, employee_id__is_active=True
    ).count()
    return figures


@login_required
@permission_required("payroll.view_payslip")
def batch_detail(request, batch_id, model=None):
    """One run: its payslips, the ones that failed, and where it can go next."""
    batch = get_object_or_404(PayrollBatch, pk=batch_id)
    problems = batch.lines.filter(
        status__in=[PayrollBatchLine.FAILED, PayrollBatchLine.SKIPPED]
    ).select_related("employee_id")

    return render(
        request,
        "payroll/batch/batch_detail.html",
        {
            "batch": batch,
            "problems": problems,
            "next_statuses": _next_statuses(batch),
        },
    )


def _next_statuses(batch):
    """The transitions offered, each with the reason when it is not."""
    offered = []
    for value, label in PayrollBatch.STATUS_CHOICES:
        if value == batch.status:
            continue
        allowed, reason = batch.can_transition_to(value)
        if allowed or value in PayrollBatch.ALLOWED_TRANSITIONS[batch.status]:
            offered.append(
                {"value": value, "label": label, "allowed": allowed, "reason": reason}
            )
    return offered


@login_required
@permission_required("payroll.change_payslip")
def batch_set_status(request, batch_id):
    """
    Move a run to another status, or say why it cannot go there.

    Checked here and not only in the template, because the template only hides
    a button.
    """
    batch = get_object_or_404(PayrollBatch, pk=batch_id)
    wanted = request.POST.get("status", "")

    allowed, reason = batch.can_transition_to(wanted)
    if not allowed:
        messages.error(request, reason)
        return HorillaRedirect(
            request, reverse("payroll-batch-detail", args=[batch.pk])
        )

    batch.status = wanted
    batch.save(update_fields=["status"])

    # The payslips follow the run, backwards as well as forwards. A run marked
    # paid whose payslips still read "draft" is the disagreement that makes
    # both untrustworthy, and so is a run sent back to draft whose payslips
    # still read "confirmed".
    #
    # Cancelling sends them to draft rather than leaving them: a run can only
    # be cancelled before it is paid, so the most they can be is confirmed,
    # and a confirmed payslip belonging to a cancelled run reads as approved
    # money.
    mirrored = {
        PayrollBatch.DRAFT: "draft",
        PayrollBatch.REVIEW: "review_ongoing",
        PayrollBatch.APPROVED: "confirmed",
        PayrollBatch.PAID: "paid",
        PayrollBatch.CANCELLED: "draft",
    }.get(wanted)
    if mirrored:
        batch.payslips.update(status=mirrored)

    messages.success(
        request,
        _("Batch marked %(status)s.") % {"status": batch.get_status_display()},
    )
    return HorillaRedirect(request, reverse("payroll-batch-detail", args=[batch.pk]))


@login_required
@permission_required("payroll.delete_payslip")
def batch_delete(request, batch_id):
    """
    Delete a run, and with it the payslips it generated.

    A paid run is refused: it is the record of money that left the business,
    and correcting it means another run. Everything short of that is a draft
    somebody ran to see what it looked like, and being unable to throw one away
    is how a list fills with runs nobody trusts.

    The payslips go too. They are only in the database because this run put
    them there, and leaving them behind would orphan them into a payslip list
    where nothing says where they came from.
    """
    batch = get_object_or_404(PayrollBatch, pk=batch_id)

    if batch.status == PayrollBatch.PAID:
        messages.error(
            request,
            _("A paid batch cannot be deleted. Correct it with another batch."),
        )
        return HorillaRedirect(
            request, reverse("payroll-batch-detail", args=[batch.pk])
        )

    if request.method != "POST":
        return HorillaRedirect(
            request, reverse("payroll-batch-detail", args=[batch.pk])
        )

    name = batch.batch_name
    removed = batch.payslips.count()
    with transaction.atomic():
        batch.payslips.all().delete()
        batch.delete()

    messages.success(
        request,
        _("Deleted the batch %(name)s and its %(count)s payslip(s).")
        % {"name": name, "count": removed},
    )
    return HorillaRedirect(request, reverse("payroll-batch-home"))


@login_required
@permission_required("payroll.delete_payslip")
@permission_required("payroll.add_payslip")
def batch_reopen(request, batch_id):
    """
    Send a draft run back to "Review & Regularize", to fix what it was built on.

    A draft is only worth keeping while it is right. When it turns out wrong
    because of what it read -- attendance that needs regularising, a contract
    missing a wage -- the fix is made in those places, and the payslips have to
    be made again to pick it up. This does the first half: it discards the
    run's draft payslips and puts the same people and period back in front of
    the review step, where the fixes are one click away. Generating from there
    makes the run afresh.

    Only a draft run qualifies. Once any payslip has moved on (review,
    confirmed, paid) it is a record somebody has acted on, and changing it
    goes through the run's status, not through a quiet rebuild.
    """
    batch = get_object_or_404(PayrollBatch, pk=batch_id)
    detail = reverse("payroll-batch-detail", args=[batch.pk])

    if request.method != "POST":
        return HorillaRedirect(request, detail)

    if (
        batch.status != PayrollBatch.DRAFT
        or batch.payslips.exclude(status="draft").exists()
    ):
        messages.error(
            request,
            _("Only a draft batch can be sent back to check its inputs."),
        )
        return HorillaRedirect(request, detail)

    state = {
        "batch_name": batch.batch_name,
        "period_start": batch.period_start.isoformat(),
        "period_end": batch.period_end.isoformat(),
        "employee_ids": list(batch.lines.values_list("employee_id_id", flat=True)),
    }
    with transaction.atomic():
        batch.payslips.all().delete()
        batch.delete()

    request.session[SESSION_KEY] = state
    messages.info(
        request,
        _(
            "Back at Review & Regularize. The draft payslips were discarded; fix "
            "what needs fixing and generate again."
        ),
    )
    return HorillaRedirect(request, reverse("payroll-batch-review"))


# ---------------------------------------------------------------------------
# Step 1 — scope
# ---------------------------------------------------------------------------


@login_required
@permission_required("payroll.add_payslip")
def wizard_scope(request):
    """Which period, and who is in it."""
    settings = _settings_for(request)
    # The last period that has finished, not the current one: payroll is run once
    # the period is over, so that is the one people almost always want. The start
    # stays editable (the end follows from it).
    period = settings.last_completed_period(date.today())

    if request.method == "POST":
        form = PayrollBatchScopeForm(request.POST, period=period, settings=settings)
        if form.is_valid():
            employees = form.selected_employees()
            request.session[SESSION_KEY] = {
                "batch_name": form.cleaned_data["batch_name"],
                "period_start": form.cleaned_data["period_start"].isoformat(),
                "period_end": form.cleaned_data["period_end"].isoformat(),
                "employee_ids": [employee.pk for employee in employees],
            }
            return redirect("payroll-batch-review")
    else:
        form = PayrollBatchScopeForm(period=period, settings=settings)

    return render(
        request,
        "payroll/batch/wizard_scope.html",
        {"form": form, "settings": settings, "step": 1},
    )


# ---------------------------------------------------------------------------
# Step 2 — review
# ---------------------------------------------------------------------------


@login_required
@permission_required("payroll.add_payslip")
def wizard_review(request):
    """
    What the engine will read for each person, and what is wrong with it.

    Nothing is written here. A blocked row cannot be generated at all — see
    ``batch_run._exceptions_for`` for why an unresolved attendance conflict is
    treated as a stop rather than a warning.
    """
    state = _wizard_state(request)
    if not state:
        return redirect("payroll-batch-scope")

    start = date.fromisoformat(state["period_start"])
    end = date.fromisoformat(state["period_end"])
    employees = list(Employee.objects.filter(pk__in=state["employee_ids"]))

    result = batch_run.review(employees, start, end)

    return render(
        request,
        "payroll/batch/wizard_review.html",
        {
            "step": 2,
            "batch_name": state["batch_name"],
            "period_start": start,
            "period_end": end,
            "blocking": batch_run.BLOCKING,
            **result,
        },
    )


# ---------------------------------------------------------------------------
# Step 3 — generate
# ---------------------------------------------------------------------------


def _progress_context(batch):
    """Who is next and who just finished, from queries that stay small on a long run."""
    from django.utils import timezone

    from payroll.models.models import PayrollBatchLine

    lines = batch.lines.select_related("employee_id", "payslip")
    done = lines.exclude(status=PayrollBatchLine.QUEUED)

    # Elapsed since the run was created, and what is left at the pace so far.
    elapsed = max(int((timezone.now() - batch.created_at).total_seconds()), 0)
    left = max(batch.employee_count - batch.processed_count, 0)
    eta = (
        int(elapsed / batch.processed_count * left)
        if batch.processed_count and not batch.is_finished
        else None
    )

    def clock(seconds):
        return f"{seconds // 60}:{seconds % 60:02d}"

    return {
        "batch": batch,
        "elapsed": clock(elapsed),
        "eta": clock(eta) if eta is not None else None,
        "left_count": max(batch.employee_count - batch.processed_count, 0),
        "next_employee": getattr(
            lines.filter(status=PayrollBatchLine.QUEUED).first(), "employee_id", None
        ),
        # Newest first, a handful: a hundred rows in a modal helps nobody.
        "recent_lines": list(
            done.exclude(status=PayrollBatchLine.FAILED).order_by("-pk")[:6]
        ),
        "failed_lines": list(lines.filter(status=PayrollBatchLine.FAILED)),
    }


@login_required
@permission_required("payroll.add_payslip")
def wizard_start(request):
    """
    Create the run and hand over to the progress page.

    The blocked employees are dropped here rather than in review, so the count
    on the confirmation is the count that will actually be paid.
    """
    state = _wizard_state(request)
    if not state or request.method != "POST":
        return redirect("payroll-batch-scope")

    start = date.fromisoformat(state["period_start"])
    end = date.fromisoformat(state["period_end"])
    employees = list(Employee.objects.filter(pk__in=state["employee_ids"]))

    result = batch_run.review(employees, start, end)
    ready = [row["employee"] for row in result["rows"] if not row["blocked"]]

    if not ready:
        messages.error(
            request, _("Nobody in this batch can be paid yet. Fix the problems listed.")
        )
        if request.headers.get("HX-Request"):
            return HorillaRedirect(request, reverse("payroll-batch-review"))
        return redirect("payroll-batch-review")

    batch = batch_run.create_batch(
        name=state["batch_name"],
        start_date=start,
        end_date=end,
        employees=ready,
        user=request.user,
        settings=_settings_for(request),
    )
    request.session.pop(SESSION_KEY, None)
    if request.headers.get("HX-Request"):
        # The review page shows the run in a modal instead of leaving the page.
        return render(
            request, "payroll/batch/_progress_modal.html", _progress_context(batch)
        )
    return redirect("payroll-batch-progress", batch_id=batch.pk)


@login_required
@permission_required("payroll.add_payslip")
def wizard_progress(request, batch_id):
    """The progress page. The bar itself is the fragment below."""
    batch = get_object_or_404(PayrollBatch, pk=batch_id)
    return render(
        request,
        "payroll/batch/wizard_progress.html",
        {"step": 3, **_progress_context(batch)},
    )


@login_required
@permission_required("payroll.add_payslip")
@hx_request_required
def wizard_generate_slice(request, batch_id):
    """
    Generate the next few payslips and re-render the bar.

    Driven by the fragment's own ``hx-trigger="load"``: each response that is
    not finished contains the element that asks for the next slice. That makes
    the run resumable by reloading the page — a browser closed mid-run leaves
    a batch whose remaining lines are still queued, not a half-written run with
    no record of where it stopped.
    """
    batch = get_object_or_404(PayrollBatch, pk=batch_id)

    if not batch.is_finished:
        try:
            batch_run.generate_slice(batch)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            logger.exception("Payroll batch %s stopped", batch.pk)
            batch.progress_state = PayrollBatch.FAILED
            batch.last_error = f"{type(exc).__name__}: {exc}"
            batch.save(update_fields=["progress_state", "last_error"])

    batch.refresh_from_db()
    return render(request, "payroll/batch/_progress.html", _progress_context(batch))


# ---------------------------------------------------------------------------
# Pay period settings
# ---------------------------------------------------------------------------


@login_required
@permission_required("payroll.change_payslipautogenerate")
def pay_period_settings(request, pk=None):
    """
    A company's pay period. One row per company (and one for all companies).

    Without ``pk`` this is the signed-in user's own company: its row, or a new one that starts
    from the setting now in force. With ``pk`` it is that row, which is how the Payroll Settings
    list edits any company's. ``?new=1`` opens a blank row for a company still without one.
    """
    from base.auth_backends import stamp_company_on_create

    creating = bool(request.GET.get("new") or request.POST.get("new"))
    if pk is not None:
        instance = get_object_or_404(PayPeriodSettings.objects.entire(), pk=pk)
    elif creating:
        instance = PayPeriodSettings()
    else:
        company = getattr(
            getattr(request.user, "employee_get", None), "get_company", lambda: None
        )()
        instance = PayPeriodSettings.objects.entire().filter(company_id=company).first()
        if instance is None:
            # No row of its own yet: start from what is in force, saved as this company's.
            in_force = PayPeriodSettings.for_company(company)
            instance = PayPeriodSettings(
                company_id=company,
                cycle_start_day=in_force.cycle_start_day,
                pay_day_offset=in_force.pay_day_offset,
                pay_day_of_month=in_force.pay_day_of_month,
            )
    # ?modal=1: the same form, loaded into a dialog -- the run wizard's, or the settings list's.
    modal = bool(request.GET.get("modal")) and bool(request.META.get("HTTP_HX_REQUEST"))
    from_list = request.GET.get("then") == "list"
    with_company = from_list
    if request.method == "POST":
        form = PayPeriodSettingsForm(
            request.POST, instance=instance, modal=modal, with_company=with_company
        )
        if form.is_valid():
            obj = form.save(commit=False)
            if not obj.pk and obj.company_id_id is None and not with_company:
                stamp_company_on_create(obj)
            obj.save()
            messages.success(request, _("Pay period saved."))
            if modal and from_list:
                return HttpResponse(
                    "<script>$('#genericModal').removeClass('oh-modal--show');"
                    "htmx.ajax('GET', '%s', {target: '#payPeriodListContainer', swap: 'innerHTML'});</script>"
                    % reverse("pay-period-list")
                )
            if modal:
                # The page behind the dialog shows dates drawn from this setting.
                return HttpResponse("<script>window.location.reload();</script>")
            return HorillaRedirect(request, reverse("pay-period-settings"))
    else:
        form = PayPeriodSettingsForm(
            instance=instance, modal=modal, with_company=with_company
        )

    start, end = instance.period_for(date.today())
    return render(
        request,
        (
            "payroll/batch/pay_period_settings_modal.html"
            if modal
            else "payroll/batch/pay_period_settings.html"
        ),
        {
            "form": form,
            "example_start": start,
            "example_end": end,
            "example_pay_date": instance.pay_date_for(end),
            "today": date.today(),
            "modal_body_id": "genericModalBody" if from_list else "pbSettingsModalBody",
            "post_url": request.get_full_path(),
            "show_company": with_company,
            "heading": _("Pay period") if not instance.pk else _("Pay period"),
        },
    )


@login_required
@permission_required("payroll.delete_payslipautogenerate")
def pay_period_delete(request, pk):
    """Remove one company's pay period; that company then falls back to the all-companies one."""
    if request.method != "POST":
        return HorillaRedirect(request, reverse("payroll-settings"))
    row = PayPeriodSettings.objects.entire().filter(pk=pk).first()
    if row is None:
        messages.error(request, _("Pay period not found."))
    else:
        row.delete()
        messages.success(request, _("Pay period deleted."))
    return HorillaRedirect(request)


@login_required
@permission_required("payroll.add_payslip")
def pay_period_generate(request, pk):
    """Generate payslips now for a company's last completed pay period."""
    if request.method != "POST":
        return HorillaRedirect(request, reverse("payroll-settings"))
    from payroll.scheduler import generate_for_setting

    row = PayPeriodSettings.objects.entire().filter(pk=pk).first()
    if row is None:
        messages.error(request, _("Pay period not found."))
        return HorillaRedirect(request)
    start, end = row.manual_period()
    created = generate_for_setting(row, date.today(), force=True)
    period = f"{start.day} {start:%b %Y} \u2013 {end.day} {end:%b %Y}"
    if created:
        messages.success(
            request,
            _("%(n)s payslips generated for %(period)s.")
            % {"n": created, "period": period},
        )
    else:
        messages.info(
            request,
            _("No new payslips: everyone already has one for %(period)s.")
            % {"period": period},
        )
    return HorillaRedirect(request)
