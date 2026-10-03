"""
A worked example for a salary structure.

The point of this is that it is not a second implementation. It calls the same
strategy functions ``calculate_allowance`` dispatches to, in the same order,
through the same ``compute_limit`` and ``flat_amount`` and the same condition
gate, and it runs deductions through the real pre-tax and post-tax passes. So a
figure shown here is a figure payroll would produce.

Only the inputs are invented: a sample wage and a plain 30-calendar-day month
with 22 working days in it, because a real period depends on an employee's
contract and the company calendar. The panel says so.

Two things it does not show, and says it does not show:

  * income tax — unless a filing status is chosen for the example. A contract
    carries one in real life; here it is picked, and the tax is worked out by
    the same compute_yearly_tax a payslip uses.
  * components that measure attendance — overtime, shift and work-type rates
    need a real employee's hours. Reported per-line rather than guessed at.

Everything is read-only. No Payslip, no Contract, nothing is saved.
"""

from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _

from horilla.decorators import hx_request_required, login_required, permission_required
from payroll.methods.component_engine import accumulate, new_context, record
from payroll.methods.methods import compute_yearly_taxable_amount
from payroll.methods.proration import flat_amount
from payroll.methods.tax_calc import TaxComputationError, compute_yearly_tax
from payroll.models.models import FilingStatus, SalaryStructure

# A month with nothing unusual about it: 30 calendar days, 22 of them working.
# Calendar days lead because that is the default proration basis, so the example
# and the default setting describe the same thing.
SAMPLE_CALENDAR_DAYS = 30
SAMPLE_WORKING_DAYS = 22

# Strategies that cannot be evaluated without a real employee's attendance.
NEEDS_ATTENDANCE = {
    "attendance",
    "shift_id",
    "work_type_id",
    "overtime",
    "week_off_overtime",
    "holiday_overtime",
    "children",
}


def sample_day_dict(lop_days=0):
    """
    One month, with any loss-of-pay days taken off both day counts.

    Carries the same keys ``months_between_range`` produces, because the
    strategies and ``period_factor`` read them by name.
    """
    worked = max(SAMPLE_WORKING_DAYS - lop_days, 0)
    calendar = max(SAMPLE_CALENDAR_DAYS - lop_days, 0)
    return [
        {
            "month": 4,
            "year": 2026,
            "days": SAMPLE_CALENDAR_DAYS,
            "start_date": "2026-04-01",
            # The slice shortens with LOP so a calendar-days basis prorates too;
            # period_factor measures this span against `days`.
            "end_date": f"2026-04-{calendar:02d}" if calendar else "2026-04-01",
            "working_days_on_period": worked,
            "working_days_on_month": SAMPLE_WORKING_DAYS,
            "per_day_amount": 0.0,
        }
    ]


def _strategy_kwargs(component, context, day_dict, basic_pay, gross_pay):
    return {
        "employee": None,
        "component": component,
        "basic_pay": basic_pay,
        "gross_pay": gross_pay,
        "day_dict": day_dict,
        "component_context": context,
        "start_date": None,
        "end_date": None,
    }


def _amount_for(component, context, day_dict, basic_pay, gross_pay):
    """One component's amount, through the engine's own strategy for it."""
    from payroll.methods.payslip_calc import calculation_mapping

    if component.is_fixed:
        return flat_amount(component, day_dict), None

    based_on = component.based_on or ""
    if based_on in NEEDS_ATTENDANCE:
        return None, str(_("Needs the employee's attendance"))

    strategy = calculation_mapping.get(based_on)
    if strategy is None:
        return None, str(_("Not configured"))

    try:
        amount = strategy(
            **_strategy_kwargs(component, context, day_dict, basic_pay, gross_pay)
        )
    except Exception as exc:  # a formula that does not evaluate, say
        return None, str(exc) or str(_("Could not be worked out"))
    return amount, None


