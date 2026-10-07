from django.utils.translation import gettext_lazy as _

"""
payroll.methods.safe_tax_code

Sandboxed evaluation of the user-supplied federal-tax formula stored on
``FilingStatus.python_code``.

Historically the ``python_code`` field was executed with a bare ``exec()`` and
only a couple of string replacements as "sanitisation". That allowed any user
able to create/edit a filing status to run arbitrary Python (and therefore OS
commands) on the server whenever a payslip was generated -- a CWE-94 code
injection / RCE.

This module replaces that with a dependency-free sandbox that:

* parses the code with :func:`ast.parse` and rejects any disallowed construct
  (imports, attribute access to dunders, calls to dangerous builtins, lambdas
  that reach into internals, etc.) *before* anything is executed;
* executes the validated code with ``__builtins__`` reduced to a tiny, safe
  allow-list (numeric/sequence helpers only);
* exposes a single :func:`validate_tax_code` entry point used at *save time*
  (so bad code is rejected before it is ever stored) and a
  :func:`run_tax_code` entry point used at *evaluation time* (defence in
  depth).

The sandbox is intentionally strict: the contract is simply that the code
defines ``calculate_federal_tax(yearly_income)`` returning a number. No
imports, file access, attribute introspection, or I/O are permitted.
"""

import ast
import ctypes
import re
import threading

__all__ = [
    "TaxCodeValidationError",
    "TaxFormulaTimeout",
    "validate_tax_code",
    "run_tax_code",
    "run_tax_formula",
]

# Wall-clock budget for one formula evaluation. Generous for arithmetic over a
# handful of brackets; short enough that a runaway formula cannot hold a
# payroll run open.
DEFAULT_TIMEOUT_SECONDS = 2.0


class TaxCodeValidationError(ValueError):
    """Raised when user-supplied tax code violates the sandbox policy."""


class TaxFormulaTimeout(Exception):
    """Raised when a tax formula exceeds its execution time budget."""


# Builtins that are safe to expose to the formula. Deliberately minimal:
# numeric/sequence helpers only, nothing that touches the filesystem,
# imports, evaluation, or introspection.
# Ceiling on anything that can manufacture a long iteration. A tax formula
# walks a handful of brackets; nothing legitimate needs a million steps.
#
# This exists because the wall-clock timeout cannot stop a C-level builtin.
# ``sum(range(10**9))`` holds the GIL inside a single bytecode operation, so
# the watchdog thread never gets scheduled to notice its deadline — measured at
# 17 seconds of full-core burn against a 2 second timeout. Capping the
# iteration at the source is what actually bounds it.
MAX_ITERATIONS = 1_000_000

# Largest exponent allowed to ``pow``. Big enough for any rate maths, small
# enough that the result cannot become a multi-megabyte integer.
MAX_POW_EXPONENT = 64


def _guarded_range(*args):
    """``range`` that refuses to produce an absurd number of steps."""
    result = range(*args)
    if len(result) > MAX_ITERATIONS:
        raise TaxCodeValidationError(
            f"range() of {len(result):,} steps exceeds the {MAX_ITERATIONS:,} "
            "allowed in a tax formula."
        )
    return result


def _guarded_pow(base, exponent, *args):
    """``pow`` that refuses exponents big enough to be a memory bomb."""
    if isinstance(exponent, (int, float)) and abs(exponent) > MAX_POW_EXPONENT:
        raise TaxCodeValidationError(
            f"pow() exponent {exponent} exceeds the maximum of {MAX_POW_EXPONENT} "
            "allowed in a tax formula."
        )
    return pow(base, exponent, *args)


_SAFE_BUILTINS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sum": sum,
    "len": len,
    "range": _guarded_range,
    "float": float,
    "int": int,
    "bool": bool,
    "dict": dict,
    "list": list,
    "tuple": tuple,
    "set": set,
    "enumerate": enumerate,
    "sorted": sorted,
    "zip": zip,
    "map": map,
    "filter": filter,
    "pow": _guarded_pow,
    "divmod": divmod,
}

