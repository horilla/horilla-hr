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
from datetime import date

from django.contrib import messages
from django.db import transaction
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
    return {key: value or 0 for key, value in figures.items()}


@login_required
@permission_required("payroll.view_payslip")
def batch_detail(request, batch_id):
    """One run: its payslips, the ones that failed, and where it can go next."""
    batch = get_object_or_404(PayrollBatch, pk=batch_id)
    payslips = batch.payslips.select_related("employee_id").order_by(
        "employee_id__employee_first_name"
    )
    problems = batch.lines.filter(
        status__in=[PayrollBatchLine.FAILED, PayrollBatchLine.SKIPPED]
    ).select_related("employee_id")

    return render(
        request,
        "payroll/batch/batch_detail.html",
        {
            "batch": batch,
            "payslips": paginator_qry(payslips, request.GET.get("page")),
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
        _("Run marked %(status)s.") % {"status": batch.get_status_display()},
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
            _("A paid run cannot be deleted. Correct it with another run."),
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
        _("Deleted the run %(name)s and its %(count)s payslip(s).")
        % {"name": name, "count": removed},
    )
    return HorillaRedirect(request, reverse("payroll-batch-home"))


# ---------------------------------------------------------------------------
# Step 1 — scope
# ---------------------------------------------------------------------------


@login_required
@permission_required("payroll.add_payslip")
def wizard_scope(request):
    """Which period, and who is in it."""
    settings = _settings_for(request)
    period = settings.period_for(date.today())

    if request.method == "POST":
        form = PayrollBatchScopeForm(request.POST, period=period)
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
        form = PayrollBatchScopeForm(period=period)

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
            request, _("Nobody in this run can be paid yet. Fix the problems listed.")
        )
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
    return redirect("payroll-batch-progress", batch_id=batch.pk)


@login_required
@permission_required("payroll.add_payslip")
def wizard_progress(request, batch_id):
    """The progress page. The bar itself is the fragment below."""
    batch = get_object_or_404(PayrollBatch, pk=batch_id)
    return render(
        request, "payroll/batch/wizard_progress.html", {"step": 3, "batch": batch}
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
    return render(request, "payroll/batch/_progress.html", {"batch": batch})


# ---------------------------------------------------------------------------
# Pay period settings
# ---------------------------------------------------------------------------


@login_required
@permission_required("payroll.change_payslipautogenerate")
def pay_period_settings(request):
    """The company's pay period. One row per company, created on first save."""
    from base.auth_backends import stamp_company_on_create

    instance = _settings_for(request)
    if request.method == "POST":
        form = PayPeriodSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            if not obj.pk:
                stamp_company_on_create(obj)
            obj.save()
            messages.success(request, _("Pay period saved."))
            return HorillaRedirect(request, reverse("pay-period-settings"))
    else:
        form = PayPeriodSettingsForm(instance=instance)

    start, end = instance.period_for(date.today())
    return render(
        request,
        "payroll/batch/pay_period_settings.html",
        {
            "form": form,
            "example_start": start,
            "example_end": end,
            "example_pay_date": instance.pay_date_for(end),
        },
    )
