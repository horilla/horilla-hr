"""
federal_tax.py

The starter formula offered when a filing status is switched to Python mode.

It is deliberately a readable slab walk rather than the 70-line version this
shipped with before. That one hardcoded US-2023 bands, nested a helper inside
the entry point, and carried print()/formated_result() debug calls the sandbox
had to stub out — all to reproduce exactly what the slab table already does
without any code.

Most filing statuses should not be in Python mode at all: slabs plus the
standard deduction, rebate and cess adjustments cover India (both regimes), US
federal, UK PAYE and more, and the Filing Status page can load any of those
ready-made. This template exists for the genuinely unusual rule, and it starts
from the shape people recognise so it is obvious what to change.
"""

CODE = '''"""
Tax formula.

Return the tax owed on one year's income. The slab walk below mirrors how the
slab table works, so edit the rows to match your tax system — or replace the
whole function if your rules are a different shape entirely.

Available: arithmetic, min/max/abs/round/sum/len, and your own helper
functions and constants. Imports, file access and attribute introspection are
refused before this is saved.
"""


def calculate_federal_tax(yearly_income):
    # from, up to, rate %.   None on the last row means "and above".
    slabs = [
        (0, 250000, 0),
        (250000, 500000, 10),
        (500000, 1000000, 20),
        (1000000, None, 30),
    ]

    tax = 0
    for lower, upper, rate in slabs:
        if yearly_income <= lower:
            break
        top = yearly_income if upper is None else min(upper, yearly_income)
        tax += (top - lower) * rate / 100

    return tax
'''