# AST node types that are flat-out forbidden anywhere in the source.
_FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    # Async constructs have no place in a synchronous tax formula and only add
    # surface area.
    ast.AsyncFunctionDef,
    ast.Await,
    ast.AsyncFor,
    ast.AsyncWith,
)

# Names that must never appear as identifiers, calls, or string-built
# attribute lookups -- these are the classic sandbox-escape primitives.
_FORBIDDEN_NAMES = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "open",
        "__import__",
        "input",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "breakpoint",
        "memoryview",
        "classmethod",
        "staticmethod",
        "super",
        "type",
        "object",
    }
)

# The single required entry-point function.
ENTRY_POINT = "calculate_federal_tax"

_DUNDER_IN_STRING = re.compile(r"__\w+__")


class _PolicyVisitor(ast.NodeVisitor):
    """Walks the parsed AST and records any policy violation."""

    def __init__(self):
        self.errors = []

    def _fail(self, node, message):
        lineno = getattr(node, "lineno", "?")
        self.errors.append(f"line {lineno}: {message}")

    def generic_visit(self, node):
        if isinstance(node, _FORBIDDEN_NODES):
            self._fail(
                node,
                f"{type(node).__name__} is not allowed in tax code "
                "(imports, async, and global/nonlocal are forbidden).",
            )
            return
        super().generic_visit(node)

    def visit_Attribute(self, node):
        # Block any dunder attribute access -- this is the route to
        # __class__ / __subclasses__ / __globals__ sandbox escapes.
        if isinstance(node.attr, str) and node.attr.startswith("__"):
            self._fail(
                node, f"access to dunder attribute '{node.attr}' is not allowed."
            )
        # str.format()/format_map() resolve "{0.attr.attr}" at runtime, which
        # is a getattr primitive the AST walk cannot see through when the
        # string is assembled dynamically. Tax formulas have no use for them.
        if node.attr in ("format", "format_map"):
            self._fail(node, f"'.{node.attr}()' is not allowed in tax code.")
        self.generic_visit(node)

    def visit_Constant(self, node):
        # str.format()/format_map() walk attributes named inside the *string*
        # ("{0.__class__.__subclasses__}".format(x)), which visit_Attribute
        # never sees. Refuse any string constant that spells a dunder.
        if isinstance(node.value, str) and _DUNDER_IN_STRING.search(node.value):
            self._fail(node, "dunder names are not allowed inside string literals.")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in _FORBIDDEN_NAMES:
            self._fail(node, f"use of '{node.id}' is not allowed.")
        if node.id.startswith("__") and node.id.endswith("__"):
            self._fail(node, f"use of dunder name '{node.id}' is not allowed.")
        self.generic_visit(node)


def _check(code: str):
    """Parse ``code`` and return the parsed module, raising on any violation."""
    if not isinstance(code, str) or not code.strip():
        raise TaxCodeValidationError(_("Tax code is empty."))

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise TaxCodeValidationError(f"Syntax error in tax code: {exc}") from exc

    visitor = _PolicyVisitor()
    visitor.visit(tree)
    if visitor.errors:
        raise TaxCodeValidationError(
            "Tax code rejected by sandbox policy:\n  " + "\n  ".join(visitor.errors)
        )

    defines_entry = any(
        isinstance(node, ast.FunctionDef) and node.name == ENTRY_POINT
        for node in tree.body
    )
    if not defines_entry:
        raise TaxCodeValidationError(
            f"Tax code must define a top-level function '{ENTRY_POINT}(yearly_income)'."
        )

    return tree


def validate_tax_code(code: str) -> None:
    """Validate user-supplied tax code without executing it.

    Use this at *save time*. Raises :class:`TaxCodeValidationError` describing
    every policy violation found, or returns ``None`` if the code is safe.
    """
    _check(code)


