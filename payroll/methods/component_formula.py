"""
payroll/methods/component_formula.py

Evaluates a salary component's formula against the amounts other components
have already computed this run.

This is a much smaller grammar than the tax-formula sandbox next door, and
deliberately so. A tax formula is a program — statements, helpers, branching —
so it needs compile/exec and therefore a timeout. A component formula is an
arithmetic expression over a handful of named amounts, so it is evaluated by
walking the parse tree directly: no compile, no exec, no statements, no
attribute access, no subscripts, no comprehensions. Nothing it can express
takes unbounded time, so it needs no timeout to be safe.

    (BASIC + DA) * 0.12
    min(BASIC * 0.5, 15000)

Moved down from the v2 engine before it was removed; it only depended on the
legacy sandbox's exception type, so the dependency direction was already
legacy <- v2.
"""

import ast
import operator
from decimal import Decimal, DivisionByZero, InvalidOperation

from payroll.methods.safe_tax_code import TaxCodeValidationError

__all__ = ["ComponentFormulaError", "run_component_formula"]


# Reusing the sandbox's error type keeps one thing for a caller to catch,
# while the alias says what it means in this context.
ComponentFormulaError = TaxCodeValidationError

# ast.Pow is deliberately absent. It is the one operator that turns a single
# expression into unbounded CPU and memory (9**9**9**9), and unlike the tax
# sandbox this evaluator has no timeout behind it — it does not need one,
# because without Pow every node below does strictly bounded work.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_CALLS = {"min": min, "max": max, "abs": abs, "round": round}


def run_component_formula(expression, context):
    """
    Evaluate ``expression`` against ``context`` (component code -> amount).

    An unknown name resolves to 0 rather than raising: a component that refers
    to something not present in this employee's structure should contribute
    nothing, not abort their payslip. A malformed expression does raise, so the
    caller can report it against that component.
    """
    if not (expression or "").strip():
        raise ComponentFormulaError("The formula is empty.")

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ComponentFormulaError(f"Could not parse the formula: {exc}") from exc

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ComponentFormulaError(
                    "Only numbers are allowed in a component formula."
                )
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            return Decimal(str(context.get(node.id.upper(), 0) or 0))
        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise ComponentFormulaError("That operator is not allowed.")
            return op(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op = _UNARY_OPS.get(type(node.op))
            if op is None:
                raise ComponentFormulaError("That operator is not allowed.")
            return op(_eval(node.operand))
        if isinstance(node, ast.Call):
            if (
                not isinstance(node.func, ast.Name)
                or node.func.id not in _ALLOWED_CALLS
            ):
                raise ComponentFormulaError(
                    "Only min(), max(), abs() and round() may be called."
                )
            if node.keywords:
                raise ComponentFormulaError("Keyword arguments are not allowed.")
            return Decimal(
                str(_ALLOWED_CALLS[node.func.id](*[_eval(a) for a in node.args]))
            )
        raise ComponentFormulaError(
            f"'{type(node).__name__}' is not allowed in a component formula."
        )

    try:
        return float(_eval(tree))
    except (DivisionByZero, ZeroDivisionError) as exc:
        raise ComponentFormulaError("The formula divides by zero.") from exc
    except InvalidOperation as exc:
        raise ComponentFormulaError(
            f"The formula produced an invalid number: {exc}"
        ) from exc
