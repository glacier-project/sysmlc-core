from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

import syside

from sysmlc.backends.statix.payload import (
    _flatten_leaf_paths,
    _reconstruct_nested_literal,
)
from sysmlc.errors import UnsupportedConstructError

if TYPE_CHECKING:
    from collections.abc import Callable

    from sysmlc.backends.statix.program import CStruct

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

# statix-specific C targets for the shared library-function allowlist. Keys MUST
# equal sysmlc.codegen.python.LIBRARY_FUNCTIONS (a test asserts it), so a new
# shared function forces an explicit map-or-reject decision here. Targets are
# <math.h> functions and are double-typed.
_C_MATH_FUNCTIONS: Final[dict[str, str]] = {
    "NumericalFunctions::abs": "fabs",
    "NumericalFunctions::max": "fmax",
    "NumericalFunctions::min": "fmin",
    "TrigFunctions::sin": "sin",
    "TrigFunctions::cos": "cos",
    "TrigFunctions::tan": "tan",
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

_RELATIONAL_OPERATORS: Final[frozenset[syside.Operator]] = frozenset(
    {
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

    When ``payload_feature`` is provided (the signal feature bound by the
    active transition's trigger, such as ``reading`` on ``Measurement``), a
    reference to a sub-feature of that payload (such as ``reading.value``, one
    segment) or one composite hop into it (``reading.sample.value``, two
    segments) renders as ``sc_event_payload_f64(event)``, and the read path
    (as a tuple of segment names) is recorded in ``payload_reads``. A
    reference to the whole payload without a sub-feature, or a chain three or
    more segments deep, is rejected.

    When ``enum_resolver`` is provided, a reference whose referent is a
    ``syside.EnumerationUsage`` (an enum literal, e.g. ``LightColor::red``)
    renders as the resolver's returned value, regardless of
    ``allow_context`` or ``attribute_names`` -- an enum literal is never a
    machine attribute and never needs ``ctx->``. With no resolver
    configured, an enum-literal referent is rejected loudly rather than
    mis-rendered as a plain feature name.
    """

    def __init__(
        self,
        *,
        context_var: str = "ctx",
        allow_context: bool = True,
        attribute_names: frozenset[str] = frozenset(),
        real_attributes: frozenset[str] = frozenset(),
        payload_feature: syside.Feature | None = None,
        enum_resolver: (
            Callable[[syside.EnumerationUsage], tuple[str, str, bool]] | None
        ) = None,
        extern_resolver: (
            Callable[[syside.InvocationExpression, CCodeGen], str | None] | None
        ) = None,
        payload_c_type: str | None = None,
        attribute_c_types: dict[str, str] | None = None,
        struct_field_types: dict[str, dict[str, str]] | None = None,
        structs_by_name: dict[str, CStruct] | None = None,
        generated_enum_types: frozenset[str] = frozenset(),
    ) -> None:
        self._ctx = context_var
        self._allow_context = allow_context
        self._attribute_names = attribute_names
        self._real_attributes = real_attributes
        self._payload_feature = payload_feature
        self._payload_c_type = payload_c_type
        self._enum_resolver = enum_resolver
        self._extern_resolver = extern_resolver
        self._attribute_c_types = attribute_c_types or {}
        self._struct_field_types = struct_field_types or {}
        self._structs_by_name = structs_by_name or {}
        self._generated_enum_types = generated_enum_types
        self.payload_reads: set[tuple[str, ...]] = set()
        self.whole_payload_types: set[str] = set()
        self._used_scalar_payload = False
        self.needs_math = False
        self._used_math = False

    def render_expression(self, expr: syside.Expression) -> str:
        """Translate ``expr`` to C source (no enclosing parentheses)."""
        return self._emit(expr)

    def render_action(self, action: syside.ActionUsage) -> str:
        """Translate a supported action usage to a C statement ending in ';'."""
        if isinstance(action, syside.AssignmentActionUsage):
            return self._render_assignment(action)
        if isinstance(action, syside.SendActionUsage):
            raise UnsupportedConstructError(
                "internal error: send actions must be lowered by the "
                "statix builder, not the expression codegen.",
                node=action,
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
        self._used_math = False
        self._used_scalar_payload = False
        if (
            self._payload_feature is not None
            and isinstance(value, syside.FeatureReferenceExpression)
            and value.referent == self._payload_feature
            and self._payload_c_type is not None
            and self._payload_c_type in self._struct_field_types
        ):
            target_c_type = (
                self._attribute_c_types.get(target.name)
                if base is None
                else self._struct_field_types.get(
                    self._attribute_c_types.get(base, ""), {}
                ).get(target.name)
            )
            if target_c_type != self._payload_c_type:
                raise CCodeGenError(
                    f"cannot assign the whole payload (type "
                    f"{self._payload_c_type!r}) to {lhs!r}, which has type "
                    f"{target_c_type!r}; statix requires an exact matching "
                    "generated struct type for a whole-payload assignment.",
                    node=assign,
                )
            self.payload_reads.add(())
            self.whole_payload_types.add(self._payload_c_type)
            return self._render_whole_payload_assignment(
                lhs, self._payload_c_type
            )
        rhs = self._emit(value)
        if (self._used_math or self._used_scalar_payload) and (
            base is not None or target.name not in self._real_attributes
        ):
            raise CCodeGenError(
                "library-function and payload-read results are double; "
                "assigning one to a non-Real attribute is unsupported by "
                "statix yet.",
                node=assign,
            )
        return f"{lhs} = {rhs};"

    def _render_whole_payload_assignment(
        self, lhs: str, struct_type: str
    ) -> str:
        """Decode a whole-payload event straight into `lhs`.

        Decodes as a multi-statement block (a local flat array, a checked read,
        then the reconstructed nested assignment) -- never a single expression,
        per the C99 constraint above.
        """
        paths = _flatten_leaf_paths(struct_type, self._structs_by_name)
        if not paths:
            raise CCodeGenError(
                f"whole-payload type {struct_type!r} has no Real leaves; "
                "statix requires at least one.",
                node=None,
            )
        nested = _reconstruct_nested_literal(
            struct_type, self._structs_by_name, paths
        )
        lines = [
            "{",
            f"    double sc__payload[{len(paths)}];",
            "    sc_status_t payload_status = sc_event_payload_read(",
            "        event, sc__payload, sizeof(sc__payload));",
            "    if (payload_status != SC_STATUS_OK) {",
            "        return payload_status;",
            "    }",
            f"    {lhs} = ({struct_type}){nested};",
            "}",
        ]
        return "\n".join(lines)

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
            return self._emit_invocation(expr)
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
        if isinstance(ref, syside.EnumerationUsage):
            if self._enum_resolver is None:
                raise CCodeGenError(
                    "enum literal reference with no resolver configured "
                    "(internal error: statix always wires one)",
                    node=expr,
                )
            _c_type, rendered, _is_generated = self._enum_resolver(ref)
            return rendered
        if self._payload_feature is not None and ref == self._payload_feature:
            if (
                self._payload_c_type is not None
                and self._payload_c_type in self._struct_field_types
            ):
                self.payload_reads.add(())
                fields = self._struct_field_types[self._payload_c_type]
                parts = [
                    f".{fname} = sc_event_payload_f64(event)"
                    for fname in fields
                ]
                return f"({self._payload_c_type}){{{', '.join(parts)}}}"
            raise CCodeGenError(
                "whole payload reference without a sub-feature is unsupported "
                "by statix yet.",
                node=expr,
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

    def _emit_invocation(self, expr: syside.InvocationExpression) -> str:
        if not self._allow_context:
            raise CCodeGenError(
                "function calls are unsupported in a context initializer.",
                node=expr,
            )
        func = expr.function
        qn = None if func is None else func.qualified_name
        target = None if qn is None else _C_MATH_FUNCTIONS.get(str(qn))
        if target is not None:
            self.needs_math = True
            self._used_math = True
            args = ", ".join(self._emit(a, 0) for a in expr.arguments.collect())
            return f"{target}({args})"
        if self._extern_resolver is not None:
            # Pass `self` (this CCodeGen instance) so the resolver renders
            # arguments through the SAME instance handling this expression --
            # there are several CCodeGen instances per builder (e.g. a
            # context-initializer one with allow_context=False), each with
            # its own _ctx/_allow_context; using the wrong one would render
            # arguments in the wrong context.
            rendered = self._extern_resolver(expr, self)
            if rendered is not None:
                return rendered
        raise CCodeGenError(
            f"unsupported function call {qn!s}; only allowlisted library "
            "functions (NumericalFunctions/TrigFunctions) are supported "
            "by statix yet.",
            node=expr,
        )

    def _emit_feature_chain(self, expr: syside.FeatureChainExpression) -> str:
        op0 = expr.operands.collect()[0]
        if (
            self._payload_feature is not None
            and isinstance(op0, syside.FeatureReferenceExpression)
            and op0.referent == self._payload_feature
        ):
            target = expr.target_feature
            if target is None:
                raise CCodeGenError(
                    "feature chain has no target feature", node=expr
                )
            chain = target.chaining_features.collect() or [target]
            names: list[str] = []
            for feature in chain:
                if feature.name is None:
                    raise CCodeGenError(
                        "payload chain has an unnamed segment", node=expr
                    )
                names.append(feature.name)
            if len(names) not in (1, 2):
                raise CCodeGenError(
                    "payload reads deeper than one composite hop (e.g. "
                    "reading.a.b) are unsupported by statix yet.",
                    node=expr,
                )
            self.payload_reads.add(tuple(names))
            self._used_scalar_payload = True
            return "sc_event_payload_f64(event)"
        base = self._emit(op0, 0)
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

    def _generated_enum_c_type(self, expr: syside.Expression) -> str | None:
        """The operand's C type, but only when it is a *generated* enum type.

        Handles three operand shapes: a bare enum-literal reference (asks
        the resolver directly -- always accurate, even for a definition
        classified for the first time by this very call); a bare attribute
        reference (looked up in ``attribute_c_types``); and a composite
        field chain (walks ``struct_field_types`` from the chain's base
        attribute). Returns None for anything else (a computed
        sub-expression, an unresolvable reference, or a resolved type that
        is native rather than generated) -- the caller then leaves ordinary
        C relational semantics alone.
        """
        if isinstance(expr, syside.FeatureReferenceExpression):
            ref = expr.referent
            chain: list[syside.Feature] = []
        elif isinstance(expr, syside.FeatureChainExpression):
            operands = expr.operands.collect()
            op0 = operands[0] if operands else None
            if not isinstance(op0, syside.FeatureReferenceExpression):
                return None
            ref = op0.referent
            target = expr.target_feature
            if target is None:
                return None
            chain = target.chaining_features.collect() or [target]
        else:
            return None
        if ref is None:
            return None
        if isinstance(ref, syside.EnumerationUsage):
            if chain or self._enum_resolver is None:
                return None  # a chain off an enum literal cannot occur
            c_type, _rendered, is_generated = self._enum_resolver(ref)
            return c_type if is_generated else None
        if ref.name is None:
            return None
        current: str | None = self._attribute_c_types.get(ref.name)
        for feature in chain:
            if current is None or feature.name is None:
                return None
            fields = self._struct_field_types.get(current)
            current = None if fields is None else fields.get(feature.name)
        return current if current in self._generated_enum_types else None

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
        if expr.operator in _RELATIONAL_OPERATORS:
            for operand in operands:
                enum_type = self._generated_enum_c_type(operand)
                if enum_type is not None:
                    raise CCodeGenError(
                        f"relational comparison ({token!r}) involving "
                        f"generated enum type {enum_type!r} is unsupported; "
                        "only == and != are supported for symbolic enum "
                        "values.",
                        node=expr,
                    )
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
