"""
Endpoints backing the salary-component form's live previews.

The builder is a tap-to-build interface — component chips, operator buttons, a
value box — rather than a text field the user types syntax into. These serve
the two things it cannot work out on its own: which codes exist, and what the
expression comes to.
"""

from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _

from horilla.decorators import hx_request_required, login_required, permission_required
from payroll.methods.component_formula import (
    ComponentFormulaError,
    run_component_formula,
)
from payroll.models.models import Allowance, Deduction

# Codes the engine seeds itself, offered alongside the components an admin has
# defined. Without these the builder could not express "a percentage of gross".
ENGINE_CODES = [
    ("BASIC", _("Basic pay")),
    # In a Gross Up structure this is gross as far as it has been built when
    # the component runs; in a CTC Down structure it is the whole wage, known
    # up front. Only the second makes "50% of gross" mean what it sounds like,
    # which is why the label says where it is dependable.
    ("GROSS", _("Gross pay (the full wage in a CTC Down structure)")),
    ("CTC", _("Cost to company (CTC Down structures)")),
    # Attendance for the period, exposed so a formula can react to it directly
    # -- "(BASIC - LOP) * 0.12" reproduces the old deduct_leave_from_basic_pay
    # behaviour for just the one component that asks for it, now that Loss of
    # Pay itself is always a separate, un-cascaded deduction.
    ("PAID_DAYS", _("Paid days in the period")),
    ("UNPAID_DAYS", _("Unpaid days in the period")),
    ("LOP", _("Loss of pay (the amount, not the day count)")),
    # Service measured to the end of the pay period, as years with decimals
    # (6.4). round(YEARS_OF_SERVICE) gives whole years. Gratuity and other
    # service-based entitlements read these.
    ("YEARS_OF_SERVICE", _("Years of service (from the joining date)")),
    ("YEARS_OF_CONTRACT", _("Years of the active contract (from its start date)")),
]


def available_codes(exclude_pk=None, exclude_model=None):
    """
    Every code a formula may reference, as (code, label) pairs.

    A component is excluded from its own list: a formula that refers to itself
    would either read a stale value or nothing at all, depending on ordering,
    and neither is something to offer.
    """
    rows = [
        {"code": code, "label": str(label), "engine": True}
        for code, label in ENGINE_CODES
    ]

    for model in (Allowance, Deduction):
        queryset = (
            model.objects.exclude(code="")
            # A standard pay item holds no amount of its own -- the loan
            # schedule or the attendance record decides it -- so a percentage
            # of one would be a percentage of zero.
            .exclude(is_system=True)
            # Claims, advances and loans are generated for one employee each,
            # so they are not components anyone configures or can reference.
            .exclude(only_show_under_employee=True).order_by("sequence", "pk")
        )
        # Loan and fine instalments are one auto-generated Deduction per due
        # date, so a single loan puts a dozen near-identical rows in here and
        # buries the components someone might actually reference. They are also
        # not configuration: they belong to one employee's repayment schedule,
        # and nothing sensible is a percentage of one.
        if hasattr(model, "is_installment"):
            queryset = queryset.filter(is_installment=False)
        if exclude_pk and model is exclude_model:
            queryset = queryset.exclude(pk=exclude_pk)
        for code, title in queryset.values_list("code", "title"):
            if any(row["code"] == code for row in rows):
                continue
            # The title leads: codes are derived plumbing, and the person
            # building a formula is picking "House Rent Allowance", not
            # remembering HOUSE_RENT_ALLOWANCE.
            rows.append({"code": code, "label": title, "engine": False})
    return rows


