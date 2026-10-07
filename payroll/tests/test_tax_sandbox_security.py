"""
Adversarial tests for the tax-formula sandbox.

FilingStatus.python_code is operator-supplied Python that the payroll engine
executes on the server, for every payslip. That is the highest-value target in
the application: whoever can edit a filing status is one bad sandbox away from
reading .env, the database credentials, or running commands.

These tests are the evidence that they cannot. Each one is a real payload, not
a proxy for one — if the sandbox regresses, these fail rather than a reviewer
having to notice.

Two classes of protection are covered:

  * containment — no file access, no imports, no OS, no reflection escape.
    Enforced by the AST allow-list, which runs at save time AND before every
    execution, so bad code cannot even be stored.
  * availability — no formula may burn the server. This is the weaker half and
    is documented as such: the wall-clock timeout stops pure-Python loops, but
    it cannot interrupt a C-level builtin holding the GIL, so the builtins that
    can manufacture huge work are capped at source instead.
"""

from django.test import SimpleTestCase

from payroll.methods import federal_tax
from payroll.methods.safe_tax_code import (
    MAX_ITERATIONS,
    TaxCodeValidationError,
    TaxFormulaTimeout,
    run_tax_formula,
    validate_tax_code,
)


def _fn(body):
    return f"def calculate_federal_tax(y):\n    {body}\n"


class SandboxContainmentTests(SimpleTestCase):
    """Nothing may reach the filesystem, the OS, or the interpreter."""

    ESCAPES = {
        "read .env directly": _fn('return open(".env").read()'),
        "read .env via alias": "def calculate_federal_tax(y):\n    f = open\n    return f('.env').read()\n",
        "import os at module level": "import os\n" + _fn("return 0"),
        "import os inside the function": _fn("import os\n    return 0"),
        "__import__": _fn('return __import__("os")'),
        "subclasses walk": _fn("return ().__class__.__bases__[0].__subclasses__()"),
        "function __globals__": _fn("return calculate_federal_tax.__globals__"),
        "str.format attribute walk": _fn('return "{0.__class__}".format(y)'),
        "getattr": _fn('return getattr(y, "__class__")'),
        "eval": _fn('return eval("1+1")'),
        "exec": _fn('return exec("x=1")'),
        "compile": _fn('return compile("1","a","eval")'),
        "globals()": _fn("return globals()"),
        "locals()": _fn("return locals()"),
        "vars()": _fn("return vars()"),
        "__builtins__": _fn("return __builtins__"),
        "type() reflection": _fn("return type(y).__mro__"),
        "object reflection": _fn("return object.__subclasses__()"),
        "breakpoint": _fn("breakpoint()\n    return 0"),
        "dunder inside a string literal": _fn('s = "__subclasses__"\n    return 0'),
    }

    def test_every_escape_attempt_is_blocked(self):
        survived = []
        for label, code in self.ESCAPES.items():
            try:
                run_tax_formula(code, 100000)
                survived.append(label)
            except (TaxCodeValidationError, TaxFormulaTimeout):
                pass
            except Exception:
                # The formula's own error is fine; it never got out.
                pass
        self.assertEqual(survived, [], f"sandbox escape executed: {survived}")

    def test_escapes_are_rejected_at_save_time_too(self):
        """
        Containment must not depend on execution being reached. validate_tax_code
        is what the form and the AJAX save endpoint call, so a payload is
        refused before it is ever stored.
        """
        for label, code in self.ESCAPES.items():
            with self.subTest(payload=label):
                with self.assertRaises(TaxCodeValidationError):
                    validate_tax_code(code)


class SandboxAvailabilityTests(SimpleTestCase):
    """No formula may hold the server open or exhaust it."""

    def test_pure_python_infinite_loop_times_out(self):
        with self.assertRaises(TaxFormulaTimeout):
            run_tax_formula(_fn("while True:\n        pass"), 1, timeout=1.0)

    def test_a_timed_out_formula_does_not_keep_running(self):
        """
        Abandoning the worker used to leave it spinning for the life of the
        process -- one busy thread per bad formula, which is what made the
        full suite take 25 minutes longer to exit under coverage.
        """
        import threading
        import time

        before = set(threading.enumerate())
        for _ in range(3):
            with self.assertRaises(TaxFormulaTimeout):
                run_tax_formula(_fn("while True:\n        pass"), 1, timeout=0.3)

        deadline = time.time() + 5
        while True:
            leaked = [
                t for t in threading.enumerate() if t not in before and t.is_alive()
            ]
            if not leaked or time.time() > deadline:
                break
            time.sleep(0.1)
        self.assertEqual(leaked, [], "timed-out formula workers are still running")

    def test_huge_range_is_refused_rather_than_run(self):
        """
        The timeout alone does not cover this. ``sum(range(10**9))`` runs inside
        a single C-level bytecode operation holding the GIL, so the watchdog
        thread is never scheduled to notice its deadline — measured at 17
        seconds of full-core burn against a 2 second timeout. Capping range() at
        source is what actually bounds it.
        """
        with self.assertRaises(TaxCodeValidationError):
            run_tax_formula(_fn("return sum(range(10**9))"), 1)

    def test_pow_bomb_is_refused(self):
        with self.assertRaises(TaxCodeValidationError):
            run_tax_formula(_fn("return pow(9, 9**7)"), 1)

    def test_legitimate_iteration_still_works(self):
        """The cap must be generous enough to be invisible in real use."""
        self.assertEqual(run_tax_formula(_fn("return sum(range(10))"), 1), 45)
        self.assertGreater(MAX_ITERATIONS, 100000)


class SandboxUsabilityTests(SimpleTestCase):
    """Containment must not make ordinary formulas impossible to write."""

    def test_the_shipped_default_template_runs(self):
        """
        Asserts the arithmetic, not merely that it returns something: the
        template is what most people edit from, so if its slab walk is wrong
        every formula derived from it starts wrong.

        750,000 over the template's bands:
          250,000 @  0%  =      0
          250,000 @ 10%  = 25,000
          250,000 @ 20%  = 50,000
        """
        self.assertEqual(run_tax_formula(federal_tax.CODE, 750000), 75000)
        # Below the first threshold there is nothing to pay.
        self.assertEqual(run_tax_formula(federal_tax.CODE, 200000), 0)
        # And the open-ended top band keeps charging above its floor.
        self.assertEqual(run_tax_formula(federal_tax.CODE, 1500000), 275000)

    def test_a_module_level_helper_is_usable(self):
        """
        exec() with separate globals and locals put top-level definitions in
        locals, while a function body resolves free names through globals — so
        a formula with a helper died with "name 'helper' is not defined", and
        only formulas that nested everything inside the entry point worked.
        """
        code = (
            "def helper(x):\n"
            "    return x * 0.1\n"
            "def calculate_federal_tax(y):\n"
            "    return helper(y)\n"
        )
        self.assertEqual(run_tax_formula(code, 100000), 10000.0)

    def test_a_module_level_constant_is_usable(self):
        code = "RATE = 0.2\n" "def calculate_federal_tax(y):\n" "    return y * RATE\n"
        self.assertEqual(run_tax_formula(code, 100000), 20000.0)

    def test_ordinary_arithmetic_and_helpers_are_allowed(self):
        code = _fn("return round(min(max(y * 0.1, 100), 50000), 2)")
        self.assertEqual(run_tax_formula(code, 100000), 10000.0)