def _head(key, label, formula, terms, amount, note=None):
    """
    One payslip head: its name, the equation in words, and the equation with
    this example's figures in it.

    Both forms, because either alone leaves a question. The words say what the
    head means in general; the substitution says where these particular numbers
    came from, which is what someone checking a structure is actually asking.
    """
    return {
        "key": key,
        "label": str(label),
        "formula": str(formula),
        "terms": [
            {"label": str(term), "amount": round(float(value), 2), "sign": sign}
            for term, value, sign in terms
        ],
        "amount": round(float(amount), 2),
        "note": note,
    }


def _line(row, amount, note, employer=None):
    return {
        "code": row["code"],
        "title": row["title"],
        "calculation": row["calculation"],
        "amount": round(float(amount), 2) if amount is not None else None,
        "employer": round(float(employer), 2) if employer else None,
        "note": note,
    }


@login_required
@hx_request_required
@permission_required("payroll.view_salarystructure")
def preview_salary_structure(request, pk):
    """Run the structure against sample figures. Saves nothing."""
    structure = SalaryStructure.objects.filter(pk=pk).first()
    if structure is None:
        return JsonResponse(
            {"ok": False, "error": str(_("Structure not found."))}, status=404
        )

    def number(name, default=0.0):
        try:
            return float(request.POST.get(name) or default)
        except (TypeError, ValueError):
            return None

    monthly_ctc = number("ctc")
    contract_basic = number("basic")
    if monthly_ctc is None or contract_basic is None:
        return JsonResponse(
            {"ok": False, "error": str(_("The sample figures must be numbers."))},
            status=400,
        )
    try:
        lop_days = max(int(number("lop_days") or 0), 0)
    except (TypeError, ValueError):
        lop_days = 0

    day_dict = sample_day_dict(lop_days)
    worked = day_dict[0]["working_days_on_period"]
    ratio = worked / SAMPLE_WORKING_DAYS if SAMPLE_WORKING_DAYS else 0.0

    rows = structure.component_rows
    flagged = next(
        (
            r["component"]
            for r in rows
            if r["kind"] == "earning" and getattr(r["component"], "is_basic_pay", False)
        ),
        None,
    )

    ctc_down = (structure.structure_mode or "gross_up") == "ctc_down"
    # Prorated the way compute_salary_on_period prorates a monthly figure: by
    # working days. Done here rather than by calling it, because that function
    # needs a saved Contract; the arithmetic is the same.
    period_ctc = monthly_ctc * ratio
    period_basic = contract_basic * ratio

    if ctc_down:
        # The package is divided up and basic comes out of it, so a basic typed
        # in here would be a second, unrelated figure.
        context = new_context(0.0, total_gross=period_ctc)
        basic_pay = 0.0
    else:
        # Basic comes from the contract unless an earning is marked as basic
        # pay — the same precedence a real run applies.
        seed = 0.0 if flagged is not None and not contract_basic else period_basic
        context = new_context(seed)
        basic_pay = seed

    # The flagged earning is skipped when the contract states basic, exactly as
    # payroll_run skips it, so the example cannot show a second basic.
    skip = flagged if (flagged is not None and basic_pay > 0) else None

    earning_lines = []
    earnings_total = 0.0
    # Tracked separately because the heads below are the engine's, term for
    # term: calculate_taxable_gross_pay takes non-taxable earnings off gross,
    # and payroll_run adds the three deduction buckets up separately.
    non_taxable_total = 0.0

    # Basic pay as its own line when it comes from the contract rather than from
    # a component. Without it the earnings read "HRA 1,125" above a gross of
    # 26,125 and the missing 25,000 has no visible origin — the real payslip
    # shows basic as the first row of the same table for that reason, and
    # The v2 engine emitted the same synthetic line.
    if not ctc_down and period_basic and flagged is None:
        earning_lines.append(
            {
                "code": "BASIC",
                "title": str(_("Basic Pay")),
                "calculation": str(_("From the contract")),
                "amount": round(period_basic, 2),
                "employer": None,
                "note": None,
            }
        )

    for row in rows:
        if row["kind"] != "earning":
            continue
        component = row["component"]
        if skip is not None and component.pk == skip.pk:
            earning_lines.append(
                _line(row, None, str(_("Not paid — the contract states basic pay")))
            )
            continue
        amount, note = _amount_for(
            component, context, day_dict, basic_pay, context.get("GROSS", 0.0)
        )
        if amount is not None:
            record(context, component, amount)
            accumulate(context, amount)
            earnings_total += float(amount)
            if not getattr(component, "is_taxable", False):
                non_taxable_total += float(amount)
        earning_lines.append(_line(row, amount, note))

    derived_basic = float(context.get("BASIC", 0) or 0)
    if ctc_down or not basic_pay:
        basic_pay = derived_basic
    gross_pay = earnings_total if ctc_down else period_basic + earnings_total
    if not ctc_down and flagged is not None and skip is None:
        # Basic came from the flagged earning, so it is already inside the
        # earnings total and must not be added again.
        gross_pay = earnings_total

    deduction_lines = []
    deductions_total = 0.0
    employer_total = 0.0
    # The engine's three disjoint buckets (payslip_calc filters on exactly these
    # two flags), summed separately because total_deductions is their sum plus
    # income tax.
    pretax_total = 0.0
    tax_component_total = 0.0
    post_tax_total = 0.0
    for row in rows:
        if row["kind"] != "deduction":
            continue
        component = row["component"]
        amount, note = _amount_for(component, context, day_dict, basic_pay, gross_pay)
        employer = None
        if amount is not None:
            record(context, component, amount)
            deductions_total += float(amount)
            if getattr(component, "is_tax", False):
                tax_component_total += float(amount)
            elif getattr(component, "is_pretax", False):
                pretax_total += float(amount)
            else:
                post_tax_total += float(amount)
            rate = getattr(component, "employer_rate", 0) or 0
            if rate:
                employer = float(amount) * float(rate) / 100
                employer_total += employer
        deduction_lines.append(_line(row, amount, note, employer=employer))

    # calculate_taxable_gross_pay, term for term. The non-taxable earnings half
    # was missing here and only the pre-tax deductions were taken off, so a
    # structure with a non-taxable earning previewed more tax than it would
    # actually charge.
    # Floored at zero, as calculate_taxable_gross_pay does: a preview that
    # showed a negative taxable gross where a real payslip shows nought would
    # be a worked example of something that cannot happen.
    taxable_gross = max(0.0, gross_pay - non_taxable_total - pretax_total)

    # ---- loss of pay -------------------------------------------------------
    # Shown among the deductions because that is where a payslip carries it,
    # but NOT added to the total, and the line says so: this preview models a
    # contract with "deduct leave from basic pay" on, where the engine reduces
    # basic pay itself and leaves loss_of_pay_amount at zero. Subtracting it
    # again here would take the same days off twice.
    lop_line = None
    if lop_days:
        full_basic = contract_basic if not ctc_down else monthly_ctc
        lost = float(full_basic) - (period_basic if not ctc_down else period_ctc)
        lop_line = {
            "code": "LOP",
            "title": str(_("Loss of pay")),
            "calculation": str(
                _("%(days)s of %(working)s working days")
                % {"days": lop_days, "working": SAMPLE_WORKING_DAYS}
            ),
            "amount": round(lost, 2),
            "employer": None,
            "note": str(_("Already taken off the pay above, not subtracted again")),
            "informational": True,
        }

    # ---- income tax, if a filing status was picked -------------------------
    # Through compute_yearly_tax, which is the whole of what a filing status
    # means and the only implementation of it — calculate_taxable_amount calls
    # the same function for a real payslip. A preview that worked tax out its
    # own way would agree with payroll right up until the day it did not, about
    # a number people are paid by.
    tax_line = None
    income_tax = 0.0
    filing = None
    filing_pk = request.POST.get("filing_status")
    if filing_pk:
        filing = FilingStatus.objects.filter(pk=filing_pk).first()
    if filing is not None:
        # Which figure the brackets are read against is the filing status's own
        # setting, and it changes the answer substantially — taxing gross
        # rather than taxable gross ignores every pre-tax deduction. It was not
        # said anywhere on the panel, so the tax line carries it now.
        bases = {
            "gross_pay": (gross_pay, _("gross pay")),
            "taxable_gross_pay": (taxable_gross, _("taxable gross pay")),
        }
        base, base_label = bases.get(filing.based_on, (basic_pay, _("basic pay")))

        # Annualised and brought back the way calculate_taxable_amount does it:
        # by calendar days, so a part month is taxed as a part month. Through
        # compute_yearly_taxable_amount as well, because that is the hook a
        # deployment overrides to change the annualisation — skipping it would
        # make the preview disagree with the payslip on exactly the sites that
        # customised it.
        period_days = max(SAMPLE_CALENDAR_DAYS - lop_days, 1)
        yearly_base = compute_yearly_taxable_amount(base, base / period_days * 365)
        try:
            yearly_tax, breakdown = compute_yearly_tax(filing, round(yearly_base, 2))
            period_tax = yearly_tax / 365 * period_days
            tax_line = {
                "code": "TAX",
                "title": str(filing),
                "calculation": str(
                    _("On %(label)s %(base)s → %(yearly)s a year")
                    % {
                        "label": base_label,
                        "base": f"{base:,.2f}",
                        "yearly": f"{yearly_base:,.0f}",
                    }
                ),
                "amount": round(period_tax, 2),
                "employer": None,
                "note": None,
                "base_key": filing.based_on,
                "base_label": str(base_label),
                "base_amount": round(base, 2),
            }
            deductions_total += period_tax
            income_tax = period_tax
        except TaxComputationError as exc:
            tax_line = {
                "code": "TAX",
                "title": str(filing),
                "calculation": "",
                "amount": None,
                "employer": None,
                "note": str(exc),
                "base_key": filing.based_on,
                "base_label": str(base_label),
                "base_amount": round(base, 2),
            }

    # ---- the payslip heads, each with the equation behind it ----------------
    # Written out rather than left as four bare totals. "Gross pay 28,737.50"
    # above "Net pay 25,237.50" does not say which earnings were counted, what
    # taxable gross took off, or why the two differ by more than the deductions
    # listed. Each equation below is the engine's, term for term, from
    # calculate_gross_pay, calculate_taxable_gross_pay and payroll_run's
    # total_deductions — so the panel doubles as documentation of what payroll
    # actually does.
    if ctc_down:
        gross_terms = [(_("All earnings, basic pay among them"), earnings_total, "+")]
        gross_formula = _("Sum of every earning")
    elif flagged is not None and skip is None:
        gross_terms = [(_("All earnings, basic pay among them"), earnings_total, "+")]
        gross_formula = _("Sum of every earning, basic pay included")
    else:
        gross_terms = [
            (_("Basic pay, from the contract"), period_basic, "+"),
            (_("Other earnings"), earnings_total, "+"),
        ]
        gross_formula = _("Basic pay + every other earning")

    # Deductions can total more than the earnings they come out of, and the
    # engine caps them at gross rather than paying a negative amount. The
    # preview has to apply the same rule or the worked example disagrees with
    # the payslip it is meant to explain.
    capped_deductions = min(deductions_total, gross_pay)

    heads = [
        _head("gross_pay", _("Gross pay"), gross_formula, gross_terms, gross_pay),
        _head(
            "taxable_gross",
            _("Taxable gross"),
            _("Gross pay − non-taxable earnings − pre-tax deductions"),
            [
                (_("Gross pay"), gross_pay, "+"),
                (_("Non-taxable earnings"), non_taxable_total, "−"),
                (_("Pre-tax deductions"), pretax_total, "−"),
            ],
            taxable_gross,
            note=str(_("What a filing status set to “taxable gross pay” reads.")),
        ),
        _head(
            "total_deductions",
            _("Total deductions"),
            _("Pre-tax + tax components + post-tax + income tax"),
            [
                (_("Pre-tax deductions"), pretax_total, "+"),
                (_("Tax components"), tax_component_total, "+"),
                (_("Post-tax deductions"), post_tax_total, "+"),
                (_("Income tax"), income_tax, "+"),
            ],
            deductions_total,
            # Said rather than quietly dropped: a payslip carries loss of pay as
            # its own deduction line, while here the days shorten the period and
            # the components prorate into it.
            note=(
                str(
                    _(
                        "Loss of pay is listed with the deductions but not added "
                        "here: this example reduces the pay itself, as a contract "
                        "set to deduct leave from basic pay does, so the days are "
                        "already gone from gross."
                    )
                )
                if lop_days
                else None
            ),
        ),
        _head(
            "net_pay",
            _("Net pay"),
            _("Gross pay − total deductions"),
            [
                (_("Gross pay"), gross_pay, "+"),
                (_("Total deductions"), capped_deductions, "−"),
            ],
            gross_pay - capped_deductions,
        ),
    ]

    counted = earnings_total + employer_total
    payload = {
        "heads": heads,
        "taxable_gross": round(taxable_gross, 2),
        "pretax_total": round(pretax_total, 2),
        "post_tax_total": round(post_tax_total, 2),
        "tax_component_total": round(tax_component_total, 2),
        "non_taxable_total": round(non_taxable_total, 2),
        "ok": True,
        "mode": "ctc_down" if ctc_down else "gross_up",
        "needs_basic_input": flagged is None,
        "lop_days": lop_days,
        "worked_days": worked,
        "working_days": SAMPLE_WORKING_DAYS,
        "calendar_days": SAMPLE_CALENDAR_DAYS,
        "basic": round(basic_pay, 2),
        "earning_lines": earning_lines,
        "deduction_lines": deduction_lines,
        "earnings_total": round(earnings_total, 2),
        "gross_pay": round(gross_pay, 2),
        "deductions_total": round(capped_deductions, 2),
        "deductions_uncapped": round(deductions_total, 2),
        "deductions_not_taken": round(deductions_total - capped_deductions, 2),
        "lop_line": lop_line,
        "tax_line": tax_line,
        "tax_included": tax_line is not None and tax_line["amount"] is not None,
        "employer_total": round(employer_total, 2),
        "net_pay": round(gross_pay - capped_deductions, 2),
    }

    if period_ctc:
        # What the structure accounts for against what it was told to cover.
        # Worth showing in both modes: under CTC Down a gap is usually a missing
        # balance earning, and under Gross Up it answers "does this structure
        # add up to the package I mean to offer?".
        payload["ctc_counted"] = round(counted, 2)
        payload["ctc_target"] = round(period_ctc, 2)
        payload["ctc_gap"] = round(period_ctc - counted, 2)
        payload["ctc_reconciles"] = abs(period_ctc - counted) < 0.05

    return JsonResponse(payload)


@login_required
@hx_request_required
@permission_required("payroll.view_salarystructure")
def salary_structure_employees(request, pk):
    """
    The Employees tab, fetched when it is first opened.

    Loaded on demand rather than with the modal because it is the one panel
    whose cost scales with the company: a structure everybody is on resolves a
    contract and a basic-pay source per person, and the modal opens on the
    Components tab, so most of that work was for a panel nobody had asked for.
    The summary bar still carries the counts, which are two cheap queries.
    """
    from django.shortcuts import render

    structure = SalaryStructure.objects.filter(pk=pk).first()
    if structure is None:
        return render(
            request,
            "cbv/salary_structure/employees_detail_col.html",
            {"instance": None, "employee_rows": []},
        )

    rows = structure.employee_rows
    return render(
        request,
        "cbv/salary_structure/employees_detail_col.html",
        {
            "instance": structure,
            "employee_rows": rows,
            # Counted from the resolved rows rather than re-queried, so the
            # banner and the flagged rows can never disagree about how many.
            "warned_count": sum(1 for row in rows if row["no_basic"]),
        },
    )
