"""
What was withheld, and what the employer owes alongside it.

A contribution component is one where the deduction taken off the employee is
only half the story: provident fund, ESI, social security. The employer owes
its own share, and the two together are what gets remitted. Payroll computes
both — ``calculate_employer_contribution`` writes the employer side onto each
payslip — but nothing ever showed them, so the figure that has to be paid to a
statutory body existed only inside a JSON column.

Read from the payslips rather than recomputed. A remittance has to agree with
the payslips that were issued, and anything that works the figures out a second
time can disagree with them — a component edited after a run would quietly
restate a month that was already paid.

That means walking ``pay_head_data``, which is a JSON blob rather than rows, so
the aggregation happens in Python. For a month it is a few hundred payslips;
denormalising it into a table would be faster and would introduce a second
place for the truth to live.
"""

from collections import defaultdict

# Where deductions live on a payslip. All four, because a component's phase is
# a tax decision -- pre-tax, post-tax, off net -- and has nothing to do with
# whether the employer contributes to it.
DEDUCTION_KEYS = (
    "pretax_deductions",
    "post_tax_deductions",
    "tax_deductions",
    "net_deductions",
)


def _rows(payslip):
    """Every deduction line on one payslip, whichever phase it sat in."""
    data = payslip.pay_head_data or {}
    if not isinstance(data, dict):
        return
    for key in DEDUCTION_KEYS:
        for row in data.get(key) or []:
            if isinstance(row, dict) and row.get("deduction_id"):
                yield row


def contribution_components():
    """
    The components configured with an employer side, by id.

    Used to keep a component on the report through a month where its employer
    share happened to compute to nothing — otherwise a quiet month looks like
    the component was removed.
    """
    from django.db.models import Q

    from payroll.models.models import Deduction

    configured = Deduction.objects.entire().filter(
        Q(employer_rate__gt=0) | Q(employer_basis=Deduction.EMPLOYER_BASIS_FORMULA)
    )
    return {component.pk: component for component in configured}


def summarise(payslips, all_deductions=False):
    """
    One row per contribution component, over the payslips given.

    Returns ``(rows, totals)``. Rows carry the employee share, the employer
    share, the two combined, and how many people it applied to — sorted by the
    combined figure, because that is the one being remitted.

    With ``all_deductions`` every deduction counts, employer share or not,
    except the generated ones (loan instalments, fines).
    """
    configured = contribution_components()
    generated = set()
    lookup = configured
    if all_deductions:
        from django.db.models import Q

        from payroll.models.models import Deduction

        every = Deduction.objects.entire()
        generated = set(
            every.filter(
                Q(only_show_under_employee=True) | Q(is_installment=True)
            ).values_list("pk", flat=True)
        )
        lookup = {
            component.pk: component for component in every.exclude(pk__in=generated)
        }

    employee_total = defaultdict(float)
    employer_total = defaultdict(float)
    people = defaultdict(set)
    titles = {}

    for payslip in payslips:
        for row in _rows(payslip):
            component_id = row["deduction_id"]
            employer = float(row.get("employer_contribution_amount") or 0)

            # A component with no employer side is an ordinary deduction and
            # not what this page is about.
            if all_deductions:
                if component_id in generated or component_id not in lookup:
                    continue
            elif component_id not in configured and not employer:
                continue

            employee_total[component_id] += float(row.get("amount") or 0)
            employer_total[component_id] += employer
            people[component_id].add(payslip.employee_id_id)
            titles.setdefault(component_id, row.get("title") or "")

    rows = []
    for component_id in titles:
        component = lookup.get(component_id)
        employee = round(employee_total[component_id], 2)
        employer = round(employer_total[component_id], 2)
        rows.append(
            {
                "id": component_id,
                "component": component,
                "title": (component.title if component else titles[component_id]),
                "basis": component.get_based_on_display() if component else "",
                "employee_rate": getattr(component, "rate", None),
                "employer_rate": getattr(component, "employer_rate", None),
                "by_formula": bool(
                    component
                    and component.employer_basis == component.EMPLOYER_BASIS_FORMULA
                ),
                "employee_amount": employee,
                "employer_amount": employer,
                "total": round(employee + employer, 2),
                "employees": len(people[component_id]),
                # Configured to contribute but nothing came of it this period.
                # Worth saying, rather than showing a row of zeroes that reads
                # like a mistake.
                "dormant": employer == 0,
            }
        )

    rows.sort(key=lambda row: (-row["total"], row["title"]))

    totals = {
        "employee_amount": round(sum(r["employee_amount"] for r in rows), 2),
        "employer_amount": round(sum(r["employer_amount"] for r in rows), 2),
        "components": len(rows),
        "employees": len({pk for ids in people.values() for pk in ids}),
    }
    totals["total"] = round(totals["employee_amount"] + totals["employer_amount"], 2)
    return rows, totals


def breakdown(payslips, component_id):
    """
    One row per payslip for a single component, newest period first.

    This is the working the summary figure is a sum of — what has to be
    produced when a remittance is queried.
    """
    lines = []
    for payslip in payslips:
        for row in _rows(payslip):
            if row["deduction_id"] != component_id:
                continue
            employee = float(row.get("amount") or 0)
            employer = float(row.get("employer_contribution_amount") or 0)
            lines.append(
                {
                    "payslip": payslip,
                    "employee": payslip.employee_id,
                    "start_date": payslip.start_date,
                    "end_date": payslip.end_date,
                    "status": payslip.get_status_display(),
                    "basis": row.get("based_on", ""),
                    "employee_amount": round(employee, 2),
                    "employer_amount": round(employer, 2),
                    "total": round(employee + employer, 2),
                }
            )

    lines.sort(
        key=lambda line: (-line["start_date"].toordinal(), str(line["employee"]))
    )
    return lines
