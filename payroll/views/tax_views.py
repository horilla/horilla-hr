"""
tax_views.py

This module contains view functions for handling federal tax-related operations.

The functions in this module handle various tasks related to payroll, including creating
filing status, managing tax brackets, calculating federal tax, and more. These functions
utilize the Django framework and make use of the render and redirect functions from the
django.shortcuts module.

"""

import math
from urllib.parse import parse_qs

from django.contrib import messages
from django.db.models import ProtectedError
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from base.methods import get_key_instances
from horilla.decorators import hx_request_required, login_required, permission_required
from horilla.http.response import HorillaRedirect
from payroll.forms.tax_forms import (
    FilingStatusForm,
    FilingStatusTaxRulesForm,
    TaxBracketForm,
    TaxBracketFormSet,
)
from payroll.methods.safe_tax_code import (
    TaxCodeValidationError,
    TaxFormulaTimeout,
    run_tax_formula,
    validate_tax_code,
)
from payroll.methods.tax_calc import TaxComputationError, preview_yearly_tax
from payroll.models.models import FilingStatus
from payroll.models.tax_models import TaxBracket
from payroll.tax_packs import load_tax_packs, pack_rows


def _adjustments(status):
    """
    The adjustments in force on a filing status, named and valued.

    Kept beside the view rather than on the model because it is how the screen
    labels them; the model already states what they *do*, in order, through
    computation_steps().
    """
    found = []
    if status.standard_deduction:
        found.append(
            {
                "label": _("Standard deduction"),
                "value": f"{status.standard_deduction:,.0f}",
            }
        )
    if status.rebate_income_limit is not None:
        found.append(
            {
                "label": _("Rebate"),
                "value": _("%(amount)s below %(limit)s")
                % {
                    "amount": f"{status.rebate_max_amount or 0:,.0f}",
                    "limit": f"{status.rebate_income_limit:,.0f}",
                },
            }
        )
    if status.cess_percent:
        found.append({"label": _("Cess"), "value": f"{status.cess_percent:g}%"})
    return found


@login_required
@permission_required("payroll.view_filingstatus")
def filing_status_view(request):
    """
    Every filing status, and what each one actually does.

    The page was a list of names in an accordion. A filing status is a mode
    flag, a slab table and four adjustment fields, so the name alone answers
    none of the questions the screen raises -- which of these charges what,
    which are configured at all, and who is on them.

    The figure that matters most is the one that was nowhere: contracts with no
    filing status. The engine computes zero tax for them, correctly and
    silently, which looks exactly like a low earner until someone reconciles a
    return.
    """
    from django.db.models import Count, Max, Prefetch, Q

    from payroll.models.models import Contract

    statuses = (
        FilingStatus.objects.all()
        .annotate(
            slab_count=Count("taxbracket", distinct=True),
            top_rate=Max("taxbracket__tax_rate"),
            # Active contracts only: a status still attached to expired
            # contracts is not one anybody is being taxed under.
            employee_count=Count(
                "contracts",
                filter=Q(contracts__contract_status="active"),
                distinct=True,
            ),
        )
        .prefetch_related(
            Prefetch(
                "taxbracket_set",
                queryset=TaxBracket.objects.order_by("min_income"),
                to_attr="slabs",
            )
        )
        .order_by("filing_status")
    )

    rows = []
    for status in statuses:
        # Configured means it will actually charge something. A status with no
        # slabs and no formula computes zero for everyone on it, which is the
        # same silent nothing as having no status at all.
        configured = (
            bool(status.python_code) if status.use_py else bool(status.slab_count)
        )
        rows.append(
            {
                "status": status,
                "configured": configured,
                # Label and figure both: the chips on the summary row name
                # the adjustments, and the ones above the slab table have room
                # to say what they are set to. A chip reading "Rebate" twice
                # would be repetition; "Rebate 60,000 below 1,200,000" is the
                # setting.
                "adjustments": _adjustments(status),
            }
        )

    unassigned = Contract.objects.filter(
        contract_status="active", filing_status__isnull=True
    ).count()

    return render(
        request,
        "payroll/tax/filing_status_view.html",
        {
            "rows": rows,
            "unassigned": unassigned,
            "total_covered": sum(r["status"].employee_count for r in rows),
            "unconfigured": sum(1 for r in rows if not r["configured"]),
        },
    )


