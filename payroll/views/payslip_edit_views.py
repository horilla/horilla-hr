"""
Editing a generated payslip's own components, with a live preview.

See payroll/methods/payslip_edit.py for what "editing" means here and why it
never touches the shared component definitions. This module is the HTTP shell
around it: render the form, read what was posted, apply it, hand back the same
payslip fragment the status dropdown already swaps into #payslipBody — so
saving an edit updates the page exactly the way changing status already does,
not as a separate mechanism next to it.
"""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from horilla.decorators import hx_request_required, login_required, permission_required
from horilla.http.response import HorillaRedirect
from payroll.methods.component_formula import (
    ComponentFormulaError,
    run_component_formula,
)
from payroll.methods.methods import get_total_calendar_days
from payroll.methods.payslip_edit import (
    NewLineError,
    apply_edits,
    editable_lines,
    formula_codes,
    formula_context,
    parse_amounts,
    parse_new_line,
    recompute_dependents,
)
from payroll.models.models import Payslip


def _payslip_context(payslip):
    """
    The exact context individual_payslip_summery.html renders from —
    pay_head_data plus the handful of keys the surrounding template expects.
    Mirrors update_payslip_status's own build of it, so the fragment returned
    after an edit looks identical in shape to the one returned after a status
    change.
    """
    data = dict(payslip.pay_head_data or {})
    data["employee"] = payslip.employee_id
    data["payslip"] = payslip
    data["json_data"] = data.copy()
    data["json_data"]["employee"] = payslip.employee_id.id
    data["json_data"]["payslip"] = payslip.id
    data["instance"] = payslip
    data["total_calendar_days"] = get_total_calendar_days(data)
    return data


@login_required
@permission_required("payroll.change_payslip")
def edit_payslip_components(request, payslip_id):
    """
    GET renders the edit form; POST applies it.

    Refused once a payslip is paid, matching every other place in this app
    that treats "paid" as the end of a payslip's story — the record of money
    that left is not something an edit form should be able to reach back into.
    """
    payslip = get_object_or_404(Payslip, pk=payslip_id)

    if payslip.status == "paid":
        messages.error(request, _("A paid payslip cannot be edited."))
        return HorillaRedirect(
            request, reverse("view-created-payslip", kwargs={"payslip_id": payslip.pk})
        )

    lines = editable_lines(payslip)

    if request.method == "POST":
        amounts = parse_amounts(request.POST, lines)
        removed = {
            key
            for key in request.POST.getlist("remove")
            if any(line["key"] == key and line["removable"] for line in lines)
        }
        try:
            new_line = parse_new_line(request.POST, payslip)
        except NewLineError as exc:
            # Nothing is written. Saving the corrections but dropping the line
            # someone just built would be the worst of both, and there is no
            # way to say so on a response that swaps the payslip itself -- so
            # the redirect is what carries the message.
            messages.error(request, exc.args[0])
            return HorillaRedirect(
                request,
                reverse("view-created-payslip", kwargs={"payslip_id": payslip.pk}),
            )

        apply_edits(payslip, amounts, removed, new_line=new_line)
        messages.success(request, _("Payslip updated."))

        if request.headers.get("HX-Request"):
            return render(
                request,
                "payroll/payslip/individual_payslip_summery.html",
                _payslip_context(payslip),
            )
        return redirect(
            reverse("view-created-payslip", kwargs={"payslip_id": payslip.pk})
        )

    return render(
        request,
        "payroll/payslip/edit_components_modal.html",
        {
            "payslip": payslip,
            "lines": lines,
            # The tap-to-build formula editor, reused as-is. It reads these two
            # from the context: which codes to offer as chips, and where to
            # send its live preview -- which for a payslip is the endpoint
            # below, not the component form's sample-figure one.
            "formula_codes": formula_codes(payslip),
            "formula_preview_url": reverse(
                "payslip-line-formula-preview", kwargs={"payslip_id": payslip.pk}
            ),
            "formula_preview_note": _("against this payslip's own figures"),
            "recalculate_url": reverse(
                "recalculate-payslip-lines", kwargs={"payslip_id": payslip.pk}
            ),
        },
    )


@login_required
@hx_request_required
@permission_required("payroll.change_payslip")
def preview_payslip_line_formula(request, payslip_id):
    """
    What a formula comes to on this payslip. Saves nothing.

    The same JSON the component form's preview returns, so the builder needs
    no second code path -- the difference is entirely in the context it is
    evaluated against: real resolved amounts for this employee and period
    rather than an illustrative basic pay, which is why the reply says so and
    the builder stops labelling the answer an estimate.
    """
    payslip = get_object_or_404(Payslip, pk=payslip_id)
    expression = request.POST.get("formula") or ""
    context = formula_context(payslip)

    try:
        result = run_component_formula(expression, context)
    except ComponentFormulaError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    used = sorted(
        {code for code in context if code in expression.upper()},
        key=lambda code: -len(code),
    )
    return JsonResponse(
        {
            "ok": True,
            "result": round(result, 2),
            "expression": expression,
            "used": [{"code": code, "value": round(context[code], 2)} for code in used],
            "note": str(_("this payslip's own figures")),
        }
    )


@login_required
@hx_request_required
@permission_required("payroll.change_payslip")
def recalculate_payslip_lines(request, payslip_id):
    """
    Move the lines that follow other lines, given what is on the form now.
    Saves nothing.

    This is on the server rather than in the form's own script for the reason
    the rest of this feature is: the amounts are worked out from the component
    definitions -- percentages, formulas, the balance of a CTC -- and a second
    implementation of those in JavaScript would be free to drift from the one
    that generated the payslip. Only the amounts come back: the totals stay
    the browser's own addition, so each figure on the form has exactly one
    thing deciding it.
    """
    payslip = get_object_or_404(Payslip, pk=payslip_id)
    lines = editable_lines(payslip)

    amounts = parse_amounts(request.POST, lines)
    removed = {
        key
        for key in request.POST.getlist("remove")
        if any(line["key"] == key and line["removable"] for line in lines)
    }
    given = {
        key
        for key in request.POST.getlist("given")
        if any(line["key"] == key for line in lines)
    }

    recomputed = recompute_dependents(payslip, amounts, removed=removed, given=given)

    return JsonResponse(
        {
            "ok": True,
            "amounts": {key: round(value, 2) for key, value in recomputed.items()},
        }
    )