def sample_context(sample_basic):
    """
    Plausible amounts for every code, for the live preview.

    This is an estimate and is labelled as one on screen. Producing the exact
    figure would mean running a full payslip for a specific employee in a
    specific period, which is what the payslip itself is for; the point here is
    to show the shape of the answer while the formula is being written.
    """
    # Illustrative attendance for the preview only -- a real payslip's day
    # counts come from the employee's actual period, which this has no way to
    # know without one. 30 calendar days, 2 unpaid, priced against the sample
    # basic the same way calendar-day proration prices a real one.
    sample_unpaid_days = 2
    sample_paid_days = 28
    sample_lop = (
        round(sample_basic / 30 * sample_unpaid_days, 2) if sample_basic else 0.0
    )
    context = {
        "BASIC": sample_basic,
        "GROSS": sample_basic,
        "CTC": sample_basic,
        "PAID_DAYS": sample_paid_days,
        "UNPAID_DAYS": sample_unpaid_days,
        "LOP": sample_lop,
        # Illustrative, like the attendance above.
        "YEARS_OF_SERVICE": 6.4,
        "YEARS_OF_CONTRACT": 2.5,
    }

    # Evaluation order, so a component that refers to an earlier one resolves
    # against the sample rather than against a zero standing in for it.
    for model in (Allowance, Deduction):
        for component in (
            model.objects.exclude(code="")
            .exclude(is_system=True)
            # Claims, advances and loans are generated for one employee each,
            # so they are not components anyone configures or can reference.
            .exclude(only_show_under_employee=True)
            .order_by("sequence", "pk")
        ):
            if component.code in context:
                continue
            if component.is_fixed:
                context[component.code] = float(component.amount or 0)
            elif component.based_on == "component":
                # Any known code, not only BASIC: percentages of gross are the
                # whole reason CTC Down structures exist, and previewing them
                # as 0 would make a correct formula look broken.
                base = context.get(
                    (component.percentage_of_code or "").strip().upper(), 0.0
                )
                context[component.code] = base * float(component.rate or 0) / 100
            elif component.based_on == "basic_pay":
                context[component.code] = (
                    sample_basic * float(component.rate or 0) / 100
                )
            else:
                context[component.code] = 0.0
    return context


@login_required
@permission_required("payroll.view_allowance")
def check_component_code(request):
    """
    Is this code free? Backs the live check under the Code input.

    ``kind`` is allowance or deduction and ``pk`` the component being edited, so it
    may keep its own code. Same rule the form applies on save.
    """
    from payroll.models.models import component_code_taken, component_code_validator

    code = (request.GET.get("code") or "").strip().upper()
    model = Deduction if request.GET.get("kind") == "deduction" else Allowance
    try:
        pk = int(request.GET.get("pk") or 0) or None
    except ValueError:
        pk = None
    if not code:
        return JsonResponse({"ok": True, "message": ""})
    try:
        component_code_validator(code)
    except Exception as exc:
        message = getattr(exc, "messages", [str(exc)])[0]
        return JsonResponse({"ok": False, "message": str(message)})
    if component_code_taken(code, model, pk):
        return JsonResponse(
            {
                "ok": False,
                "message": str(
                    _("The code %(code)s is already used by another component.")
                    % {"code": code}
                ),
            }
        )
    return JsonResponse({"ok": True, "message": str(_("Available"))})


@login_required
@hx_request_required
@permission_required("payroll.view_allowance")
def preview_component_formula(request):
    """Evaluate a formula against sample amounts. Saves nothing."""
    expression = request.POST.get("formula") or ""
    try:
        sample_basic = float(request.POST.get("sample_basic") or 0)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": str(_("Sample basic pay must be a number."))},
            status=400,
        )

    context = sample_context(sample_basic)
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
        }
    )


# Representative periods for the ceiling note. Illustrative on purpose, and
# labelled as such on screen: a real period depends on the company calendar and
# the employee's contract. What is NOT illustrative is the arithmetic — these go
# through the same period_factor the payslip uses, so the note cannot claim a
# figure payroll would not produce.
SAMPLE_PERIODS = [
    (
        _("A whole month"),
        [
            {
                "days": 30,
                "start_date": "2026-04-01",
                "end_date": "2026-04-30",
                "working_days_on_period": 22,
                "working_days_on_month": 22,
            }
        ],
    ),
    (
        _("Joined mid-month (15 days)"),
        [
            {
                "days": 30,
                "start_date": "2026-04-16",
                "end_date": "2026-04-30",
                "working_days_on_period": 11,
                "working_days_on_month": 22,
            }
        ],
    ),
    (
        _("A 10 day period"),
        [
            {
                "days": 30,
                "start_date": "2026-04-01",
                "end_date": "2026-04-10",
                "working_days_on_period": 8,
                "working_days_on_month": 22,
            }
        ],
    ),
]


