"""
Which components apply to one employee, edited from their contract.

A component reaches an employee through ``specific_employees``; a salary
structure is only what puts them there. So this edits membership of that M2M
and nothing else — never the component itself, which is shared. Changing
"HRA 50%" from one contract would change it for everyone on it, and the person
doing it would have no way to see that from here.

Three of the four routes a component can take are therefore untouchable here:
one that applies to every active employee, or by condition, is not this
contract's to decide, and switching it off for one person means an exclusion on
the component rather than a membership change. The form says so rather than
offering a tick that would not hold.
"""

from django.contrib import messages
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from horilla.decorators import hx_request_required, login_required, permission_required
from horilla.http.response import HorillaRedirect
from payroll.models.models import Allowance, Contract, Deduction, SalaryStructure


def _rows_for(contract):
    """
    Everything tickable, with its current state.

    Both what already applies and what could — one list, because "add this"
    and "remove that" are the same decision and splitting them into two
    screens makes you hold the difference in your head.
    """
    applied = {(row["kind"], row["pk"]): row for row in contract.component_rows}

    rows = []
    for model, kind in ((Allowance, "allowance"), (Deduction, "deduction")):
        queryset = (
            model.objects.exclude(is_system=True)
            .exclude(only_show_under_employee=True)
            .order_by("sequence", "pk")
        )
        for component in queryset:
            current = applied.get((kind, component.pk))
            rows.append(
                {
                    "component": component,
                    "kind": kind,
                    "pk": component.pk,
                    "checked": current is not None,
                    "locked": current is not None and not current["can_toggle"],
                    "source_label": current["source_label"] if current else "",
                    "standard": False,
                }
            )

        # The standard pay items, on and locked. Loss of pay, a loan, a fine:
        # they reach this employee when the thing happens, not because anyone
        # ticked them, so they are shown rather than offered. Listing them is
        # the difference between "these are the components you chose" and
        # "this is what can reach the payslip" -- and the second is the
        # question someone opens this to ask.
        for template in (
            model.objects.entire().filter(is_system=True).order_by("sequence", "pk")
        ):
            rows.append(
                {
                    "component": template,
                    "kind": kind,
                    "pk": template.pk,
                    "checked": True,
                    "locked": True,
                    "source_label": _("Standard, always on"),
                    "standard": True,
                }
            )
    return rows


@login_required
@hx_request_required
@permission_required("payroll.change_contract")
def contract_components(request, pk):
    """Tick the components that apply to this contract's employee."""
    contract = Contract.objects.filter(pk=pk).first()
    if contract is None:
        return HorillaRedirect(request, "/payroll/view-contract/")

    if request.method != "POST":
        return render(
            request,
            "payroll/contract/components_modal.html",
            {"contract": contract, "rows": _rows_for(contract)},
        )

    employee = contract.employee_id
    wanted = set(request.POST.getlist("components"))
    added = removed = 0

    for row in _rows_for(contract):
        # A component applying to everyone, or by condition, is decided by the
        # component. Skipped rather than obeyed: the tick was disabled on the
        # form, so a value for it can only have been forged or left stale.
        if row["locked"]:
            continue

        token = f"{row['kind']}:{row['pk']}"
        should_apply = token in wanted
        if should_apply and not row["checked"]:
            row["component"].specific_employees.add(employee)
            added += 1
        elif not should_apply and row["checked"]:
            row["component"].specific_employees.remove(employee)
            removed += 1

    if added or removed:
        messages.success(
            request,
            _("%(added)s added, %(removed)s removed for %(employee)s.")
            % {"added": added, "removed": removed, "employee": employee},
        )
    else:
        messages.info(request, _("Nothing changed."))

    return HorillaRedirect(request, "/payroll/view-contract/")


@login_required
@hx_request_required
@permission_required("payroll.change_contract")
def bulk_contract_components(request):
    """
    Assign a structure, or add and remove components, across many contracts.

    Both in one place because they are two ways of doing the same job and the
    difference matters: a structure is a named set someone maintains, so
    assigning it keeps those employees in step with it afterwards. Adding
    components directly does not — it is a one-off, and nothing later will
    remember why those particular people have that particular component.
    Worth saying on the form rather than leaving to be discovered.
    """
    ids = request.POST.getlist("instance_ids") or request.GET.getlist("instance_ids")
    contracts = Contract.objects.filter(pk__in=ids)

    if request.method != "POST" or "action" not in request.POST:
        return render(
            request,
            "payroll/contract/bulk_components_modal.html",
            {
                "contracts": contracts,
                "ids": ids,
                "structures": SalaryStructure.objects.all(),
                "allowances": Allowance.objects.exclude(is_system=True).exclude(
                    only_show_under_employee=True
                ),
                "deductions": Deduction.objects.exclude(is_system=True).exclude(
                    only_show_under_employee=True
                ),
            },
        )

    if not contracts.exists():
        messages.error(request, _("No contracts were selected."))
        return HorillaRedirect(request, "/payroll/view-contract/")

    action = request.POST.get("action")

    if action == "structure":
        structure = SalaryStructure.objects.filter(
            pk=request.POST.get("salary_structure")
        ).first()
        if structure is None:
            messages.error(request, _("Choose a salary structure."))
            return HorillaRedirect(request, "/payroll/view-contract/")

        for contract in contracts:
            # set_salary_structure, not a direct assignment: it is what syncs
            # the employee onto the structure's components, which is the whole
            # point of assigning one.
            contract.set_salary_structure(structure)
        messages.success(
            request,
            _("%(count)s contract(s) moved to %(structure)s.")
            % {"count": contracts.count(), "structure": structure},
        )
        return HorillaRedirect(request, "/payroll/view-contract/")

    employees = [contract.employee_id for contract in contracts]
    chosen = request.POST.getlist("components")
    if not chosen:
        messages.error(request, _("Choose at least one component."))
        return HorillaRedirect(request, "/payroll/view-contract/")

    removing = action == "remove"
    touched = 0
    for token in chosen:
        kind, _sep, pk = token.partition(":")
        model = Allowance if kind == "allowance" else Deduction
        component = model.objects.filter(pk=pk).first()
        if component is None:
            continue
        if removing:
            component.specific_employees.remove(*employees)
        else:
            component.specific_employees.add(*employees)
        touched += 1

    messages.success(
        request,
        _("%(components)s component(s) %(verb)s %(count)s employee(s).")
        % {
            "components": touched,
            "verb": _("removed from") if removing else _("added to"),
            "count": len(employees),
        },
    )
    return HorillaRedirect(request, "/payroll/view-contract/")
