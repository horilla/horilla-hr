"""
limits.py

The ceiling on a component's amount.
"""

from payroll.methods.proration import period_factor


def compute_limit(component, amount, day_dict):
    """
    Apply the component's maximum, scaled to the pay period.

    The maximum is quoted on a basis — a month's worth, an amount per working
    day, or a flat figure — and ``maximum_unit`` says which. Scaling it was
    written inline here and then commented out, so the field has been on the
    form all along offering "For working days on month" while the code applied
    the number flat. A ten-day period was capped at a whole month's ceiling.

    A full month still caps at exactly the figure configured, because the
    period's working days and the month's working days are then the same. Only
    partial and multi-month periods move, which is the point.
    """
    if not component.has_max_limit:
        return amount

    ceiling = component.maximum_amount
    if ceiling is None:
        return amount

    ceiling = float(ceiling) * period_factor(
        day_dict, getattr(component, "maximum_unit", None)
    )
    return min(amount, ceiling)
