"""
The section layout for the Allowance and Deduction forms.

Defined here rather than in the template because the previous form listed the
field names it wanted to render by hand, in a chain of ``{% if field.name ==
... %}`` blocks. Anything not in that chain was simply not drawn — which is how
``percentage_of_code`` and ``formula`` came to exist on the model, be accepted
on save, and have nowhere on the form to set them.

A layout expressed as data can be checked. ``sections_for()`` ends by sweeping
every field the layout did not place into a final group, so a new field appears
somewhere on the form the day it is added, and ``test_component_form_ui``
asserts that the sweep is empty for the fields that are meant to be placed.

``show_if`` is the progressive-disclosure rule, read by
``static/src/js/componentForm.js``: space-separated ``name=value|value``
clauses, all of which must hold, where a checkbox reads ``on`` or ``off``.
"""

from django.utils.translation import gettext_lazy as _

# Amount types that are a straight percentage of something, and so need a rate.
PERCENTAGE_OF = "basic_pay|gross_pay|taxable_gross_pay|net_pay|component"

CALCULATED = "is_fixed=off"

# The first condition row. Further rows are cloned from it by the template.
CONDITIONAL = "include_active_employees=off is_condition_based=on"

# The form is long — around thirty fields on the Allowance side — and most of
# them do not apply to any given component. Progressive disclosure already hides
# the irrelevant ones, but what is left still reads as one tall column where the
# amount rule, the eligibility rules and the period rules run into each other.
#
# Three steps, because there are three questions: what is it, how much is it,
# and who and when. Every field stays in the DOM and the form still posts once —
# stepping is presentation, not a multi-request wizard — so validation, "save
# and add another" and the existing view are all untouched.
STEPS = [
    ("basics", _("Basics"), _("Name it and say what kind of component it is.")),
    ("amount", _("Amount"), _("How much, and any ceiling on it.")),
    ("applies", _("Applies to"), _("Which employees, and in which periods.")),
]


def _amount_fields():
    """Shared by both forms; each keeps only the ones it actually has."""
    return [
        ("amount", 6, "is_fixed=on"),
        ("based_on", 6, CALCULATED),
        # Which component, then what share of it. The other way round asked for
        # a percentage before saying what it was a percentage of.
        ("percentage_of_code", 6, f"{CALCULATED} based_on=component"),
        ("rate", 6, f"{CALCULATED} based_on={PERCENTAGE_OF}"),
        # The employer's share applies whatever the employee's side is worked
        # out from -- including a custom formula and a flat amount. It used to
        # be shown only for percentage-of components, so a component using a
        # formula could not state an employer contribution at all, and one
        # with a fixed amount could not either.
        ("employer_basis", 6, ""),
        ("employer_rate", 6, "employer_basis=rate"),
        ("per_attendance_fixed_amount", 6, f"{CALCULATED} based_on=attendance"),
        ("per_children_fixed_amount", 6, f"{CALCULATED} based_on=children"),
        ("shift_id", 6, f"{CALCULATED} based_on=shift_id"),
        ("shift_per_attendance_amount", 6, f"{CALCULATED} based_on=shift_id"),
        ("work_type_id", 6, f"{CALCULATED} based_on=work_type_id"),
        ("work_type_per_attendance_amount", 6, f"{CALCULATED} based_on=work_type_id"),
        (
            "amount_per_one_hr",
            6,
            f"{CALCULATED} based_on=overtime|week_off_overtime|holiday_overtime",
        ),
        # Not under "upper limit": it governs the fixed amount as well as the
        # ceiling, and a setting that only appeared once a ceiling was switched
        # on could not be found by anyone configuring a flat component.
        ("maximum_unit", 6, ""),
    ]


LAYOUT = [
    (
        "basics",
        _("What this component is"),
        None,
        [
            ("title", 6, ""),
            ("sequence", 6, ""),
            ("is_taxable", 6, ""),
            # Beside the other "what kind of thing is this" switches, because
            # that is what it is — not an amount setting.
            ("is_basic_pay", 6, ""),
            ("is_pretax", 6, ""),
            ("is_tax", 6, ""),
            ("one_time_date", 6, ""),
        ],
    ),
    (
        "amount",
        _("How much"),
        _("Either a set amount, or worked out from something else."),
        [("is_fixed", 12, "")] + _amount_fields(),
    ),
    (
        "amount",
        _("Upper limit"),
        None,
        [
            ("has_max_limit", 12, CALCULATED),
            ("maximum_amount", 6, f"{CALCULATED} has_max_limit=on"),
        ],
    ),
    (
        "applies",
        _("Who gets it"),
        None,
        [
            ("include_active_employees", 12, ""),
            ("specific_employees", 6, "include_active_employees=off"),
            ("exclude_employees", 6, ""),
            ("is_condition_based", 12, "include_active_employees=off"),
            ("field", 4, CONDITIONAL),
            ("condition", 4, CONDITIONAL),
            ("value", 4, CONDITIONAL),
        ],
    ),
    (
        "applies",
        _("When it applies"),
        _("Leave these alone to pay it every period."),
        [
            ("if_choice", 6, ""),
            ("if_component_code", 6, "if_choice=component"),
            ("if_condition", 6, ""),
            ("if_amount", 6, "if_condition=equal|notequal|lt|gt|le|ge"),
            ("start_range", 6, "if_condition=range"),
            ("end_range", 6, "if_condition=range"),
        ],
    ),
]

