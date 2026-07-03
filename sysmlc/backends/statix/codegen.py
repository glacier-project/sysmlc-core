from __future__ import annotations

import logging
from typing import Final

import syside

from sysmlc.errors import UnsupportedConstructError

logger = logging.getLogger(__name__)

# operator -> (C token, precedence). Mirrors the precedence discipline in
# sysmlc/codegen/python.py; C relational/equality are lumped at 4 with the
# comparison-parenthesization rule, which only ever over-parenthesizes.
_BINARY_OPERATORS: Final[dict[syside.Operator, tuple[str, int]]] = {
    syside.Operator.Or: ("||", 1),
    syside.Operator.LogicalOr: ("||", 1),
    syside.Operator.And: ("&&", 2),
    syside.Operator.LogicalAnd: ("&&", 2),
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
    syside.Operator.Not: ("!", 3),
}

_COMPARISON_OPERATORS: Final[frozenset[syside.Operator]] = frozenset(
    {
        syside.Operator.Equals,
        syside.Operator.NotEquals,
        syside.Operator.Less,
        syside.Operator.LessEqual,
        syside.Operator.Greater,
        syside.Operator.GreaterEqual,
    }
)


class CCodeGenError(UnsupportedConstructError):
    """Raised when the C code generator does not support a construct."""


