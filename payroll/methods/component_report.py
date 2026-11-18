"""
What each allowance and deduction came to over a period.

Read from the payslips as issued, like the contributions report: a figure that is
reported has to agree with the payslips that were paid, so nothing is recomputed
from the components as they are configured today. The lines live in the
``pay_head_data`` JSON of each payslip, so the totals are summed in Python.
"""

from collections import defaultdict

from django.utils.translation import gettext as _

ALLOWANCE = "allowance"
DEDUCTION = "deduction"

BUCKETS = {
    ALLOWANCE: ("allowances",),
    DEDUCTION: (
        "basic_pay_deductions",
        "gross_pay_deductions",
        "pretax_deductions",
        "post_tax_deductions",
        "tax_deductions",
        "net_deductions",
    ),
}

ID_FIELD = {ALLOWANCE: "allowance_id", DEDUCTION: "deduction_id"}


def _rows(payslip, kind):
    """Every line of this kind on one payslip, whichever bucket it sat in."""
    data = payslip.pay_head_data or {}
    if not isinstance(data, dict):
        return
    for bucket in BUCKETS[kind]:
        for row in data.get(bucket) or []:
            if isinstance(row, dict):
                yield row


def _model(kind):
    from payroll.models.models import Allowance, Deduction

    return Allowance if kind == ALLOWANCE else Deduction


def _key(row, kind):
    """A component's id, or the title for a line added by hand, which has no component."""
    component_id = row.get(ID_FIELD[kind])
    return (
        component_id
        if component_id and not row.get("custom_id")
        else f"title:{row.get('title', '')}"
    )


def _is_default(component):
    """
    A system default, or an entry raised for one request (a loan, an advance, a claim).

    These repeat: every request makes its own record with the same name and a numbered code, so they are
    reported as one entry rather than one row each.
    """
    return bool(
        getattr(component, "is_system", False)
        or getattr(component, "only_show_under_employee", False)
        or getattr(component, "is_installment", False)
    )


def _taxed(kind, component):
    """True for a taxable earning or a pre-tax deduction: what tells two entries of one name apart."""
    return bool(component.is_taxable if kind == ALLOWANCE else component.is_pretax)


def _treatment(kind, taxed):
    if kind == ALLOWANCE:
        return _("Taxable") if taxed else _("Non-Taxable")
    return _("Pre-Tax") if taxed else _("Post-Tax")


def member_ids(kind, component):
    """The ids of the entries reported as one with this component: itself, or every default entry of its name."""
    if not _is_default(component):
        return {component.pk}
    taxed = _taxed(kind, component)
    same = _model(kind).objects.entire().filter(title__iexact=component.title.strip())
    return {
        entry.pk
        for entry in same
        if _is_default(entry) and _taxed(kind, entry) == taxed
    } | {component.pk}


def summarise(payslips, kind, search=""):
    """
    One row per component of this kind, over the payslips given, largest total first.

    Returns ``(rows, totals)``. The default entries of one name (see ``_is_default``) are one row, with how many
    entries it holds; when a name has both taxable and non-taxable (or pre-tax and post-tax) entries each row
    says which in brackets. A line added by hand on a payslip has no component, so it is grouped by its title and
    cannot be opened. ``search`` keeps the rows whose title or code contains it, and the totals follow what is kept.
    """
    total = defaultdict(float)
    employer = defaultdict(float)
    people = defaultdict(set)
    count = defaultdict(int)
    titles = {}
    for payslip in payslips:
        for row in _rows(payslip, kind):
            key = _key(row, kind)
            total[key] += float(row.get("amount") or 0)
            employer[key] += float(row.get("employer_contribution_amount") or 0)
            people[key].add(payslip.employee_id_id)
            count[key] += 1
            titles.setdefault(key, row.get("title") or "")

    ids = [key for key in titles if isinstance(key, int)]
    components = _model(kind).objects.entire().in_bulk(ids)

    # One group per component, except that the default entries of a name share one.
    groups = {}
    for key in titles:
        component = components.get(key)
        group = key
        if component is not None and _is_default(component):
            group = (
                "default",
                component.title.strip().lower(),
                _taxed(kind, component),
            )
        groups.setdefault(group, []).append(key)

    needle = (search or "").strip().lower()
    rows = []
    kept_people = set()
    for group, members in groups.items():
        first = min(
            (key for key in members if isinstance(key, int)), default=members[0]
        )
        component = components.get(first)
        name = component.title if component else titles[first]
        codes = [getattr(components.get(key), "code", "") or "" for key in members]
        if (
            needle
            and needle not in name.lower()
            and not any(needle in code.lower() for code in codes)
        ):
            continue
        amount = round(sum(total[key] for key in members), 2)
        shared = round(sum(employer[key] for key in members), 2)
        slips = sum(count[key] for key in members)
        who = set().union(*(people[key] for key in members))
        kept_people |= who
        rows.append(
            {
                "id": first if isinstance(first, int) else None,
                "title": name,
                "code": codes[0] if len(members) == 1 else "",
                "entries": len(members),
                "by_hand": component is None,
                "employees": len(who),
                "payslips": slips,
                "total": amount,
                "average": round(amount / slips, 2) if slips else 0.0,
                "employer_total": shared,
                "combined": round(amount + shared, 2),
                "_taxed": group[2] if isinstance(group, tuple) else None,
            }
        )

    # A name that has default entries of both treatments is told apart in brackets.
    treatments = defaultdict(set)
    for row in rows:
        if row["_taxed"] is not None:
            treatments[row["title"].strip().lower()].add(row["_taxed"])
    for row in rows:
        if (
            row["_taxed"] is not None
            and len(treatments[row["title"].strip().lower()]) > 1
        ):
            row["title"] = f"{row['title']} ({_treatment(kind, row['_taxed'])})"
        del row["_taxed"]

    # When the employer shares in a deduction, what it comes to is both shares together, so that is what the
    # rows are ranked by.
    split = kind == DEDUCTION and any(row["employer_total"] for row in rows)
    main = "combined" if split else "total"
    rows.sort(key=lambda row: (-row[main], row["title"]))

    grand = round(sum(row[main] for row in rows), 2)
    totals = {
        "total": round(sum(row["total"] for row in rows), 2),
        "employer_total": round(sum(row["employer_total"] for row in rows), 2),
        "combined": grand if split else round(sum(row["combined"] for row in rows), 2),
        "split": split,
        "components": len(rows),
        "employees": len(kept_people),
    }
    return rows, totals