# Drawn by the template itself rather than as an ordinary row: a formula is
# edited in the builder popover, and only its summary belongs inline. The
# employer's is the same field in a second popover, opened from the employer
# basis row.
HANDLED_ELSEWHERE = {"formula", "employer_formula"}

# Never drawn. The code is derived from the title on save so that components can
# reference each other; it is plumbing, and asking someone to invent an
# identifier for a component they just named is the opposite of the point.
#
# update_compensation is hidden rather than dropped. It does something no other
# setting does — it shrinks the pay head itself, so a later "percentage of
# basic" is worked out on the reduced figure — but it bypasses eligibility,
# the "when it applies" rules, the ceiling and the period basis, and it sat
# between "Is Tax" and "One Time Date" with nothing to say any of that. Keeping
# it in the DOM means an existing one survives an edit; nothing on this form
# can create one.
HIDDEN_FIELDS = {"code", "update_compensation"}


def sections_for(form):
    """
    The form's visible fields, grouped for rendering.

    Returns ``[{"title", "hint", "rows": [{"field", "width", "show_if"}]}]``.
    Empty groups are dropped, so the Allowance form does not show a "Deduction
    only" heading with nothing under it.
    """
    placed = set(HANDLED_ELSEWHERE) | set(HIDDEN_FIELDS)
    sections = []

    for index, (step, title, hint, spec) in enumerate(LAYOUT, start=1):
        rows = []
        for name, width, show_if in spec:
            if name in placed or name not in form.fields:
                continue
            placed.add(name)
            rows.append({"field": form[name], "width": width, "show_if": show_if})
        if rows:
            # The key ties the heading to its rows in the DOM. They are siblings
            # rather than parent and child — everything has to be a direct child
            # of the Bootstrap row — so a heading can only know whether anything
            # under it is still visible by matching on this.
            sections.append(
                {
                    "key": f"s{index}",
                    "step": step,
                    "title": title,
                    "hint": hint,
                    "rows": rows,
                }
            )

    # Anything the layout above does not know about. A field added to the model
    # later shows up here instead of silently not existing on the form.
    leftovers = [
        {"field": bound, "width": 6, "show_if": ""}
        for bound in form.visible_fields()
        if bound.name not in placed
    ]
    if leftovers:
        sections.append(
            {
                "key": "other",
                "step": STEPS[-1][0],
                "title": _("Other settings"),
                "hint": None,
                "rows": leftovers,
            }
        )

    return sections


def steps_for(form):
    """
    The sections above, grouped into the steps the form is presented in.

    Returns ``[{"key", "label", "hint", "index", "sections": [...]}]``. A step
    whose sections are all empty for this form is dropped rather than shown as
    an unreachable tab.
    """
    sections = sections_for(form)
    steps = []
    for index, (key, label, hint) in enumerate(STEPS, start=1):
        members = [section for section in sections if section["step"] == key]
        if members:
            steps.append(
                {
                    "key": key,
                    "label": label,
                    "hint": hint,
                    "index": len(steps) + 1,
                    "sections": members,
                }
            )
    return steps


def unplaced_field_names(form):
    """The leftover sweep, for tests to assert on."""
    placed = set(HANDLED_ELSEWHERE) | set(HIDDEN_FIELDS)
    for _step, _title, _hint, spec in LAYOUT:
        placed.update(name for name, _w, _s in spec)
    return [f.name for f in form.visible_fields() if f.name not in placed]


def form_context(form, model):
    """
    Everything the component form template needs beyond the form itself.

    Shared by AllowanceFormView and DeductionFormView, which previously each
    carried their own copy of the formula-chip lookup.
    """
    from payroll.views.component_formula_views import available_codes

    instance = getattr(form, "instance", None)
    pk = instance.pk if instance is not None and instance.pk else None

    extra_conditions = []
    if pk:
        extra_conditions = [
            {"field": row.field, "condition": row.condition, "value": row.value}
            for row in instance.other_conditions.all()
        ]

    return {
        "formula_codes": available_codes(exclude_pk=pk, exclude_model=model),
        "component_steps": steps_for(form),
        "extra_conditions": extra_conditions,
    }


