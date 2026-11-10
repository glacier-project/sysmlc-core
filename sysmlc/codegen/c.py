"""C source generation for SysML expressions and assignments.

The generator renders bare names. Targets executing the code inside a
runtime context (``self->`` in Lingua Franca, ``ctx->`` elsewhere)
overrides :meth:`CCodeGen._emit_feature_reference`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final, override

import syside

from sysmlc.codegen.expression import ExpressionCodeGen
from sysmlc.codegen.python import LIBRARY_FUNCTIONS as _PYTHON_LIBRARY
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine.facts import AttributeValue, CompositeValue

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping


# The only precedences ``_emit_binary`` refers to by name.
_OR_PRECEDENCE: Final = 1
_AND_PRECEDENCE: Final = 2

_BINARY_OPERATORS: Final[dict[syside.Operator, tuple[str, int]]] = {
    syside.Operator.Or: ("||", _OR_PRECEDENCE),
    syside.Operator.LogicalOr: ("||", _OR_PRECEDENCE),
    syside.Operator.And: ("&&", _AND_PRECEDENCE),
    syside.Operator.LogicalAnd: ("&&", _AND_PRECEDENCE),
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

# C's unary operators bind tighter than every binary operator.
_UNARY_OPERATORS: Final[dict[syside.Operator, tuple[str, int]]] = {
    syside.Operator.Plus: ("+", 7),
    syside.Operator.Minus: ("-", 7),
    syside.Operator.Not: ("!", 7),
}

_ORDERING: Final = frozenset(
    {
        syside.Operator.Less,
        syside.Operator.LessEqual,
        syside.Operator.Greater,
        syside.Operator.GreaterEqual,
    }
)

# The C callee of every shared library function; all live in <math.h>.
LIBRARY_FUNCTIONS: Final[dict[str, str]] = {
    "NumericalFunctions::abs": "fabs",
    "NumericalFunctions::max": "fmax",
    "NumericalFunctions::min": "fmin",
    "TrigFunctions::sin": "sin",
    "TrigFunctions::cos": "cos",
    "TrigFunctions::tan": "tan",
}
assert set(LIBRARY_FUNCTIONS) == set(_PYTHON_LIBRARY)

_ESCAPES: Final = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def c_string(text: str) -> str:
    """Return ``text`` as an escaped C string literal."""
    escaped = "".join(_ESCAPES.get(char, char) for char in text)
    return f'"{escaped}"'


def _is_string(expr: syside.Expression) -> bool:
    """Whether ``expr`` is a string literal or a String-typed feature."""
    if isinstance(expr, syside.LiteralString):
        return True
    if isinstance(expr, syside.FeatureChainExpression):
        feature = expr.target_feature
    elif isinstance(expr, syside.FeatureReferenceExpression):
        feature = expr.referent
    else:
        return False
    if feature is None:
        return False
    # An enumeration specializing String is a C enum, not a string.
    types = feature.types.collect()
    return not any(
        isinstance(t, syside.EnumerationDefinition) for t in types
    ) and (
        any(t.matches_qualified_name(("ScalarValues", "String")) for t in types)
    )


def _is_enum_literal(expr: syside.Expression) -> bool:
    return isinstance(expr, syside.FeatureReferenceExpression) and isinstance(
        expr.referent, syside.EnumerationUsage
    )


class CCodeGenError(UnsupportedConstructError):
    """Raised when the C code generator does not support a construct."""


class CCodeGen(ExpressionCodeGen):
    """Generates C source from SysML expressions and assignments.

    Division is real division, as in SysML: the left operand is cast to
    ``double``. Structured values render as compound literals with
    designated initializers. Strings are pointers in C: comparing or adding
    them is rejected rather than compiled to pointer arithmetic, and so is
    ordering enumeration literals, whose C constants are positions.

    Args:
        external: The Foreign Artifacts available to back external calc-def
            calls, or None if none were provided.
    """

    _language_name: ClassVar[str] = "C"
    _error_type: ClassVar[type[UnsupportedConstructError]] = CCodeGenError
    _binary_operators: ClassVar[Mapping[syside.Operator, tuple[str, int]]] = (
        _BINARY_OPERATORS
    )
    _unary_operators: ClassVar[Mapping[syside.Operator, tuple[str, int]]] = (
        _UNARY_OPERATORS
    )
    _library_functions: ClassVar[Mapping[str, str]] = LIBRARY_FUNCTIONS

    def type_symbol(self, definition: syside.Definition) -> str:
        """Return the C type name of a structured definition.

        A target with its own type naming overrides this.

        Args:
            definition: The definition to name.

        Returns:
            The definition's simple name.

        Raises:
            ValueError: If the definition has no name.
        """
        if definition.name is None:
            raise ValueError("structured definition has no name")
        return definition.name

    def render_value(
        self,
        value: AttributeValue,
        register: Callable[[syside.Definition], None] | None = None,
    ) -> str | None:
        """Translate a neutral attribute value to a C expression.

        Args:
            value: The value to translate.
            register: Called with a structured value's definition before
                its literal is rendered, so the caller can declare its type,
                or None when the caller already does.

        Returns:
            C source for ``value``, or None when ``value`` is None.

        Raises:
            ValueError: If an expression is a node kind the emitter does not
                support.
        """
        if isinstance(value, CompositeValue):
            braces = self._braces(value, register)
            return f"({self.type_symbol(value.definition)}){braces}"
        return self._scalar(value)

    def _braces(
        self,
        value: CompositeValue,
        register: Callable[[syside.Definition], None] | None,
    ) -> str:
        """A structured value's initializer list, nested ones as plain braces.

        Only the outermost value is a compound literal: a nested compound
        literal is not a constant, so a static initializer cannot hold one.
        """
        if register is not None:
            register(value.definition)
        return f"{{ {self.render_fields(value.fields, register) or '0'} }}"

    def _scalar(self, value: AttributeValue) -> str | None:
        if value is None:
            return None
        if isinstance(value, float):
            return repr(value)
        assert not isinstance(value, CompositeValue)
        return self.render_expression(value)

    def render_fields(
        self,
        fields: Iterable[tuple[str, AttributeValue]],
        register: Callable[[syside.Definition], None] | None = None,
    ) -> str:
        """Translate named field values to designated initializers.

        A field whose value is None, unspecified, gets no initializer, so C
        zero-initializes it; a structured field is a plain brace list.

        Args:
            fields: ``(field name, value)`` pairs.
            register: As for :meth:`render_value`.

        Returns:
            Comma-separated ``.<name> = <source>`` initializers or empty when
            no field has a value.
        """
        initializers: list[str] = []
        for name, value in fields:
            rendered = (
                self._braces(value, register)
                if isinstance(value, CompositeValue)
                else self._scalar(value)
            )
            if rendered is not None:
                initializers.append(f".{name} = {rendered}")
        return ", ".join(initializers)

    @override
    def _render_assignment_statement(self, target: str, value: str) -> str:
        """Renders an assignment as ``<target> = <value>;``."""
        return f"{target} = {value};"

    @override
    def _library_call_needs_math(self, callee: str) -> bool:
        """Every C library function lives in ``<math.h>``."""
        return True

    @override
    def _emit_literal_boolean(self, expr: syside.LiteralBoolean) -> str:
        """Emit ``true`` or ``false`` (``<stdbool.h>``)."""
        return "true" if expr.value else "false"

    @override
    def _emit_literal_integer(self, expr: syside.LiteralInteger) -> str:
        """Emit an integer literal (always non-negative in SysML)."""
        return str(expr.value)

    @override
    def _emit_literal_rational(self, expr: syside.LiteralRational) -> str:
        """Emit a rational literal."""
        return repr(expr.value)

    @override
    def _emit_literal_string(self, expr: syside.LiteralString) -> str:
        """Emit an escaped C string literal."""
        return c_string(expr.value)

    @override
    def _emit_feature_reference(
        self, expr: syside.FeatureReferenceExpression
    ) -> str:
        """Emit a bare feature reference as the referent's name.

        Raises:
            ValueError: If the referent has no resolved name.
        """
        ref = expr.referent
        if ref is None or ref.name is None:
            raise ValueError(
                "FeatureReferenceExpression has no resolved referent"
            )
        return ref.name

    @override
    def _emit_feature_chain(self, expr: syside.FeatureChainExpression) -> str:
        """Emit a chained reference as struct member access ``a.b.c``.

        Raises:
            ValueError: If the chain has no target feature or an unnamed
                segment.
        """
        base = self._emit(expr.operands.collect()[0], parent_precedence=0)
        target = expr.target_feature
        if target is None:
            raise ValueError("FeatureChainExpression has no target feature")
        segments = [base]
        for feature in target.chaining_features.collect() or [target]:
            if feature.name is None:
                raise ValueError(
                    "FeatureChainExpression has an unnamed chain segment"
                )
            segments.append(feature.name)
        return ".".join(segments)

    @override
    def _emit_binary(
        self,
        expr: syside.OperatorExpression,
        parent_precedence: int,
    ) -> str:
        """Emit a binary expression in C.

        Beyond the shared precedence rules, an ``&&`` operand of ``||`` is
        parenthesized (as ``-Wparentheses`` asks), and ``/`` casts its left
        operand to ``double`` so integer operands divide as reals.

        Raises:
            CCodeGenError: If an operand is a String, or an ordering compares
                an enumeration literal.
        """
        operands = expr.operands.collect()
        if any(_is_string(operand) for operand in operands):
            raise CCodeGenError(
                "String values cannot be compared or combined in C; use an "
                "enumeration instead",
                node=expr,
            )
        if expr.operator in _ORDERING and any(
            _is_enum_literal(operand) for operand in operands
        ):
            raise CCodeGenError(
                "enumeration literals cannot be ordered in C", node=expr
            )
        token, precedence = self._binary_operators[expr.operator]
        if precedence == _OR_PRECEDENCE:
            lhs = self._emit(operands[0], _AND_PRECEDENCE + 1)
            rhs = self._emit(operands[1], _AND_PRECEDENCE + 1)
            body = f"{lhs} {token} {rhs}"
        elif expr.operator is syside.Operator.Divide:
            lhs = self._emit(operands[0], 0)
            rhs = self._emit(operands[1], 0)
            body = f"(double)({lhs}) / ({rhs})"
        else:
            return super()._emit_binary(expr, parent_precedence)
        return f"({body})" if precedence < parent_precedence else body

    @override
    def _emit_unary(
        self,
        expr: syside.OperatorExpression,
        parent_precedence: int,
    ) -> str:
        """Emit a unary expression. Signed operands (positive or negative) gets
        parentheses (``-(-x)`` must not become ``--x``).
        """
        token, precedence = self._unary_operators[expr.operator]
        inner = self._emit(expr.operands.collect()[0], precedence)
        if inner.startswith(("+", "-")):
            inner = f"({inner})"
        body = f"{token}{inner}"
        return f"({body})" if precedence < parent_precedence else body