def limit_note_rows(ceiling, basis):
    """
    What a ceiling comes to over a few example periods.

    Shared by preview_maximum_unit (the live AJAX recompute the form calls on
    every edit) and component_layout.form_context (which renders the same
    thing server-side for the component form's own initial load) -- one real
    place doing the arithmetic, so a form being edited shows the exact same
    figures start to finish instead of a placeholder that then jumps to the
    AJAX endpoint's own answer a moment later.
    """
    from payroll.methods.proration import FULL_PERIOD, period_factor

    rows = [
        {
            "label": str(label),
            "factor": round(period_factor(day_dict, basis), 4),
            "amount": round(ceiling * period_factor(day_dict, basis), 2),
        }
        for label, day_dict in SAMPLE_PERIODS
    ]
    return {
        "flat": basis == FULL_PERIOD or not basis,
        "ceiling": round(ceiling, 2),
        "rows": rows,
    }


@login_required
@hx_request_required
@permission_required("payroll.view_allowance")
def preview_maximum_unit(request):
    """
    What a ceiling comes to over a few example periods. Saves nothing.

    The field was on the form for a long time with the scaling commented out,
    so "For working days on month" described something the engine did not do.
    Showing the worked figures is how that stays honest: if the arithmetic ever
    stops matching the label again, the note says so.
    """
    try:
        ceiling = float(request.POST.get("maximum_amount") or 0)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": str(_("The maximum must be a number."))},
            status=400,
        )

    basis = (request.POST.get("maximum_unit") or "").strip()
    return JsonResponse({"ok": True, **limit_note_rows(ceiling, basis)})


# Where "Add from library" can send someone afterwards. An allowlist rather
# than trusting a posted URL, so the `next` field cannot be pointed off-site.
LIBRARY_RETURN_TO = {
    "allowance": "view-allowance",
    "deduction": "view-deduction",
    "settings": "payroll-settings-view",
}


@login_required
@hx_request_required
@permission_required("payroll.add_allowance")
@permission_required("payroll.add_deduction")
def component_library_picker(request):
    """The "start from a ready-made component" chooser."""
    from django.shortcuts import render

    from payroll.component_library import library_rows
    from payroll.models.models import Allowance, Deduction

    titles = set(Allowance.objects.values_list("title", flat=True))
    titles |= set(Deduction.objects.values_list("title", flat=True))
    return render(
        request,
        "payroll/component/_library_modal.html",
        {
            "rows": library_rows(titles),
            # Which page opened it, so loading returns there instead of always
            # landing on Allowances.
            "return_to": request.GET.get("from", "allowance"),
        },
    )


@login_required
@permission_required("payroll.add_allowance")
@permission_required("payroll.add_deduction")
def load_component_library(request):
    """
    Create the chosen components from the library.

    They are ordinary Allowances and Deductions afterwards, editable like any
    other — a starting point rather than something managed from here. The rates
    are the statutory or conventional ones at the time of writing, which is why
    the message says to check them.
    """
    from django.contrib import messages
    from django.urls import reverse

    from horilla.http.response import HorillaRedirect
    from payroll.component_library import load_components

    back = reverse(
        LIBRARY_RETURN_TO.get(request.POST.get("return_to"), "view-allowance")
    )

    if request.method != "POST":
        return HorillaRedirect(request, back)

    keys = request.POST.getlist("components")
    if not keys:
        messages.error(request, _("Select at least one component to load."))
        return HorillaRedirect(request, back)

    created = load_components(keys)
    if created:
        messages.success(
            request,
            _(
                "Created %(count)s component(s). Check the rates and the bases "
                "against your own rules before anyone is paid by them."
            )
            % {"count": len(created)},
        )
    else:
        messages.info(request, _("Those components already exist."))
    return HorillaRedirect(request, back)


