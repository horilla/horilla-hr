"""
The standard pay items every payroll has, as components you can configure.

Loans, salary advances, fines, attendance penalties, reimbursements, leave and
bonus encashment and loss of pay all reach a payslip already — but not as
components anyone chose. Each is generated in code, per employee, one row per
instalment: a loan with twelve repayments makes twelve Deductions titled
"<loan> - <date>". Every one of those generation sites assigns five or six
fields and lets the rest fall through to the model defaults.

Those defaults are therefore the real policy, and nobody set them:

  * is_taxable = True     -> reimbursements and encashments are taxed as income
  * is_pretax = True      -> loan and fine repayments reduce taxable gross
  * maximum_unit = calendar days
                          -> a loan payout prorates, so a mid-month joiner
                             receives a fraction of their loan

None of that is written down anywhere near the code relying on it, and none of
it is changeable without editing Python.

So each kind gets one template row, seeded by the system rather than created by
hand, sitting in the ordinary Allowance or Deduction list where the settings it
carries already have columns. The generators copy its tax treatment and its
proration basis instead of falling through to defaults. A template is not a
component in its own right: it is never paid, never eligible for an employee,
and never selectable into a salary structure — it only says how its kind
behaves.

Adding a kind here is the whole job: seeding, the list, the locked form and the
generators all read this table.
"""

from django.utils.translation import gettext_lazy as _

EARNING = "allowance"
DEDUCTION = "deduction"

# maximum_unit values, from payroll.methods.proration. Named here rather than
# imported so this table reads as the statement of policy it is.
CALENDAR_DAYS = "month_calendar_days"
WORKING_DAYS = "month_working_days"
FULL_PERIOD = "full_period"

SYSTEM_COMPONENTS = [
    # ------------------------------------------------------------- loans
    {
        "key": "loan_payout",
        "kind": EARNING,
        "title": "Loan",
        "summary": _("What an employee is paid when a loan is granted."),
        "note": _(
            "Created when a loan is approved, for the amount of the loan. "
            "Taxable by default, which is how it has always behaved here — "
            "a loan is money advanced, not earnings, so check this against "
            "your own rules."
        ),
        "defaults": {"is_taxable": True, "maximum_unit": FULL_PERIOD},
        "no_proration": True,
    },
    {
        "key": "loan_repayment",
        "kind": DEDUCTION,
        "title": "Loan repayment",
        "summary": _("Each instalment taken back from an employee's pay."),
        "note": _(
            "One deduction per instalment date. Pre-tax by default, so "
            "repayments reduce taxable gross."
        ),
        "defaults": {"is_pretax": True, "maximum_unit": FULL_PERIOD},
        "no_proration": True,
    },
    # ---------------------------------------------------------- advances
    {
        "key": "advance_payout",
        "kind": EARNING,
        "title": "Salary advance",
        "summary": _("What an employee is paid when salary is advanced."),
        "defaults": {"is_taxable": True, "maximum_unit": FULL_PERIOD},
        "no_proration": True,
    },
    {
        "key": "advance_repayment",
        "kind": DEDUCTION,
        "title": "Salary advance repayment",
        "summary": _("Each instalment of an advance taken back from pay."),
        "defaults": {"is_pretax": True, "maximum_unit": FULL_PERIOD},
        "no_proration": True,
    },
    # ------------------------------------------------------------- fines
    {
        "key": "fine",
        "kind": DEDUCTION,
        "title": "Fine",
        "summary": _("A penalty charged to an employee, taken in instalments."),
        "note": _(
            "Raised against an asset or entered directly. Unlike a loan it "
            "pays nothing out — only the instalments come off."
        ),
        "defaults": {"is_pretax": True, "maximum_unit": FULL_PERIOD},
        "no_proration": True,
    },
    {
        "key": "penalty",
        "kind": DEDUCTION,
        "title": "Attendance penalty",
        "summary": _("A late-come, early-out or leave penalty."),
        "note": _(
            "Raised automatically from attendance and leave rules, for the "
            "period it applies to."
        ),
        "defaults": {"is_pretax": True, "maximum_unit": FULL_PERIOD},
        "no_proration": True,
    },
    # ----------------------------------------------------- reimbursements
    {
        "key": "reimbursement",
        "kind": EARNING,
        "title": "Reimbursement",
        "summary": _("An approved expense paid back to an employee."),
        "note": _(
            "Taxable by default. A reimbursement of an expense is commonly "
            "not taxable income — worth checking against your own rules."
        ),
        "defaults": {"is_taxable": True, "maximum_unit": FULL_PERIOD},
        "no_proration": True,
    },
    {
        "key": "leave_encashment",
        "kind": EARNING,
        "title": "Leave encashment",
        "summary": _("Unused leave days paid out."),
        "defaults": {"is_taxable": True, "maximum_unit": FULL_PERIOD},
        "no_proration": True,
    },
    {
        "key": "bonus_encashment",
        "kind": EARNING,
        "title": "Bonus point encashment",
        "summary": _("Bonus points paid out."),
        "defaults": {"is_taxable": True, "maximum_unit": FULL_PERIOD},
        "no_proration": True,
    },
]