@login_required
@hx_request_required
@permission_required("payroll.change_filingstatus")
def update_filing_status(request, filing_status_id):
    """
    Update an existing filing status record based on user input.

    If the request method is POST and the form data is valid, update the filing status form
    and redirect to the update-filing-status page.

    :param tax_bracket_id: The ID of the filing status to update.
    """
    filing_status = FilingStatus.find(filing_status_id)
    if not filing_status:
        messages.error(request, _("Filing status not found"))
        return HorillaRedirect(request)
    filing_status_form = FilingStatusForm(instance=filing_status)
    if request.method == "POST":
        filing_status_form = FilingStatusForm(request.POST, instance=filing_status)
        if filing_status_form.is_valid():
            filing_status_form.save()
            messages.success(request, _("Filing status updated successfully."))
    return render(
        request,
        "payroll/tax/filing_status_edit.html",
        {
            "form": filing_status_form,
        },
    )


@login_required
@hx_request_required
@permission_required("payroll.delete_filingstatus")
def filing_status_delete(request, filing_status_id):
    """
    Delete a filing status.

    This view deletes a filing status with the given `filing_status_id` from the
    database and redirects to the filing status view.

    """
    try:
        filing_status = FilingStatus.find(filing_status_id)
        if filing_status:
            try:
                filing_status.delete()
                messages.info(request, _("Filing status successfully deleted."))
            except ProtectedError:
                messages.error(
                    request,
                    _("Filing status is in use by tax brackets. Remove them first."),
                )
        else:
            messages.error(request, _("This filing status was not found."))
    except Exception as e:
        messages.error(
            request, _("An error occurred while trying to delete the filing status.")
        )
    if not FilingStatus.objects.exists():
        return HorillaRedirect(request)
    # By URL name, not by the view function. This used to be
    # ``redirect(filing_status_search)``, but that view's path() is commented
    # out in tax_urls.py — the name now routes to FilingStatusPipeline — so
    # reversing the function object raised NoReverseMatch and deleting any
    # filing status other than the last one returned a 500. The early return
    # above hid it whenever the last one was deleted.
    return redirect("filing-status-search")


@login_required
@hx_request_required
@permission_required("payroll.view_filingstatus")
def filing_status_search(request):
    """
    Display the filing status search view.

    This view handles the search functionality for filing statuses. It retrieves
    the search term from the GET parameters, filters the FilingStatus objects
    based on the search term, and renders the 'payroll/tax/filing_status_list.html'
    template with the filtered filing statuses.
    """
    search = request.GET.get("search") if request.GET.get("search") else ""
    status = FilingStatus.objects.filter(filing_status__icontains=search)
    previous_data = request.GET.urlencode()
    data_dict = parse_qs(previous_data)
    get_key_instances(FilingStatus, data_dict)
    context = {
        "status": status,
        "pd": previous_data,
        "filter_dict": data_dict,
    }
    return render(request, "payroll/tax/filing_status_list.html", context)


@login_required
@hx_request_required
@permission_required("payroll.view_taxbracket")
def tax_bracket_list(request, filing_status_id):
    """
    Display a list of tax brackets for a specific filing status.

    This view retrieves all tax brackets associated with the given `filing_status_id`
    and renders them in the "tax_bracket_view.html" template.

    Args:
        request: The HTTP request object.
        filing_status_id: The ID of the filing status for which to display tax brackets.

    Returns:
        The rendered "tax_bracket_view.html" template with the tax brackets for the
        specified filing status.
    """
    filing_status = FilingStatus.objects.filter(id=filing_status_id).first()
    if not filing_status:
        return HttpResponse()
    tax_brackets = TaxBracket.objects.filter(
        filing_status_id=filing_status_id
    ).order_by("max_income")
    context = {"tax_brackets": tax_brackets, "filing_status": filing_status}
    return render(request, "payroll/tax/tax_bracket_view.html", context)


@login_required
@hx_request_required
@permission_required("payroll.add_taxbracket")
def create_tax_bracket(request, filing_status_id):
    """
    Create a tax bracket record for federal tax calculation based on user input.

    If the request method is POST and the form data is valid, save the tax bracket form
    and redirect to the tax-bracket-create page.

    """
    tax_bracket_form = TaxBracketForm(initial={"filing_status_id": filing_status_id})
    context = {
        "form": tax_bracket_form,
        "filing_status_id": filing_status_id,
    }
    if request.method == "POST":
        tax_bracket_form = TaxBracketForm(
            request.POST, initial={"filing_status_id": filing_status_id}
        )
        if tax_bracket_form.is_valid():
            max_income = tax_bracket_form.cleaned_data.get("max_income")
            if not max_income:
                messages.info(request, _("The maximum income will be infinite"))
                tax_bracket_form.instance.max_income = math.inf
            tax_bracket_form.save()
            messages.success(request, _("The tax bracket was created successfully."))
            return redirect(create_tax_bracket, filing_status_id=filing_status_id)

        context["form"] = tax_bracket_form

    return render(request, "payroll/tax/tax_bracket_creation.html", context)