@login_required
@permission_required("payroll.view_allowance")
def employee_pick_rows(request):
    """
    Active employees, a page at a time, for the employee picker on a component's form.

    ``?q=`` searches name, badge id and department; ``?department=``, ``?job_position=`` and
    ``?job_role=`` narrow it to one of each. ``?ids=1`` answers with every matching id instead,
    for the header box that picks them all. The next page number travels in X-Next-Page, as it
    does for the applies table, and X-Column names the group column the rows show.
    """
    from django.core.paginator import Paginator
    from django.db.models import Q
    from django.http import HttpResponse
    from django.template.loader import render_to_string

    from employee.models import Employee

    query = (request.GET.get("q") or "").strip()
    employees = (
        Employee.objects.filter(is_active=True)
        .select_related(
            "employee_work_info__department_id",
            "employee_work_info__job_position_id",
            "employee_work_info__job_role_id",
        )
        .order_by("employee_first_name", "employee_last_name", "pk")
    )
    if query:
        employees = employees.filter(
            Q(employee_first_name__icontains=query)
            | Q(employee_last_name__icontains=query)
            | Q(badge_id__icontains=query)
            | Q(employee_work_info__department_id__department__icontains=query)
        )
    column = "department"
    for name in ("department", "job_position", "job_role"):
        value = request.GET.get(name) or ""
        if value.isdigit():
            employees = employees.filter(
                **{f"employee_work_info__{name}_id": int(value)}
            )
            if name != "department":
                column = name
    if request.GET.get("ids"):
        return JsonResponse(
            {"ids": [str(pk) for pk in employees.values_list("pk", flat=True)]}
        )

    page = Paginator(employees, 25).get_page(request.GET.get("page") or 1)
    html = render_to_string(
        "payroll/component/_employee_pick_rows.html",
        {"rows": page.object_list, "column": column},
        request=request,
    )
    response = HttpResponse(html)
    response["X-Column"] = column
    response["X-Next-Page"] = str(page.next_page_number()) if page.has_next() else ""
    return response


@login_required
@permission_required("payroll.view_allowance")
def component_applies_rows(request):
    """
    Next page of the "who gets it" table on the component form, as table rows.

    The next page number, if any, travels in X-Next-Page so the script can keep
    scrolling without parsing the rows.
    """
    from django.http import HttpResponse
    from django.template.loader import render_to_string

    from payroll.forms.component_layout import applies_page

    model = Deduction if request.GET.get("model") == "deduction" else Allowance
    try:
        pk = int(request.GET.get("pk") or 0) or None
        page = int(request.GET.get("page") or 1)
    except ValueError:
        pk, page = None, 1
    targeted = set()
    everyone = False
    excluded = set()
    group = None
    by = request.GET.get("by") or ""
    if by in ("department", "job_position", "job_role"):
        ids = {
            int(v) for v in (request.GET.get("group") or "").split(",") if v.isdigit()
        }
        group = (by, ids)
    if pk:
        instance = model.objects.get(pk=pk)
        targeted = set(instance.specific_employees.values_list("pk", flat=True))
        everyone = bool(instance.include_active_employees) and group is None
        excluded = set(instance.exclude_employees.values_list("pk", flat=True))
    if request.GET.get("ids"):
        # Everyone the search matches who is not already on a structure, for the
        # header box to tick in one go.
        rows, _more, _covered = applies_page(
            model, pk, targeted, None, request.GET.get("q", "")
        )
        return JsonResponse(
            {"ids": [str(r["pk"]) for r in rows if r["via"] != "structure"]}
        )
    rows, has_next, _covered = applies_page(
        model,
        pk,
        targeted,
        page,
        request.GET.get("q", ""),
        everyone=everyone,
        excluded=excluded,
        group=group,
    )
    html = render_to_string(
        "payroll/component/_applies_rows.html",
        {"rows": rows, "editable": True},
        request=request,
    )
    response = HttpResponse(html)
    response["X-Next-Page"] = str(page + 1) if has_next else ""
    return response