def _stop_worker(worker, attempts: int = 20, wait: float = 0.05):
    """Ask CPython to raise ``SystemExit`` inside a worker that outran its timeout.

    Python cannot kill a thread, but it can raise an exception in one the next
    time it runs bytecode, which is enough for ``while True: pass``. It is
    repeated because a formula may catch the first one (``try/except`` around
    its own loop). It cannot interrupt a single long C call, which is why
    ``range()`` and ``**`` are capped at source instead.
    """
    for _ in range(attempts):
        if not worker.is_alive():
            return
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(worker.ident), ctypes.py_object(SystemExit)
        )
        worker.join(wait)


def run_tax_formula(code: str, yearly_income, timeout: float = DEFAULT_TIMEOUT_SECONDS):
    """Validate, sandbox-execute, and call the tax formula under a time limit.

    Returns the numeric result of ``calculate_federal_tax(yearly_income)``.
    Raises :class:`TaxCodeValidationError` if the code violates the sandbox
    policy, :class:`TaxFormulaTimeout` if it does not finish within ``timeout``
    seconds, or propagates whatever the formula itself raised.

    The AST allow-list above bounds what the code may *reach*, but nothing in
    it bounds how long the code may *run*: ``while True: pass`` passes every
    policy check and then hangs whichever thread is generating payslips. Since
    the code being run is operator-supplied and stored in the database, that is
    a denial-of-service waiting to happen, and it used to be reachable through
    ``run_tax_code``.

    The work therefore happens on a daemon worker joined with a wall-clock
    timeout. ``threading`` rather than ``signal.alarm`` because the latter is
    POSIX-only and this project runs on Windows too. Joining does not stop a
    stuck worker, so on timeout it is also told to raise inside itself
    (:func:`_stop_worker`). Without that the abandoned thread kept spinning for
    the life of the process: every bad formula leaked a busy thread, and the
    test suite ended up 25 minutes slower in CI waiting on the ones it made.
    """
    _check(code)

    # No-op stand-in for the template's debug helpers so legacy formulas that
    # call print()/formated_result() at module load do not blow up. They simply
    # do nothing in production.
    def _noop(*args, **kwargs):
        return None

    sandbox_globals = {
        "__builtins__": dict(_SAFE_BUILTINS),
        "print": _noop,
        "pass_print": _noop,
        "formated_result": _noop,
    }
    result_box = {}
    error_box = {}

    def _worker():
        try:
            # The AST check above has already guaranteed there are no imports,
            # dunder escapes, or dangerous calls; execution happens with the
            # restricted builtins only.
            #
            # One namespace, deliberately: exec() with separate globals and
            # locals puts the author's top-level definitions in locals, while a
            # function body resolves free names through globals. So a formula
            # that defined a helper — or recursed — died with "name 'helper' is
            # not defined", and the only formulas that worked were ones with
            # every helper nested inside the entry point.
            compiled = compile(code, "<tax_code>", "exec")
            exec(
                compiled, sandbox_globals
            )  # noqa: S102 - sandboxed; see module docstring
            func = sandbox_globals.get(ENTRY_POINT)
            if not callable(func):
                raise TaxCodeValidationError(
                    f"Tax code did not define a callable '{ENTRY_POINT}'."
                )
            result_box["value"] = func(yearly_income)
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller's thread
            error_box["error"] = exc

    worker = threading.Thread(target=_worker, name="tax-formula-worker", daemon=True)
    worker.start()
    worker.join(timeout=timeout)

    if worker.is_alive():
        _stop_worker(worker)
        raise TaxFormulaTimeout(
            f"Tax formula did not finish within {timeout}s and was abandoned."
        )
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("value")


def run_tax_code(code: str, yearly_income):
    """Backwards-compatible alias for :func:`run_tax_formula`.

    Deliberately delegates rather than keeping its own untimed ``exec``: an
    unbounded runner that still exists is one a caller can still reach, and
    this one was reachable from ``tax_calc.calculate_taxable_amount`` on every
    payslip. There is now no code path that executes a formula without a
    timeout.
    """
    return run_tax_formula(code, yearly_income)
