"""
Overriding a generated payslip's own figures, by hand.

A payslip is not only a computed result — once generated it is a record, and
sometimes the record needs correcting without re-running the whole engine: a
manager waives a fine, HR fixes a fat-fingered bonus, a number was wrong on the
source data and the payslip has already moved past Draft. None of that should
touch the shared Allowance/Deduction definitions everyone else's payslip reads
from — editing here changes the one JSON snapshot this payslip already is,
which is exactly the object `pay_head_data` was always meant to be: what was
decided, for this person, this period.

Every figure a payslip shows lives in one of four places:

  * ``basic_pay``, a scalar on the model.
  * ``federal_tax``, a scalar inside ``pay_head_data`` (shown as "Income Tax").
  * the four deduction buckets: pretax_deductions, post_tax_deductions,
    tax_deductions, net_deductions.
  * ``allowances``.

Editing any of them re-derives gross, total deductions and net the same way
the engine's own final steps do — deductions capped at gross (see
``payroll_run.calculate``), net never negative — so a hand-edited payslip
still reads as one whose own arithmetic works out. Income Tax follows the edit: it is worked out again by the same
``period_tax`` the engine used, from the taxable gross the edit leaves, so the
bracket arithmetic is not duplicated here. It stays an editable line -- a figure
typed into it is kept as typed.

A line can also be *added* here, which is the other half of the same idea:
a one-off allowance or deduction that belongs to this payslip and nothing
else. It is written straight into the snapshot with no Allowance/Deduction row
behind it, so it exists for this period only and cannot leak into anyone's
next payslip -- which is the whole difference from the component library, and
the reason adding one does not mean creating a component first. Its amount can
be worked out by a formula against this payslip's own resolved figures, but
what gets stored is the resulting number: the formula is a calculator, not a
standing rule, and the expression is kept alongside only so the figure can be
traced back to how it was reached.

Two figures can drift out of step for one specific case: a CTC Down payslip's
``basic_pay`` scalar and its flagged earning's own row in ``allowances`` are
two independent pieces of storage that happened to agree at generation time
(see payroll_run.py — the derived figure is written to both). Editing one here
does not update the other. That is a pre-existing storage duplication, not
something this introduces, and is out of scope to fix here.
"""

import re
import uuid

from django.utils.translation import gettext_lazy as _

from payroll.methods.component_formula import (
    ComponentFormulaError,
    run_component_formula,
)

DEDUCTION_BUCKETS = (
    "pretax_deductions",
    "post_tax_deductions",
    "tax_deductions",
    "net_deductions",
)

BASIC_KEY = "basic"
TAX_KEY = "tax"
NEW_LINE_KEY = "new"

# Names that appear in a formula without being a component. Left out of a
# line's dependencies so "min(BASIC, 15000)" is recorded as following BASIC
# and nothing else.
FORMULA_CALLS = {"MIN", "MAX", "ABS", "ROUND"}

# A balance component is "whatever is left of the CTC", so it follows every
# other earning at once rather than one named component. The marker says that
# without pretending to list them.
BALANCE_DEPENDS_ON_EVERYTHING = "*"

# The engine figures a component can be a percentage of, and the context key
# each one is held under. Taxable gross and net are deliberately absent: one
# needs the tax engine and the other is not known until every deduction has
# run, so a line based on either keeps the figure the payslip was generated
# with rather than being moved to a guess.
AGGREGATE_CODES = {
    "basic_pay": "BASIC",
    "gross_pay": "GROSS",
    "ctc": "CTC",
}

# Where a hand-added deduction goes. Of the four buckets this is the only one
# that is not a claim about the line: "pre-tax" and "tax" both say something
# about tax that a one-off line has no business asserting -- nothing here
# recomputes tax -- and "off net pay" survives the cap at gross, which would
# make an added line behave unlike every other one on the form.
NEW_LINE_BUCKET = "post_tax_deductions"


class NewLineError(Exception):
    """A line was asked for but could not be made from what was posted."""


