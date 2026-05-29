from __future__ import annotations

import logging
from typing import Final

import syside

logger = logging.getLogger(__name__)

_BINARY_OPERATORS: Final[dict[syside.Operator, tuple[str, int]]] = {
    syside.Operator.Or: ("or", 1),
    syside.Operator.LogicalOr: ("or", 1),
    syside.Operator.And: ("and", 2),
    syside.Operator.LogicalAnd: ("and", 2),
    syside.Operator.Equals: ("==", 4),
    syside.Operator.NotEquals: ("!=", 4),
    syside.Operator.Less: ("<", 4),
    syside.Operator.LessEqual: ("<=", 4),
    syside.Operator.Greater: (">", 4),
    syside.Operator.GreaterEqual: (">=", 4),
    syside.Operator.Plus: ("+", 5),
    syside.Operator.Minus: ("-", 5),
    syside.Operator.Multiply: ("*", 6),
    syside.Operator.Divide: ("/", 6),
}

_UNARY_OPERATORS: Final[dict[syside.Operator, tuple[str, int]]] = {
    syside.Operator.Minus: ("-", 7),
    syside.Operator.Not: ("not ", 3),
}


def emit_expression(expr: syside.Expression) -> str:
    """Translate ``expr`` to a Python source string.

    Public entry point for the sismic expression translator.

    Args:
        expr: The expression node to translate.

    Returns:
        Python source for ``expr``, with no enclosing parentheses.

    Raises:
        ValueError: If ``expr`` (or any sub-expression) is a node
            kind the emitter does not support.
    """
    return _emit(expr, parent_precedence=0)


def emit_assignment(assign: syside.AssignmentActionUsage) -> str:
    """Translate an assignment action to a Python assignment statement.

    Emits ``<target> = <rhs>``, where ``<target>`` is the assigned
    attribute's simple name and ``<rhs>`` is the emitted value
    expression.

    Args:
        assign: The ``assign <target> := <expr>`` action to translate.

    Returns:
        Python source for the assignment statement.

    Raises:
        ValueError: If the assignment target has no resolved name, if the
            value expression is absent, or if the value expression is a
            node kind ``emit_expression`` does not support.
    """
    target = assign.referent
    if target is None or target.name is None:
        raise ValueError("AssignmentActionUsage has no resolved target")
    value = assign.value_expression
    if value is None:
        raise ValueError("AssignmentActionUsage has no value expression")
    return f"{target.name} = {emit_expression(value)}"


def _emit(expr: syside.Expression, parent_precedence: int) -> str:
    """Dispatch ``expr`` to its node-type handler.

    Branch order respects syside's class hierarchy: more specific
    subclasses are matched before their parent classes.

    Args:
        expr: The expression node to translate.
        parent_precedence: Precedence of the enclosing operator. An
            operator handler wraps its output in parentheses when its
            own precedence is strictly less than this value.

    Returns:
        Python source for ``expr``.

    Raises:
        ValueError: If ``expr`` is a node kind the emitter does not
            support, or if any called handler raises.
    """
    logger.debug("dispatching %s", type(expr).__name__)

    if isinstance(expr, syside.LiteralBoolean):
        return _emit_literal_boolean(expr)
    if isinstance(expr, syside.LiteralRational):
        return _emit_literal_rational(expr)
    if isinstance(expr, syside.LiteralInteger):
        return _emit_literal_integer(expr)
    if isinstance(expr, syside.OperatorExpression):
        return _emit_operator(expr, parent_precedence)
    if isinstance(expr, syside.FeatureReferenceExpression):
        return _emit_feature_reference(expr)

    raise ValueError(f"unsupported expression node: {type(expr).__name__}")


def _emit_literal_boolean(expr: syside.LiteralBoolean) -> str:
    """Emit a boolean literal as ``"True"`` or ``"False"``.

    Args:
        expr: The literal node to translate.

    Returns:
        Python source for ``expr``.
    """
    return "True" if expr.value else "False"


def _emit_literal_integer(expr: syside.LiteralInteger) -> str:
    """Emit an integer literal as its Python ``str``.

    Always non-negative; SysML wraps negatives in a unary minus.

    Args:
        expr: The literal node to translate.

    Returns:
        Python source for ``expr``.
    """
    return str(expr.value)


def _emit_literal_rational(expr: syside.LiteralRational) -> str:
    """Emit a rational literal as its Python ``repr``.

    Args:
        expr: The literal node to translate.

    Returns:
        Python source for ``expr``.
    """
    return repr(expr.value)


def _emit_feature_reference(expr: syside.FeatureReferenceExpression) -> str:
    """Emit a bare feature reference as the referent's simple name.

    Sismic resolves the name against the interpreter context at
    evaluate time, so a qualified name would be invalid Python here.

    Args:
        expr: The feature reference to translate.

    Returns:
        Python source for ``expr``.

    Raises:
        ValueError: If the referent has no resolved name.
    """
    ref = expr.referent
    if ref is None or ref.name is None:
        raise ValueError("FeatureReferenceExpression has no resolved referent")
    return ref.name


def _emit_operator(
    expr: syside.OperatorExpression,
    parent_precedence: int,
) -> str:
    """Route ``expr`` to the binary or unary handler by operator arity.

    Args:
        expr: The operator expression to translate.
        parent_precedence: Precedence of the enclosing operator.

    Returns:
        Python source for ``expr``.

    Raises:
        ValueError: If the operator value or arity is not supported.
    """
    op = expr.operator
    operands = expr.operands.collect()
    logger.debug("operator %s with %d operand(s)", op, len(operands))

    if op in _BINARY_OPERATORS and len(operands) == 2:
        return _emit_binary(expr, parent_precedence)
    if op in _UNARY_OPERATORS and len(operands) == 1:
        return _emit_unary(expr, parent_precedence)

    raise ValueError(
        f"unsupported operator: {op!r} with {len(operands)} operand(s)"
    )


def _emit_binary(
    expr: syside.OperatorExpression,
    parent_precedence: int,
) -> str:
    """Emit a binary operator expression as ``<lhs> <op> <rhs>``.

    Args:
        expr: The operator expression to translate.
        parent_precedence: Precedence of the enclosing operator.

    Returns:
        Python source for ``expr``, wrapped in parentheses when this
        operator's precedence is strictly less than
        ``parent_precedence``.
    """
    py_op, prec = _BINARY_OPERATORS[expr.operator]
    operands = expr.operands.collect()
    lhs = _emit(operands[0], prec)
    # +1 forces parens around an equal-precedence RHS (left-associativity):
    # 'a - b - c' stays bare, 'a - (b - c)' keeps its parens.
    rhs = _emit(operands[1], prec + 1)
    body = f"{lhs} {py_op} {rhs}"
    return f"({body})" if prec < parent_precedence else body


def _emit_unary(
    expr: syside.OperatorExpression,
    parent_precedence: int,
) -> str:
    """Emit a unary operator expression as ``<op><inner>``.

    Args:
        expr: The operator expression to translate.
        parent_precedence: Precedence of the enclosing operator.

    Returns:
        Python source for ``expr``, wrapped in parentheses when this
        operator's precedence is strictly less than
        ``parent_precedence``.
    """
    py_op, prec = _UNARY_OPERATORS[expr.operator]
    inner = _emit(expr.operands.collect()[0], prec)
    body = f"{py_op}{inner}"
    return f"({body})" if prec < parent_precedence else body