class CCodeGen:
    """Lowers syside guard/effect/attribute nodes to C source.

    Attribute references render as ``<context_var>-><name>`` (chained references
    as ``<context_var>-><a>.<b>``). When ``allow_context`` is False (rendering a
    context-struct initializer, which runs outside any function) a feature
    reference is rejected rather than mis-rendered.

    When ``attribute_names`` is non-empty, a reference to a name outside that
    set is rejected loudly (e.g. reading a signal payload like ``reading.value``
    that has no context field), rather than emitting ``ctx->reading`` that only
    fails at C-compile time. An empty set disables the check (used where the
    valid names are not known to the caller).
    """

    def __init__(
        self,
        *,
        context_var: str = "ctx",
        allow_context: bool = True,
        attribute_names: frozenset[str] = frozenset(),
    ) -> None:
        self._ctx = context_var
        self._allow_context = allow_context
        self._attribute_names = attribute_names

    def render_expression(self, expr: syside.Expression) -> str:
        """Translate ``expr`` to C source (no enclosing parentheses)."""
        return self._emit(expr)

    def render_action(self, action: syside.ActionUsage) -> str:
        """Translate a supported action usage to a C statement ending in ';'."""
        if isinstance(action, syside.AssignmentActionUsage):
            return self._render_assignment(action)
        if isinstance(action, syside.SendActionUsage):
            raise CCodeGenError(
                "`send` effects are not supported by statix yet.", node=action
            )
        raise CCodeGenError("unsupported action type", node=action)

    def _render_assignment(self, assign: syside.AssignmentActionUsage) -> str:
        target = assign.referent
        if target is None or target.name is None:
            raise CCodeGenError(
                "assignment has no resolved target", node=assign
            )
        base = _assignment_target_base(assign)
        lhs = (
            f"{self._ctx}->{target.name}"
            if base is None
            else f"{self._ctx}->{base}.{target.name}"
        )
        value = assign.value_expression
        if value is None:
            raise CCodeGenError(
                "assignment has no value expression", node=assign
            )
        return f"{lhs} = {self._emit(value)};"

    def _emit(self, expr: syside.Expression, parent_precedence: int = 0) -> str:
        if isinstance(expr, syside.LiteralBoolean):
            return "true" if expr.value else "false"
        if isinstance(expr, syside.LiteralRational):
            return repr(expr.value)
        if isinstance(expr, syside.LiteralInteger):
            return str(expr.value)
        if isinstance(expr, syside.LiteralString):
            raise CCodeGenError(
                "string literals are unsupported by statix", node=expr
            )
        if isinstance(expr, syside.FeatureChainExpression):
            return self._emit_feature_chain(expr)
        if isinstance(expr, syside.OperatorExpression):
            return self._emit_operator(expr, parent_precedence)
        if isinstance(expr, syside.FeatureReferenceExpression):
            return self._emit_feature_reference(expr)
        if isinstance(expr, syside.InvocationExpression):
            raise CCodeGenError(
                "function calls are unsupported by statix yet.", node=expr
            )
        raise CCodeGenError(
            f"unsupported expression node: {type(expr).__name__}", node=expr
        )

    def _emit_feature_reference(
        self, expr: syside.FeatureReferenceExpression
    ) -> str:
        ref = expr.referent
        if ref is None or ref.name is None:
            raise CCodeGenError(
                "feature reference has no resolved referent", node=expr
            )
        if not self._allow_context:
            raise CCodeGenError(
                f"reference to {ref.name!r} in a context initializer is "
                "unsupported",
                node=expr,
            )
        if self._attribute_names and ref.name not in self._attribute_names:
            raise CCodeGenError(
                f"reference to {ref.name!r} is not a machine attribute; "
                "reading signal payloads / non-attribute features is "
                "unsupported by statix yet.",
                node=expr,
            )
        return f"{self._ctx}->{ref.name}"

    def _emit_feature_chain(self, expr: syside.FeatureChainExpression) -> str:
        base = self._emit(expr.operands.collect()[0], 0)
        target = expr.target_feature
        if target is None:
            raise CCodeGenError(
                "feature chain has no target feature", node=expr
            )
        chain = target.chaining_features.collect() or [target]
        segments = [base]
        for feature in chain:
            if feature.name is None:
                raise CCodeGenError(
                    "feature chain has an unnamed segment", node=expr
                )
            segments.append(feature.name)
        return ".".join(segments)

    def _emit_operator(
        self, expr: syside.OperatorExpression, parent_precedence: int
    ) -> str:
        op = expr.operator
        operands = expr.operands.collect()
        if op in _BINARY_OPERATORS and len(operands) == 2:
            return self._emit_binary(expr, parent_precedence)
        if op in _UNARY_OPERATORS and len(operands) == 1:
            return self._emit_unary(expr, parent_precedence)
        raise CCodeGenError(
            f"unsupported operator: {op!r} with {len(operands)} operand(s)",
            node=expr,
        )

    def _emit_binary(
        self, expr: syside.OperatorExpression, parent_precedence: int
    ) -> str:
        token, prec = _BINARY_OPERATORS[expr.operator]
        operands = expr.operands.collect()
        if expr.operator in _COMPARISON_OPERATORS:
            lhs_parent = prec + 1
            rhs_parent = prec + 1
        else:
            lhs_parent = prec
            rhs_parent = prec + 1
        lhs = self._emit(operands[0], lhs_parent)
        rhs = self._emit(operands[1], rhs_parent)
        body = f"{lhs} {token} {rhs}"
        return f"({body})" if prec < parent_precedence else body

    def _emit_unary(
        self, expr: syside.OperatorExpression, parent_precedence: int
    ) -> str:
        token, prec = _UNARY_OPERATORS[expr.operator]
        inner = self._emit(expr.operands.collect()[0], prec)
        body = f"{token}{inner}"
        return f"({body})" if prec < parent_precedence else body


def _assignment_target_base(
    assign: syside.AssignmentActionUsage,
) -> str | None:
    """Return a chained assignment target's base feature name, if any.

    Mirrors the equivalent helper in sysmlc/codegen/python.py; reimplemented
    here to keep the statix backend independent of that module's privates.
    """
    target_feature: syside.Feature | None = None
    for feature in assign.owned_features.collect():
        if feature.name == "target":
            target_feature = feature
            break
    if target_feature is None:
        return None
    for rel in target_feature.owned_relationships.collect():
        if not isinstance(rel, syside.Specialization):
            continue
        general = rel.general
        if general is None or general.name is None:
            continue
        qn = (
            ""
            if general.qualified_name is None
            else str(general.qualified_name)
        )
        if qn.startswith("Actions::"):
            continue
        return general.name
    return None