def _line_key(prefix, row, id_field, index):
    """
    A stable key for one stored line.

    Keyed by the id the engine already recorded (``allowance_id`` /
    ``deduction_id``) rather than position, so the form still matches the
    right row if anything reordered between load and save. Position is the
    fallback only for a line saved before ids were recorded on it.
    """
    custom = row.get("custom_id")
    if custom:
        # A line added by hand has no component behind it, so it has no id to
        # be keyed by -- and falling back to position would let it collide
        # with a real row whose id happens to equal that position. The "c"
        # prefix is what keeps the two sets of keys apart.
        return f"{prefix}:c{custom}"
    identity = row.get(id_field)
    return f"{prefix}:{identity if identity is not None else index}"


def _components_on(payslip):
    """
    The Allowance and Deduction rows this payslip's lines came from.

    Two queries for the whole form rather than one per line. entire(): the
    components are being read to explain figures already on this payslip, so a
    company filter here could only hide the explanation, never protect
    anything -- the amounts are on screen either way.
    """
    from payroll.models.models import Allowance, Deduction

    data = payslip.pay_head_data or {}
    allowance_ids = [
        row.get("allowance_id")
        for row in data.get("allowances") or []
        if row.get("allowance_id")
    ]
    basic_id = data.get("basic_pay_component_id")
    if basic_id:
        allowance_ids.append(basic_id)

    deduction_ids = [
        row.get("deduction_id")
        for bucket in DEDUCTION_BUCKETS
        for row in data.get(bucket) or []
        if row.get("deduction_id")
    ]
    return (
        Allowance.objects.entire().in_bulk(allowance_ids),
        Deduction.objects.entire().in_bulk(deduction_ids),
    )


def _depends_on(component):
    """
    The component codes this one's amount is worked out from.

    Empty for a flat amount, and for anything the payslip cannot re-derive
    from the other figures on the form -- an attendance or overtime component
    depends on the timesheet, not on another line, so no amount of editing
    here would move it.
    """
    if component is None or getattr(component, "is_fixed", False):
        return []

    based_on = getattr(component, "based_on", "") or ""
    if based_on == "component":
        code = (getattr(component, "percentage_of_code", "") or "").strip().upper()
        return [code] if code else []
    if based_on in AGGREGATE_CODES:
        return [AGGREGATE_CODES[based_on]]
    if based_on == "formula":
        expression = (getattr(component, "formula", "") or "").upper()
        return sorted(set(re.findall(r"[A-Z_][A-Z0-9_]*", expression)) - FORMULA_CALLS)
    if based_on == "balance":
        return [BALANCE_DEPENDS_ON_EVERYTHING]
    return []


def _explain(component):
    """
    ``basis`` and ``applies`` for one line, or empty strings when there is
    nothing worth saying.

    Reuses the summaries the salary structure listing already shows, so a
    payslip cannot describe a component differently from the page that
    configures it. A flat amount is skipped: "1,250.00" beside a box reading
    1,250.00 is not an explanation.
    """
    if component is None or getattr(component, "is_fixed", False):
        return "", ""

    from payroll.methods.component_summary import applies_summary, calculation_summary

    basis = str(calculation_summary(component))
    applies = str(applies_summary(component))
    # "Always" is what applies_summary says when a component carries only the
    # default "is this person being paid at all" gate, which is not a
    # condition anybody configured and not worth a line on the form. Both
    # spellings, because the summary is translated and the literal is what a
    # catalogue-less locale falls back to.
    return basis, ("" if applies in {str(_("Always")), "Always"} else applies)