# The only fields a system component exposes. Everything else about it is
# decided by whatever generates it -- the amount comes from the loan schedule
# or the attendance record, the employee from the request -- so offering those
# fields would be offering settings that do nothing.
#
# maximum_unit is in this list but no kind currently uses it: every standard
# pay item is an exact amount fixed by the event that raised it, so there is
# nothing to divide by a shorter period. It stays here for a kind that one day
# is a monthly figure.
EDITABLE_FIELDS = ("is_taxable", "is_pretax", "maximum_unit")

BY_KEY = {entry["key"]: entry for entry in SYSTEM_COMPONENTS}


def entries_for(kind):
    """The system components of one kind, in the order defined above."""
    return [entry for entry in SYSTEM_COMPONENTS if entry["kind"] == kind]


def editable_fields(key):
    """
    Which of EDITABLE_FIELDS this kind actually has.

    An allowance has no is_pretax and a deduction no is_taxable, and loss of
    pay has no proration basis — showing a field that its kind cannot use is
    the same mistake as showing one that does nothing.
    """
    entry = BY_KEY.get(key)
    if entry is None:
        return ()

    fields = []
    if entry["kind"] == EARNING:
        fields.append("is_taxable")
    else:
        fields.append("is_pretax")
    if not entry.get("no_proration"):
        fields.append("maximum_unit")
    return tuple(fields)


def policy(key):
    """
    The stored template for one kind, or None if it has not been seeded.

    Callers fall back to their own behaviour when this returns None, so a
    database seeded before this existed keeps working unchanged.
    """
    from payroll.models.models import Allowance, Deduction

    entry = BY_KEY.get(key)
    if entry is None:
        return None
    model = Allowance if entry["kind"] == EARNING else Deduction
    # entire(), not objects: a template belongs to no company, and the company
    # manager would filter it out of a request scoped to one.
    return model.objects.entire().filter(system_key=key).first()


def policy_fields(key):
    """
    The tax treatment and proration basis to give a row of this kind.

    Returned as kwargs for the model, so a generator writes
    ``Deduction(**policy_fields("loan_repayment"), ...)`` instead of leaving
    those fields to defaults nobody chose.
    """
    fields = dict(BY_KEY.get(key, {}).get("defaults", {}))

    stored = policy(key)
    if stored is not None:
        # The stored row wins for anything editable; the rest of the defaults
        # still apply, so a setting that was REMOVED from the form -- the
        # proration basis -- keeps being honoured rather than silently
        # reverting to the model default it was introduced to override.
        for field in editable_fields(key):
            fields[field] = getattr(stored, field)
    return fields


def seed(company=None):
    """
    Create any template that does not exist yet. Returns the ones created.

    Idempotent on system_key, so it is safe to run on every startup and safe
    to run again after a kind is added here. It never overwrites a stored
    template: the settings on it are the user's, not this file's.
    """
    from payroll.models.models import Allowance, Deduction

    # A kind removed from the table above leaves its row behind, still
    # is_system and so still undeletable by hand. Pruned here so the list on
    # screen matches this file, which is the only place a kind is defined.
    # is_system is cleared first because the delete guard reads it.
    keys = {entry["key"] for entry in SYSTEM_COMPONENTS}
    for model in (Allowance, Deduction):
        stale = (
            model.objects.entire().filter(is_system=True).exclude(system_key__in=keys)
        )
        for row in stale:
            row.is_system = False
            row.save(update_fields=["is_system"])
            row.delete()

    created = []
    for entry in SYSTEM_COMPONENTS:
        model = Allowance if entry["kind"] == EARNING else Deduction
        if model.objects.entire().filter(system_key=entry["key"]).exists():
            continue

        row = model(
            title=entry["title"],
            is_system=True,
            system_key=entry["key"],
            # Never paid to anyone on its own: a template is read by whatever
            # generates the real rows, and generating it as well would pay the
            # same thing twice.
            include_active_employees=False,
            is_fixed=True,
            amount=0,
            **entry.get("defaults", {}),
        )
        row.save()
        created.append(row)
    return created