@login_required
@hx_request_required
@permission_required("payroll.change_taxbracket")
def update_tax_bracket(request, tax_bracket_id):
    """
    Update an existing tax bracket record based on user input.

    If the request method is POST and the form data is valid, update the tax bracket form
    and redirect to the tax-bracket-create page.

    :param tax_bracket_id: The ID of the tax bracket to update.
    """
    tax_bracket = TaxBracket.find(tax_bracket_id)
    if tax_bracket:
        filing_status_id = tax_bracket.filing_status_id.id
        tax_bracket_form = TaxBracketForm(instance=tax_bracket)
        if request.method == "POST":
            tax_bracket_form = TaxBracketForm(request.POST, instance=tax_bracket)
            if tax_bracket_form.is_valid():
                max_income = tax_bracket_form.cleaned_data.get("max_income")
                if not max_income:
                    messages.info(request, _("The maximum income will be infinite"))
                    tax_bracket_form.instance.max_income = math.inf
                tax_bracket_form.save()
                messages.success(
                    request, _("The tax bracket has been updated successfully.")
                )

        context = {
            "form": tax_bracket_form,
            "filing_status_id": filing_status_id,
        }
        return render(request, "payroll/tax/tax_bracket_edit.html", context)
    messages.error(request, _("Tax bracket not found"))
    return HorillaRedirect(request)


@login_required
@hx_request_required
@permission_required("payroll.delete_taxbracket")
def delete_tax_bracket(request, tax_bracket_id):
    """
    Delete an existing tax bracket record.

    Retrieve the tax bracket with the specified ID and delete it from the database.
    Then, redirect to the tax-bracket-create page.

    :param tax_bracket_id: The ID of the tax bracket to delete.
    """
    tax_bracket = TaxBracket.find(tax_bracket_id)
    filing_status_id = (
        tax_bracket.filing_status_id.id
        if tax_bracket and tax_bracket.delete()
        else None
    )
    if filing_status_id:
        messages.success(request, _("Tax bracket successfully deleted."))
    else:
        messages.error(request, _("Tax bracket not found"))
    return (
        redirect(tax_bracket_list, filing_status_id=filing_status_id)
        if filing_status_id
        else HttpResponseRedirect(request.META.get("HTTP_REFERER", "/"))
    )


@login_required
@hx_request_required
@permission_required("payroll.change_filingstatus")
def update_py_code(request, pk):
    """
    Ajax method to update python code of filing status.

    Gated on change_filingstatus, not change_taxbracket. This endpoint stores
    Python that the payroll engine later executes, so it was previously
    possible to install executable tax code while holding only the permission
    to edit a tax *bracket* — a narrower, more freely granted role.
    """
    code = request.POST.get("code")
    if not code:
        messages.error(request, _("Missing required parameter"))
        return JsonResponse({"message": "Missing required parameter: code"}, status=400)
    filing = FilingStatus.find(pk)
    if not filing:
        messages.error(request, _("Filing status not found"))
        return JsonResponse({"message": "Filing status not found"}, status=404)

    try:
        validate_tax_code(code)
    except TaxCodeValidationError as exc:
        messages.error(request, _("Invalid tax code"))
        return JsonResponse({"message": str(exc)}, status=400)

    if not filing.python_code == code:
        filing.python_code = code
        filing.save()
        messages.success(request, _("Python code saved successfully!"))
    return JsonResponse({"message": "success"})


@login_required
@hx_request_required
@permission_required("payroll.add_filingstatus")
def tax_pack_picker(request):
    """The 'load a ready-made tax configuration' chooser."""
    loaded = set(FilingStatus.objects.values_list("filing_status", flat=True))
    return render(
        request,
        "payroll/tax/_tax_pack_modal.html",
        {"rows": pack_rows(loaded)},
    )