def described_lines(payslip):
    """
    Every line on this payslip, in the shape the edit form needs.

    Returns ``(line, component)`` pairs. The component is what
    ``recompute_dependents`` needs and no caller of ``editable_lines`` does,
    which is why that one hands back the lines alone.

    Each line is a dict: ``key``, ``section`` ("earning"/"deduction"),
    ``title``, ``amount``, ``removable``, plus what the line is and how it was
    worked out -- ``code``, ``basis``, ``applies``, ``depends_on``. Those last
    four are what let the form say "40% of BASIC" beside a figure instead of
    presenting every line as a flat number somebody typed, and what let
    ``recompute_dependents`` move a line when the line it follows changes.

    Basic Pay and Income Tax are never removable — a payslip with no basic pay
    figure or no stated tax reads as "nothing was ever entered", not as
    "entered and it is zero"; typing 0 says the latter, which is always
    available.
    """
    data = payslip.pay_head_data or {}
    allowances, deductions = _components_on(payslip)

    def described(key, section, title, amount, removable, component, **extra):
        basis, applies = _explain(component)
        return component, {
            **extra,
            "key": key,
            "section": section,
            "title": title,
            "amount": amount,
            "removable": removable,
            "code": (getattr(component, "code", "") or "").strip().upper(),
            "basis": basis,
            "applies": applies,
            "depends_on": _depends_on(component),
        }

    basic_component = allowances.get(data.get("basic_pay_component_id"))
    pairs = [
        described(
            BASIC_KEY,
            "earning",
            str(_("Basic Pay")),
            payslip.basic_pay or 0,
            False,
            basic_component,
            taxable=True,
        )
    ]
    # Basic pay is what the others are worked out from, so it is given here
    # rather than derived -- editing it is the whole point of the form, and a
    # line that recomputed itself could not be edited at all.
    pairs[0][1]["depends_on"] = []
    if not pairs[0][1]["code"]:
        pairs[0][1]["code"] = "BASIC"

    for index, row in enumerate(data.get("allowances") or []):
        pairs.append(
            described(
                _line_key("allowance", row, "allowance_id", index),
                "earning",
                row.get("title", ""),
                row.get("amount", 0) or 0,
                True,
                allowances.get(row.get("allowance_id")),
                taxable=bool(row.get("is_taxable", True)),
            )
        )

    pairs.append(
        described(
            TAX_KEY,
            "deduction",
            str(_("Income Tax")),
            data.get("federal_tax", 0) or 0,
            False,
            None,
        )
    )

    for bucket in DEDUCTION_BUCKETS:
        for index, row in enumerate(data.get(bucket) or []):
            pairs.append(
                described(
                    _line_key(bucket, row, "deduction_id", index),
                    "deduction",
                    row.get("title", ""),
                    row.get("amount", 0) or 0,
                    True,
                    deductions.get(row.get("deduction_id")),
                    pretax=bucket == "pretax_deductions",
                )
            )

    return [(line, component) for component, line in pairs]


def editable_lines(payslip):
    """Every line on this payslip, without the component behind it."""
    return [line for line, _component in described_lines(payslip)]


def preview_totals(lines, amounts, removed):
    """
    What Gross, Total deductions and Net would read given these edits.

    Pure arithmetic over figures already on screen — no tax bracket, no
    formula, nothing the engine would need to be called for — which is what
    makes a genuinely live, no-round-trip preview honest rather than a second,
    divergent implementation of the tax engine. The same function backs both
    the live preview and the value actually saved, so what was shown is what
    gets written.
    """
    earnings = 0.0
    deductions = 0.0
    for line in lines:
        key = line["key"]
        if key in removed and line["removable"]:
            continue
        amount = amounts.get(key, line["amount"]) or 0
        if line["section"] == "earning":
            earnings += float(amount)
        else:
            deductions += float(amount)

    gross_pay = round(earnings, 2)
    deduction_before_cap = round(deductions, 2)
    total_deductions = round(min(deduction_before_cap, gross_pay), 2)
    uncovered_deduction = round(deduction_before_cap - total_deductions, 2)
    net_pay = round(max(0.0, gross_pay - total_deductions), 2)

    return {
        "gross_pay": gross_pay,
        "deduction_before_cap": deduction_before_cap,
        "total_deductions": total_deductions,
        "uncovered_deduction": uncovered_deduction,
        "net_pay": net_pay,
    }


