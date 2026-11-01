"""Every redirect target in the payslip views must actually reverse.

`create_payslip`, `add_bonus` and `add_deduction` all redirected to the URL
name `view-payslip` with a `payslip_id` kwarg. That name belongs to a *list*
view taking no arguments:

    payroll/urls/component_urls.py   view-payslip/                -> view-payslip
    payroll/urls/urls.py             view-payslip/<int:id>/       -> view-created-payslip

so the reverse raised NoReverseMatch -> HTTP 500, *after* save_payslip() had
already committed. ATOMIC_REQUESTS is unset (Django default False), so the
payslip was durable: the user saw an error page for an operation that had in
fact succeeded, and clicking Create again produced a duplicate for the same
employee and period.

The giveaway that it was a typo rather than intent: the notification seven
lines above the create_payslip redirect already used `view-created-payslip`.

Asserting the reverse directly rather than exercising the views: the defect is
entirely in the URL name, and a view-level test would need a contract, a
period and a full payslip computation to reach the same line.

Reported as https://github.com/horilla/horilla-hr/issues/1238 by @Safeer1877.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

SOURCE = Path(__file__).resolve().parents[1] / "views" / "component_views.py"

# reverse("<name>"  -- the opening paren may be followed by a newline.
REVERSE_CALL = re.compile(r'reverse\(\s*"([a-z0-9-]+)"')


class PayslipRedirectReverseTests(SimpleTestCase):
    def test_no_reverse_in_the_payslip_views_passes_payslip_id_to_a_nameless_route(
        self,
    ):
        """Every reverse() in the module must accept the kwargs given to it."""
        source = SOURCE.read_text(encoding="utf-8")
        offenders = []
        checked = 0
        for match in REVERSE_CALL.finditer(source):
            name = match.group(1)
            tail = source[match.end() : match.end() + 120]
            if "payslip_id" not in tail:
                continue
            checked += 1
            try:
                reverse(name, kwargs={"payslip_id": 1})
            except NoReverseMatch:
                line = source.count("\n", 0, match.start()) + 1
                offenders.append(f"{SOURCE}:{line} reverse({name!r}, payslip_id=...)")

        # The scan is only a guard while it finds something to check.
        self.assertGreater(checked, 0, "no reverse(..., payslip_id=...) found")
        self.assertEqual(
            offenders,
            [],
            "these reverse() calls pass payslip_id to a route that takes no "
            "arguments, so they raise NoReverseMatch at runtime -- after the "
            "payslip has already been committed:\n  " + "\n  ".join(offenders),
        )