@require_POST
@login_required
@permission_required("payroll.add_filingstatus")
def load_tax_pack(request):
    """
    Create filing statuses from the chosen ready-made packs.

    Each pack is slabs plus adjustments and no code at all — which is the
    point: the systems people actually run payroll under are expressible as
    configuration, and an admin should start from a correct table rather than
    an empty one.
    """
    keys = request.POST.getlist("packs")
    if not keys:
        messages.error(request, _("Select at least one tax configuration to load."))
        return HorillaRedirect(request, reverse("filing-status-view"))

    created = load_tax_packs(keys)
    if created:
        messages.success(
            request,
            _(
                "Loaded %(count)s tax configuration(s). Check the rates against "
                "the current finance act before anyone is paid by them."
            )
            % {"count": len(created)},
        )
    else:
        messages.info(request, _("Those tax configurations are already loaded."))
    return HorillaRedirect(request, reverse("filing-status-view"))


@login_required
@permission_required("payroll.change_filingstatus")
def filing_status_rules(request, pk):
    """
    The tax rules page for one filing status: slabs, adjustments, formula.

    Everything that decides how much tax this status computes lives here, on
    one full-width page, instead of behind one modal per bracket. The seeded US
    set is 4 statuses x 7 bands = 28 modal round trips; this is one form.

    The slab grid is an inline formset so the table is validated as a whole —
    TaxBracket.clean() only ever compared one row against an unordered queryset,
    so overlaps and gaps both got through, and a gap silently under-taxes.
    """
    filing_status = FilingStatus.find(pk)
    if not filing_status:
        messages.error(request, _("Filing status not found"))
        return HorillaRedirect(request)

    if request.method == "POST":
        rules_form = FilingStatusTaxRulesForm(request.POST, instance=filing_status)
        bracket_formset = TaxBracketFormSet(request.POST, instance=filing_status)
        if rules_form.is_valid() and bracket_formset.is_valid():
            rules_form.save()
            bracket_formset.save()
            messages.success(request, _("Tax rules saved."))
            return HorillaRedirect(
                request, reverse("filing-status-rules", kwargs={"pk": filing_status.pk})
            )
    else:
        rules_form = FilingStatusTaxRulesForm(instance=filing_status)
        bracket_formset = TaxBracketFormSet(instance=filing_status)

    return render(
        request,
        "payroll/tax/filing_status_rules.html",
        {
            "filing_status": filing_status,
            "rules_form": rules_form,
            "bracket_formset": bracket_formset,
        },
    )


@login_required
@hx_request_required
@permission_required("payroll.view_filingstatus")
def preview_filing_status_tax(request, pk):
    """
    What would this filing status charge on a given yearly income?

    Runs the real bracket walk and the real adjustments — the same code
    calculate_taxable_amount uses — so the number shown is the number a payslip
    would produce. A preview that computes its own way agrees with payroll
    right up until the day it doesn't.

    Nothing is saved, and no payslip is created.
    """
    filing_status = FilingStatus.find(pk)
    if not filing_status:
        return JsonResponse(
            {"ok": False, "error": _("Filing status not found")}, status=404
        )

    try:
        yearly_income = float(request.POST.get("yearly_income") or 0)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": _("Enter a number for the yearly income.")},
            status=400,
        )

    try:
        breakdown = preview_yearly_tax(filing_status, yearly_income)
    except TaxComputationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse({"ok": True, **breakdown})


@login_required
@hx_request_required
@permission_required("payroll.change_filingstatus")
def test_py_code(request):
    """
    Run a tax formula against a sample income and report what it returns.

    This is the preview that replaces the onecompiler.com iframe. The iframe
    ran the code in a third-party sandbox against whatever the admin typed
    there, which told them nothing about what *this* system would compute —
    and shipped the employer's tax formula to another company to find out.

    This runs the real ``run_tax_formula``: the same validator, the same
    restricted builtins, the same timeout, the same entry point that payroll
    itself calls. So a formula that previews cleanly here is a formula that
    will not fail at payslip time, and the error text an admin sees while
    editing is the error text that would otherwise have blocked a payroll run.

    Nothing is saved.
    """
    code = request.POST.get("code") or ""
    raw_income = request.POST.get("sample_income") or "0"
    try:
        sample_income = float(raw_income)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": _("Sample income must be a number.")}, status=400
        )

    try:
        result = run_tax_formula(code, sample_income)
    except TaxCodeValidationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except TaxFormulaTimeout as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001 - the formula's own error is the answer
        return JsonResponse(
            {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=400
        )

    if not isinstance(result, (int, float)) or isinstance(result, bool):
        return JsonResponse(
            {
                "ok": False,
                "error": _("The formula returned %(value)r, which is not a number.")
                % {"value": result},
            },
            status=400,
        )
    return JsonResponse(
        {"ok": True, "sample_income": sample_income, "result": round(float(result), 2)}
    )