def apply_edits(payslip, amounts, removed, new_line=None):
    """
    Write the edits to the payslip: the four buckets, the allowances list,
    Basic Pay and Income Tax, then the derived totals -- using the identical
    arithmetic ``preview_totals`` already showed, so nothing changes between
    what was previewed and what gets saved.

    ``new_line``, when given, is a line with no component behind it (see
    ``parse_new_line``). It counts towards the totals on the same footing as
    every stored line, because from the moment it is saved that is what it is.
    """
    data = dict(payslip.pay_head_data or {})
    pairs = described_lines(payslip)
    lines = [line for line, _component in pairs]
    old_tax = float(data.get("federal_tax", 0) or 0)
    old_basic = float(data.get("basic_pay", payslip.basic_pay) or 0)
    amounts = dict(amounts)
    if new_line:
        lines = lines + [
            {
                "key": NEW_LINE_KEY,
                "section": new_line["section"],
                "title": new_line["title"],
                "amount": new_line["amount"],
                "removable": True,
            }
        ]

    # Income Tax follows the edit. A figure typed into the tax line itself is
    # kept as typed; one left as it was (or not sent) is worked out again from
    # what the payslip now comes to, by the same tax engine that generated it.
    if TAX_KEY not in removed:
        posted = amounts.get(TAX_KEY)
        if posted is None or abs(posted - old_tax) < 0.005:
            earnings_now = preview_totals(lines, amounts, removed)["gross_pay"]
            tax = recomputed_tax(payslip, pairs, amounts, removed, earnings_now)
            if tax is not None:
                if new_line and new_line["section"] == "earning":
                    # A one-off earning is taxable, as an allowance is.
                    tax = recomputed_tax_with_line(
                        payslip, pairs, amounts, removed, earnings_now, new_line
                    )
                amounts[TAX_KEY] = tax
    totals = preview_totals(lines, amounts, removed)

    def rebuild(rows, prefix, id_field):
        kept = []
        for index, row in enumerate(rows or []):
            key = _line_key(prefix, row, id_field, index)
            if key in removed:
                continue
            row = dict(row)
            if key in amounts:
                row["amount"] = amounts[key]
            kept.append(row)
        return kept

    data["allowances"] = rebuild(data.get("allowances"), "allowance", "allowance_id")
    for bucket in DEDUCTION_BUCKETS:
        data[bucket] = rebuild(data.get(bucket), bucket, "deduction_id")

    if new_line:
        row = {
            "custom_id": uuid.uuid4().hex[:8],
            "title": new_line["title"],
            "amount": new_line["amount"],
            # Where the figure came from, kept for the record. Nothing
            # re-evaluates it: the formula was a calculator, and the amount
            # beside it is what was decided.
            "formula": new_line.get("formula", ""),
        }
        if new_line["section"] == "earning":
            # Taxable, as an allowance is unless it says otherwise -- though
            # nothing here recomputes tax, so this is what the row claims
            # about itself rather than something that moves a figure.
            row.update({"allowance_id": None, "is_taxable": True})
            data["allowances"] = list(data["allowances"]) + [row]
        else:
            row["deduction_id"] = None
            data[NEW_LINE_BUCKET] = list(data.get(NEW_LINE_BUCKET) or []) + [row]

    data["federal_tax"] = (
        0.0 if TAX_KEY in removed else amounts.get(TAX_KEY, data.get("federal_tax", 0))
    )
    new_basic = round(amounts.get(BASIC_KEY, payslip.basic_pay or 0), 2)
    # The page reads these from the snapshot, not from the model's columns, so
    # leaving them as generated showed the old basic and gross after a save.
    data["basic_pay"] = new_basic
    data["gross_pay"] = totals["gross_pay"]
    data["taxable_gross_pay"] = round(
        taxable_after(payslip, pairs, amounts, removed, new_line), 2
    )
    if abs(new_basic - old_basic) > 0.005:
        # Basic was set by hand, so it is no longer "after loss of pay": the
        # figure is what was decided, and a Salary Adjustments block claiming
        # a deduction from it would describe something that did not happen.
        data["loss_of_pay_before_edit"] = data.get("loss_of_pay", 0)
        data["loss_of_pay"] = 0.0
        data["lop_reflected_in_basic"] = False
        data["basic_edited"] = True
    data["total_deductions"] = totals["total_deductions"]
    data["deduction_before_cap"] = totals["deduction_before_cap"]
    data["uncovered_deduction"] = totals["uncovered_deduction"]
    data["net_pay"] = totals["net_pay"]

    payslip.basic_pay = round(amounts.get(BASIC_KEY, payslip.basic_pay or 0), 2)
    payslip.gross_pay = totals["gross_pay"]
    payslip.deduction = totals["total_deductions"]
    payslip.net_pay = totals["net_pay"]
    payslip.pay_head_data = data
    payslip.save()
    return payslip


