"""
Ready-made salary components.

Every payroll department builds the same dozen components by hand — HRA,
Provident Fund, 401(k), GOSI — and gets the same details slightly wrong each
time: the rate, which base it applies to, whether it comes off before tax, the
ceiling it stops at. Getting one of those wrong is not a cosmetic problem; it
underpays or overcharges everyone on the structure.

These are those components, written out once with the rules that actually
define them. Loading one creates an ordinary Allowance or Deduction that can
then be edited like any other — this is a starting point, not a managed object.
Nothing here is loaded automatically.

The figures are the statutory or conventional ones at the time of writing, and
the rates in particular change: they are a head start, not a substitute for
checking against the current rules for the jurisdiction. Where a figure is a
common convention rather than a legal requirement — the HRA percentages, the
401(k) default — the entry says so.
"""

from django.utils.translation import gettext_lazy as _

EARNING = "allowance"
DEDUCTION = "deduction"

# Each entry: the fields the form would have been filled in with, plus enough
# context for someone to tell whether they want it. `fields` is passed straight
# to the model, so anything valid on Allowance or Deduction works here.
COMPONENT_LIBRARY = [
    # ---------------------------------------------------------------- India
    {
        "key": "in_basic",
        "group": _("India"),
        "kind": EARNING,
        "name": "Basic Pay",
        "summary": _("50% of CTC. Marked as basic pay, for a CTC Down structure."),
        "note": _(
            "Only needed when the structure divides a CTC. In a Gross Up "
            "structure basic pay comes from the contract wage instead."
        ),
        "fields": {
            "sequence": 10,
            "is_fixed": False,
            "based_on": "component",
            "percentage_of_code": "CTC",
            "rate": 50.0,
            "is_taxable": True,
            "is_basic_pay": True,
        },
    },
    {
        "key": "in_hra",
        "group": _("India"),
        "kind": EARNING,
        "name": "House Rent Allowance (HRA)",
        "summary": _("50% of basic pay."),
        "note": _(
            "50% is the usual figure for the metro cities and 40% elsewhere; "
            "it is a convention, not a fixed rule."
        ),
        "fields": {
            "sequence": 20,
            "is_fixed": False,
            "based_on": "basic_pay",
            "rate": 50.0,
            "is_taxable": True,
        },
    },
    {
        "key": "in_da",
        "group": _("India"),
        "kind": EARNING,
        "name": "Dearness Allowance (DA)",
        "summary": _("A percentage of basic pay, revised with inflation."),
        "note": _(
            "The rate is set periodically by the employer or by government "
            "notification; 20% here is only a placeholder."
        ),
        "fields": {
            "sequence": 30,
            "is_fixed": False,
            "based_on": "basic_pay",
            "rate": 20.0,
            "is_taxable": True,
        },
    },
    {
        "key": "in_conveyance",
        "group": _("India"),
        "kind": EARNING,
        "name": "Conveyance Allowance",
        "summary": _("A flat 1,600 a month, prorated by calendar days."),
        "fields": {
            "sequence": 40,
            "is_fixed": True,
            "amount": 1600.0,
            "is_taxable": True,
            "maximum_unit": "month_calendar_days",
        },
    },
    {
        "key": "in_special",
        "group": _("India"),
        "kind": EARNING,
        "name": "Special Allowance",
        "summary": _("Whatever is left of the CTC after every other earning."),
        "note": _(
            "Only meaningful in a CTC Down structure, and it has to run last — "
            "it can only see what has already been worked out."
        ),
        "fields": {
            "sequence": 900,
            "is_fixed": False,
            "based_on": "balance",
            "is_taxable": True,
        },
    },
    {
        "key": "in_pf",
        "group": _("India"),
        "kind": DEDUCTION,
        "name": "Provident Fund (PF)",
        "summary": _("12% of basic pay, before tax. The employer matches it."),
        "note": _(
            "Statutory contributions are commonly capped at a wage ceiling of "
            "15,000; set a maximum on the component if that applies to you."
        ),
        "fields": {
            "sequence": 100,
            "is_fixed": False,
            "based_on": "basic_pay",
            "rate": 12.0,
            "employer_rate": 12.0,
            "is_pretax": True,
        },
    },
    {
        "key": "in_esi",
        "group": _("India"),
        "kind": DEDUCTION,
        "name": "Employee State Insurance (ESI)",
        "summary": _("0.75% of gross, only while gross is at or under 21,000."),
        "note": _(
            "The ceiling is the point of this one: above it the employee is "
            "outside the scheme entirely, which is why it carries a rule "
            "rather than a maximum amount."
        ),
        "fields": {
            "sequence": 110,
            "is_fixed": False,
            "based_on": "gross_pay",
            "rate": 0.75,
            "employer_rate": 3.25,
            "is_pretax": True,
            "if_choice": "gross_pay",
            "if_condition": "le",
            "if_amount": 21000.0,
        },
    },
    {
        "key": "in_pt",
        "group": _("India"),
        "kind": DEDUCTION,
        "name": "Professional Tax",
        "summary": _("A flat 200 a month, the same in every period."),
        "note": _(
            "Levied by the state, so both the amount and the slabs vary; a "
            "flat figure is the common case."
        ),
        "fields": {
            "sequence": 120,
            "is_fixed": True,
            "amount": 200.0,
            "is_pretax": True,
            "maximum_unit": "full_period",
        },
    },
    # ------------------------------------------------------------------- US
    {
        "key": "us_401k",
        "group": _("United States"),
        "kind": DEDUCTION,
        "name": "401(k) Contribution",
        "summary": _("5% of gross, before tax."),
        "note": _(
            "The rate is whatever the employee elected, so 5% is only a "
            "starting point. Annual IRS limits are not modelled here."
        ),
        "fields": {
            "sequence": 100,
            "is_fixed": False,
            "based_on": "gross_pay",
            "rate": 5.0,
            "is_pretax": True,
        },
    },
    {
        "key": "us_social_security",
        "group": _("United States"),
        "kind": DEDUCTION,
        "name": "Social Security",
        "summary": _("6.2% of gross, matched by the employer."),
        "note": _(
            "Applies up to an annual wage base that is raised most years; "
            "that cap is not modelled here."
        ),
        "fields": {
            "sequence": 110,
            "is_fixed": False,
            "based_on": "gross_pay",
            "rate": 6.2,
            "employer_rate": 6.2,
            "is_pretax": True,
        },
    },
    {
        "key": "us_medicare",
        "group": _("United States"),
        "kind": DEDUCTION,
        "name": "Medicare",
        "summary": _("1.45% of gross, matched by the employer."),
        "fields": {
            "sequence": 120,
            "is_fixed": False,
            "based_on": "gross_pay",
            "rate": 1.45,
            "employer_rate": 1.45,
            "is_pretax": True,
        },
    },
    # ----------------------------------------------------------------- Gulf
    {
        "key": "gcc_housing",
        "group": _("Gulf"),
        "kind": EARNING,
        "name": "Housing Allowance",
        "summary": _("25% of basic pay."),
        "fields": {
            "sequence": 20,
            "is_fixed": False,
            "based_on": "basic_pay",
            "rate": 25.0,
            "is_taxable": True,
        },
    },
    {
        "key": "gcc_transport",
        "group": _("Gulf"),
        "kind": EARNING,
        "name": "Transport Allowance",
        "summary": _("10% of basic pay."),
        "fields": {
            "sequence": 30,
            "is_fixed": False,
            "based_on": "basic_pay",
            "rate": 10.0,
            "is_taxable": True,
        },
    },
    {
        "key": "gcc_gosi",
        "group": _("Gulf"),
        "kind": DEDUCTION,
        "name": "GOSI",
        "summary": _("9.75% of basic pay, with the employer paying 11.75%."),
        "note": _(
            "Saudi social insurance. The rates differ for Saudi and non-Saudi "
            "employees and the contribution base is usually basic plus "
            "housing — use a formula component if you need that base."
        ),
        "fields": {
            "sequence": 100,
            "is_fixed": False,
            "based_on": "basic_pay",
            "rate": 9.75,
            "employer_rate": 11.75,
            "is_pretax": True,
        },
    },
    # ------------------------------------------------------------------- UK
    {
        "key": "uk_pension",
        "group": _("United Kingdom"),
        "kind": DEDUCTION,
        "name": "Workplace Pension",
        "summary": _("5% of gross, with the employer adding 3%."),
        "note": _(
            "The auto-enrolment minimum. Real schemes apply it to qualifying "
            "earnings between a lower and upper limit rather than to all of "
            "gross."
        ),
        "fields": {
            "sequence": 100,
            "is_fixed": False,
            "based_on": "gross_pay",
            "rate": 5.0,
            "employer_rate": 3.0,
            "is_pretax": True,
        },
    },
]