# How the Based On choices are grouped in the dropdown. It is one flat list of
# eleven on the Allowance form, mixing "a percentage of something" with "a rate
# per unit worked" and with the two advanced modes — so "Custom Formula" sat
# between "Percentage of Another Component" and "Balance of CTC" with nothing
# to say they are a different kind of answer, and was routinely missed.
#
# Values not listed here still appear, under a trailing group, for the same
# reason sections_for sweeps up unplaced fields: a choice added to the model
# later must not vanish from the form.
BASED_ON_GROUPS = [
    (
        _("Percentage of"),
        ["basic_pay", "gross_pay", "taxable_gross_pay", "net_pay", "component"],
    ),
    (_("Work out with a formula"), ["formula", "balance"]),
    (
        _("A rate per unit worked"),
        [
            "attendance",
            "children",
            "shift_id",
            "work_type_id",
            "overtime",
            "week_off_overtime",
            "holiday_overtime",
        ],
    ),
]


def group_based_on_choices(field):
    """
    Regroup a Based On field's choices in place, keeping every one of them.

    The empty choice stays at the top and ungrouped: it is the "not chosen yet"
    state, not a kind of amount.
    """
    labels = {str(value): label for value, label in field.choices}
    # "Basic Pay" here is the figure on the contract; the Percentage Of list's
    # "Basic pay" is the component worked out by the structure. Say which.
    if "basic_pay" in labels:
        labels["basic_pay"] = _("Basic Pay (Basic on contract)")
    blank = [(value, label) for value, label in field.choices if value == ""]

    grouped = []
    used = {""}
    for title, values in BASED_ON_GROUPS:
        members = [(value, labels[value]) for value in values if value in labels]
        if members:
            grouped.append((title, members))
            used.update(value for value, _label in members)

    leftovers = [
        (value, label) for value, label in field.choices if str(value) not in used
    ]
    if leftovers:
        grouped.append((_("Other"), leftovers))

    field.choices = blank + grouped


def component_picker_rows(selected_allowances=(), selected_deductions=()):
    """
    Every component that can go in a salary structure, as table rows.

    A table rather than a tag box. In a multi-select two components with
    similar names are indistinguishable — "House Rent Allowance" and "House
    Rent Allowance (Metro)" are the same chip twice — and nothing tells you
    what either one pays or when. The columns are the same ones the structure's
    own listing shows, from the same summarisers, so a component reads the same
    before and after it is added.

    Ordered by (sequence, pk), the engine's own order, so the list doubles as a
    preview of the order they will run in.
    """
    from payroll.methods.component_summary import (
        applies_summary,
        calculation_summary,
        in_ctc_summary,
        proration_summary,
    )
    from payroll.models.models import Allowance, Deduction

    chosen_allowances = {int(pk) for pk in selected_allowances or []}
    chosen_deductions = {int(pk) for pk in selected_deductions or []}

    rows = []
    for model, kind, chosen in (
        (Allowance, "earning", chosen_allowances),
        (Deduction, "deduction", chosen_deductions),
    ):
        queryset = model.objects.exclude(only_show_under_employee=True).exclude(
            # A standard pay item says how loans or penalties behave; it is
            # never paid, so it cannot be a line in a structure.
            is_system=True
        )
        # Loan and fine instalments are one auto-generated Deduction per due
        # date. They belong to one employee's repayment schedule, not to a
        # reusable structure.
        if hasattr(model, "is_installment"):
            queryset = queryset.filter(is_installment=False)

        for component in queryset.order_by("sequence", "pk"):
            if kind == "earning":
                type_label = _("Earning")
            elif component.is_tax:
                type_label = _("Tax")
            elif component.is_pretax:
                type_label = _("Pre-tax deduction")
            else:
                type_label = _("Deduction")

            rows.append(
                {
                    "pk": component.pk,
                    "field": "allowances" if kind == "earning" else "deductions",
                    "kind": kind,
                    "checked": component.pk in chosen,
                    "sequence": component.sequence,
                    "code": component.code,
                    "title": component.title,
                    "type_label": type_label,
                    "calculation": calculation_summary(component),
                    "prorates": proration_summary(component),
                    "in_ctc": in_ctc_summary(component, kind),
                    "applies": applies_summary(component),
                    "is_basic_pay": getattr(component, "is_basic_pay", False),
                }
            )

    rows.sort(key=lambda row: (row["sequence"] or 0, row["pk"]))
    return rows