def parse_amounts(post, lines):
    """
    The posted amounts, as floats — never the client's own arithmetic.

    Only fields for lines that actually exist on this payslip are read, and
    an unparsable value is dropped rather than raising: a stray or tampered
    field should not fail the whole save when everything else on the form is
    fine.
    """
    amounts = {}
    for line in lines:
        raw = post.get(f"amount:{line['key']}")
        if raw in (None, ""):
            continue
        try:
            amounts[line["key"]] = round(float(raw), 2)
        except (TypeError, ValueError):
            continue
    return amounts


def formula_context(payslip):
    """
    ``{CODE: amount}`` for a formula written against this payslip.

    Not a sample. The engine recorded exactly which code resolved to what
    while it was generating this payslip (see ``payroll_run`` — the context is
    stored on ``pay_head_data``), so a formula here is evaluated against this
    person's real figures for this period rather than against the illustrative
    ones the component form previews with, where no employee is in view yet.

    A payslip generated before that context was stored keeps the two figures
    it has always had. They are the two most formulas reach for, and reading a
    missing code as 0 — which the evaluator already does — is the same answer
    the engine would give for a component the structure does not have.
    """
    data = payslip.pay_head_data or {}
    context = {
        str(code).upper(): float(value or 0)
        for code, value in (data.get("component_context") or {}).items()
    }
    context.setdefault("BASIC", float(payslip.basic_pay or 0))
    context.setdefault("GROSS", float(payslip.gross_pay or 0))
    # Older payslips did not store these; they are worked out from the dates.
    if "YEARS_OF_SERVICE" not in context or "YEARS_OF_CONTRACT" not in context:
        from payroll.methods.component_engine import add_service_years

        contract = payslip.employee_id.contract_set.filter(
            contract_status="active"
        ).first()
        fresh = add_service_years({}, payslip.employee_id, contract, payslip.end_date)
        for key, value in fresh.items():
            context.setdefault(key, value)
    return context


def formula_codes(payslip):
    """
    The codes worth offering as chips for this payslip, in the builder's shape.

    Narrowed to what this payslip actually resolved. The component form offers
    everything configured, because it is defining a rule that will meet many
    employees; here the employee and the period are both already decided, and
    a chip for a component this person does not have would quietly evaluate to
    0 while looking like it had done something.
    """
    from payroll.views.component_formula_views import available_codes

    context = formula_context(payslip)
    return [row for row in available_codes() if row["code"] in context]