def library_rows(existing_titles=frozenset()):
    """
    The library, flagged with what already exists.

    Matched on title, which is what someone reads. A component renamed after
    loading will look absent and can be loaded again — deliberate, because the
    alternative is a hidden marker that makes a plain Allowance behave unlike
    every other one.
    """
    existing = {title.strip().lower() for title in existing_titles}
    return [
        {
            "key": entry["key"],
            "group": entry["group"],
            "kind": entry["kind"],
            "name": entry["name"],
            "summary": entry["summary"],
            "note": entry.get("note", ""),
            "already_loaded": entry["name"].strip().lower() in existing,
        }
        for entry in COMPONENT_LIBRARY
    ]


def load_components(keys=None):
    """
    Create the chosen components. Returns the ones created.

    Skips anything whose title already exists, so running it twice does not
    produce a second Provident Fund — and so a half-finished selection can be
    retried without cleaning up first.
    """
    from payroll.models.models import Allowance, Deduction

    wanted = set(keys) if keys else {entry["key"] for entry in COMPONENT_LIBRARY}
    created = []

    for entry in COMPONENT_LIBRARY:
        if entry["key"] not in wanted:
            continue

        model = Allowance if entry["kind"] == EARNING else Deduction
        if model.objects.filter(title__iexact=entry["name"]).exists():
            continue

        component = model(title=entry["name"], **entry["fields"])
        component.save()
        created.append(component)

    return created