def breakdown(payslips, kind, component, search=""):
    """
    One line per payslip for a component, newest period first: what its total is a sum of.

    ``component`` is an id, a set of ids (the default entries reported as one, see ``member_ids``), or the
    ``title:...`` key of a line added by hand.

    ``search`` keeps the lines of the employees whose name or badge id contains it.
    """
    wanted = (
        set(component)
        if isinstance(component, (set, frozenset, list, tuple))
        else {component}
    )
    needle = (search or "").strip().lower()
    lines = []
    for payslip in payslips:
        for row in _rows(payslip, kind):
            if _key(row, kind) not in wanted:
                continue
            employee = payslip.employee_id
            if needle and needle not in f"{employee} {employee.badge_id or ''}".lower():
                continue
            lines.append(
                {
                    "payslip": payslip,
                    "employee": payslip.employee_id,
                    "start_date": payslip.start_date,
                    "end_date": payslip.end_date,
                    "status": payslip.get_status_display(),
                    "amount": round(float(row.get("amount") or 0), 2),
                    "employer_amount": round(
                        float(row.get("employer_contribution_amount") or 0), 2
                    ),
                    "combined": round(
                        float(row.get("amount") or 0)
                        + float(row.get("employer_contribution_amount") or 0),
                        2,
                    ),
                    "name": payslip.employee_id.get_full_name(),
                    "badge_id": payslip.employee_id.badge_id or "",
                }
            )
    lines.sort(
        key=lambda line: (-line["start_date"].toordinal(), str(line["employee"]))
    )
    return lines


def summary_columns(kind, split):
    """``(label, key)`` of the summary table's columns, in the order the table shows them."""
    columns = [
        ("Component", "title"),
        ("Code", "code"),
        ("Employees", "employees"),
        ("Payslips", "payslips"),
        ("Average", "average"),
    ]
    if split:
        columns += [("Employee Share", "total"), ("Employer Share", "employer_total")]
    columns.append(("Combined Total", "combined") if split else ("Total", "total"))
    return columns


def detail_columns(kind, split):
    """``(label, key)`` of the component page's columns, in the order the table shows them."""
    columns = [
        ("Employee", "name"),
        ("Badge ID", "badge_id"),
        ("Period Start", "start_date"),
        ("Period End", "end_date"),
        ("Payslip Status", "status"),
    ]
    if split:
        columns += [
            ("Employee Share", "amount"),
            ("Employer Share", "employer_amount"),
            ("Combined Total", "combined"),
        ]
    else:
        columns.append(("Amount", "amount"))
    return columns


def export_table(columns, chosen, records):
    """
    ``(headers, rows)`` for the columns chosen, in the table's order.

    ``chosen`` comes from the browser, so only keys the table really has are used, and the labels are the
    table's own.
    """
    wanted = set(chosen)
    kept = [(label, key) for label, key in columns if key in wanted]
    return [label for label, _key in kept], [
        [record.get(key, "") for _label, key in kept] for record in records
    ]