def parse_new_line(post, payslip):
    """
    The line being added, or ``None`` if the form was left alone.

    A formula, if one was built, decides the amount — evaluated here against
    ``formula_context`` and never taken from the client, which is the same
    stance ``parse_amounts`` takes for every other figure on this form. A
    formula that cannot be evaluated refuses the line rather than falling back
    to whatever number happened to be in the box, because those two are not
    interchangeable: one of them is what the person asked for.
    """
    title = (post.get("new_title") or "").strip()
    raw_amount = (post.get("new_amount") or "").strip()
    expression = (post.get("new_formula") or "").strip()

    if not (title or raw_amount or expression):
        return None
    if not title:
        raise NewLineError(_("Give the new line a name."))

    section = "earning" if post.get("new_section") != "deduction" else "deduction"

    if expression:
        try:
            amount = run_component_formula(expression, formula_context(payslip))
        except ComponentFormulaError as exc:
            raise NewLineError(
                _("%(title)s: %(problem)s") % {"title": title, "problem": exc}
            ) from exc
    else:
        try:
            amount = float(raw_amount or 0)
        except (TypeError, ValueError) as exc:
            raise NewLineError(
                _("%(title)s needs an amount, or a formula to work one out.")
                % {"title": title}
            ) from exc

    return {
        "section": section,
        "title": title,
        "amount": round(amount, 2),
        "formula": expression,
    }


def _derive(component, context, earned):
    """
    What this component comes to against the amounts worked out so far, or
    ``None`` when it is not something this form can re-derive.

    Only the bases that are a function of other figures on the same payslip
    are here. They are safe to recompute because the figures they read are
    already prorated -- 40% of a basic pay that has had loss of pay taken off
    is the same 40% the engine arrived at, which is why this does not have to
    know anything about the period. Attendance and overtime bases are not:
    they read the timesheet, and no edit on this form changes that.
    """
    based_on = getattr(component, "based_on", "") or ""
    rate = float(getattr(component, "rate", 0) or 0)

    if based_on == "component":
        code = (getattr(component, "percentage_of_code", "") or "").strip().upper()
        return context.get(code, 0.0) * rate / 100 if code else None

    if based_on in AGGREGATE_CODES:
        return context.get(AGGREGATE_CODES[based_on], 0.0) * rate / 100

    if based_on == "formula":
        try:
            return run_component_formula(
                getattr(component, "formula", "") or "", context
            )
        except ComponentFormulaError:
            # The formula is the component's problem, not this form's. The
            # figure the payslip was generated with is kept and the line is
            # left where it is rather than being zeroed by a typo elsewhere.
            return None

    if based_on == "balance":
        # Whatever is left of the package after everything else. The structure
        # rules put a balance component last, so by the time it is reached
        # every other earning has been worked out -- which is the same order
        # the engine relies on.
        return max(0.0, context.get("CTC", 0.0) - earned)

    return None


def recompute_dependents(payslip, amounts, removed=(), given=()):
    """
    What every line comes to once the lines that follow others have caught up.

    A payslip's components are not a list of flat figures -- most of them are
    a percentage of one of the others -- so changing basic pay and leaving HRA
    where it was produces a payslip that no structure would ever have
    generated. This re-derives the ones that follow, in the order the engine
    ran them, against the amounts on the form right now.

    ``given`` are the lines somebody typed into. They are taken as stated even
    when they would otherwise be derived: an override is the reason this form
    exists, and a line that recomputed over the top of what was just typed
    could not be corrected at all.

    Gross is set from the earnings before the deductions are reached, exactly
    as ``payroll_run`` does it, so a deduction that is a percentage of gross
    reads the gross this edit produces rather than the one it was generated
    against.
    """
    stored = (payslip.pay_head_data or {}).get("component_context") or {}
    context = {str(code).upper(): float(value or 0) for code, value in stored.items()}
    given = set(given)
    removed = set(removed)

    pairs = described_lines(payslip)
    result = {}
    earned = 0.0

    for section in ("earning", "deduction"):
        if section == "deduction":
            # Every earning is in, so gross is final -- the point at which the
            # engine hands it to the deduction pass.
            context["GROSS"] = round(earned, 2)

        for line, component in pairs:
            if line["section"] != section:
                continue
            key = line["key"]
            amount = float(amounts.get(key, line["amount"]) or 0)

            if key in removed:
                result[key] = amount
                continue

            if key not in given and component is not None and line["depends_on"]:
                derived = _derive(component, context, earned)
                if derived is not None:
                    amount = round(derived, 2)

            result[key] = amount
            if line["code"]:
                context[line["code"]] = amount
            if section == "earning":
                earned += amount

    # Income Tax follows the edit unless it was typed into or taken off.
    if TAX_KEY not in given and TAX_KEY not in removed:
        tax = recomputed_tax(payslip, pairs, result, removed, earned)
        if tax is not None:
            result[TAX_KEY] = tax

    return result


def recomputed_tax_with_line(payslip, pairs, amounts, removed, gross, new_line):
    """recomputed_tax for a payslip that also gains a one-off taxable earning."""
    extra = float(new_line["amount"] or 0)
    return recomputed_tax(payslip, pairs, amounts, removed, gross, extra_taxable=extra)


def taxable_after(payslip, pairs, amounts, removed, new_line=None):
    """
    The taxable gross these figures leave, built the way the engine builds it:
    taxable earnings, less pre-tax deductions, less loss of pay when it is a
    separate pre-tax deduction.

    Worked from the lines rather than moved from the stored figure, so a
    payslip whose snapshot drifted (an earlier edit, or one generated before
    a fix) is still taxed on what it shows.
    """
    data = payslip.pay_head_data or {}
    taxable = 0.0
    for line, _component in pairs:
        key = line["key"]
        new = 0.0 if key in removed else float(amounts.get(key, line["amount"]) or 0)
        if line["section"] == "earning" and line.get("taxable"):
            taxable += new
        elif line.get("pretax"):
            taxable -= new
    if new_line and new_line["section"] == "earning":
        taxable += float(new_line["amount"] or 0)
    taxable -= taxable_loss_of_pay(payslip)
    return max(0.0, taxable)


def taxable_loss_of_pay(payslip):
    """Loss of pay that is taken off taxable gross: a separate, pre-tax one."""
    data = payslip.pay_head_data or {}
    if data.get("lop_reflected_in_basic"):
        return 0.0
    from payroll.models.models import Contract

    contract = (
        Contract.objects.entire()
        .filter(employee_id=payslip.employee_id, contract_status="active")
        .first()
    )
    if contract is None or contract.loss_of_pay_is_pretax:
        return float(data.get("loss_of_pay") or 0)
    return 0.0


def tax_explanation(payslip, pairs, amounts, removed, gross, extra_taxable=0.0):
    """
    How the Income Tax on these figures is worked out, or None when there is
    nothing to work out (no filing status on the contract: "no income tax
    configured", as it is in the engine).

    The same arithmetic ``period_tax`` does -- laid out step by step by
    ``explain_period_tax`` -- fed the figure the filing status taxes. Taxable
    gross is built from the lines: taxable earnings, less pre-tax deductions.
    """
    from payroll.methods.tax_calc import explain_period_tax
    from payroll.models.models import Contract

    contract = (
        Contract.objects.entire()
        .filter(employee_id=payslip.employee_id, contract_status="active")
        .select_related("filing_status")
        .first()
    )
    filing = contract.filing_status if contract is not None else None
    if filing is None:
        return None

    taxable = taxable_after(payslip, pairs, amounts, removed) + extra_taxable

    if filing.based_on == "taxable_gross_pay":
        income = taxable
    elif filing.based_on == "gross_pay":
        income = gross
    else:
        income = float(amounts.get(BASIC_KEY, payslip.basic_pay or 0) or 0)

    return explain_period_tax(
        filing,
        max(income, 0.0),
        payslip.start_date,
        payslip.end_date,
        employee=payslip.employee_id,
        pay_frequency=contract.pay_frequency,
    )


def recomputed_tax(payslip, pairs, amounts, removed, gross, extra_taxable=0.0):
    """The Income Tax these figures come to, or None (see tax_explanation)."""
    explained = tax_explanation(
        payslip, pairs, amounts, removed, gross, extra_taxable=extra_taxable
    )
    return None if explained is None else round(explained["period_tax"], 2)
