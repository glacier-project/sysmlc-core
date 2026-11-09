"""The language-neutral expression generator, driven by a dummy language.

Every spelling of the dummy language differs from Python's, so a test fails
when :class:`ExpressionCodeGen` hard-codes Python instead of asking the
subclass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

import pytest
import syside

from sysmlc.codegen.expression import ExpressionCodeGen
from sysmlc.errors import UnsupportedConstructError
from tests import _load_inline_model, _single_element

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


class _DummyError(UnsupportedConstructError):
    pass


class _DummyCodeGen(ExpressionCodeGen):
    _language_name: ClassVar[str] = "Dummy"
    _error_type: ClassVar[type[UnsupportedConstructError]] = _DummyError
    _binary_operators: ClassVar[Mapping[syside.Operator, tuple[str, int]]] = {
        syside.Operator.LogicalOr: ("OR", 1),
        syside.Operator.LogicalAnd: ("AND", 2),
        syside.Operator.Equals: ("EQ", 4),
        syside.Operator.Less: ("LT", 4),
        syside.Operator.Greater: ("GT", 4),
        syside.Operator.Plus: ("PLUS", 5),
        syside.Operator.Minus: ("MINUS", 5),
    }
    _unary_operators: ClassVar[Mapping[syside.Operator, tuple[str, int]]] = {
        syside.Operator.Not: ("NOT ", 3),
        syside.Operator.Minus: ("NEG ", 7),
    }
    _library_functions: ClassVar[Mapping[str, str]] = {
        "NumericalFunctions::abs": "ABS",
        "TrigFunctions::cos": "COS",
    }

    @override
    def _emit_literal_boolean(self, expr: syside.LiteralBoolean) -> str:
        return "#t" if expr.value else "#f"

    @override
    def _emit_literal_integer(self, expr: syside.LiteralInteger) -> str:
        return f"{expr.value}i"

    @override
    def _emit_literal_rational(self, expr: syside.LiteralRational) -> str:
        return f"{expr.value}r"

    @override
    def _emit_literal_string(self, expr: syside.LiteralString) -> str:
        return f"<{expr.value}>"

    @override
    def _emit_feature_reference(
        self, expr: syside.FeatureReferenceExpression
    ) -> str:
        assert expr.referent is not None
        return f"@{expr.referent.name}"

    @override
    def _emit_feature_chain(self, expr: syside.FeatureChainExpression) -> str:
        base = self._emit(expr.operands.collect()[0])
        assert expr.target_feature is not None
        return f"{base}->{expr.target_feature.name}"

    @override
    def _render_assignment_statement(self, target: str, value: str) -> str:
        return f"SET {target} TO {value};"

    @override
    def _library_call_needs_math(self, callee: str) -> bool:
        return callee == "COS"


_MODEL = """
package Test {{
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import TrigFunctions::*;

    part def Equipment {{
        attribute ready : Boolean;
    }}

    state def Machine {{
        attribute a : Boolean;
        attribute b : Boolean;
        attribute c : Boolean;
        attribute x : Real;
        attribute n : Integer;
        attribute label : String;
        part equipment : Equipment;

        entry;
            then idle;
        state idle {{
            entry assign n := n + 1;
        }}
        state running;

        transition first idle if {guard} then running;
    }}
}}
"""


def _guard(tmp_path: Path, guard: str) -> syside.Expression:
    model = _load_inline_model(tmp_path, _MODEL.format(guard=guard))
    expression = _single_element(model, syside.TransitionUsage).guard_expression
    assert expression is not None
    return expression


@pytest.mark.parametrize(
    ("guard", "expected"),
    [
        ("a and b or c", "@a AND @b OR @c"),
        ("(a or b) and c", "(@a OR @b) AND @c"),
        ("not a", "NOT @a"),
        ("-x < 0", "NEG @x LT 0i"),
        ("x - (n - 2) > 0", "@x MINUS (@n MINUS 2i) GT 0i"),
        ("(a == b) == c", "(@a EQ @b) EQ @c"),
        ("a == (b == c)", "@a EQ (@b EQ @c)"),
    ],
    ids=[
        "precedence",
        "lower-precedence-operand",
        "unary",
        "unary-in-binary",
        "left-associative",
        "comparison-lhs",
        "comparison-rhs",
    ],
)
def test_operators_use_the_language_spelling_and_precedence(
    tmp_path: Path, guard: str, expected: str
) -> None:
    rendered = _DummyCodeGen().render_expression(_guard(tmp_path, guard))

    assert rendered == expected


@pytest.mark.parametrize(
    ("guard", "expected"),
    [
        ("true", "#t"),
        ("n == 3", "@n EQ 3i"),
        ("x == 0.5", "@x EQ 0.5r"),
        ('label == "hi"', "@label EQ <hi>"),
        ("equipment.ready", "@equipment->ready"),
    ],
    ids=["boolean", "integer", "rational", "string", "feature-chain"],
)
def test_leaves_use_the_language_hooks(
    tmp_path: Path, guard: str, expected: str
) -> None:
    rendered = _DummyCodeGen().render_expression(_guard(tmp_path, guard))

    assert rendered == expected


def test_operator_outside_the_language_tables_is_rejected(
    tmp_path: Path,
) -> None:
    # `*` is a SysML operator the dummy language does not declare.
    with pytest.raises(ValueError, match="unsupported operator"):
        _DummyCodeGen().render_expression(_guard(tmp_path, "x * 2 > 0"))


def test_assignment_uses_the_language_statement(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, _MODEL.format(guard="true"))
    assign = _single_element(model, syside.AssignmentActionUsage)

    assert _DummyCodeGen().render_action(assign) == "SET n TO @n PLUS 1i;"


def test_library_call_uses_the_language_callee(tmp_path: Path) -> None:
    rendered = _DummyCodeGen().render_expression(_guard(tmp_path, "abs(x) > 1"))

    assert rendered == "ABS(@x) GT 1i"


@pytest.mark.parametrize(
    ("guard", "needs_math"),
    [("abs(x) > 1", False), ("cos(x) > 1", True)],
    ids=["abs", "cos"],
)
def test_library_call_reports_whether_it_needs_math(
    tmp_path: Path, guard: str, needs_math: bool
) -> None:
    comparison = _guard(tmp_path, guard)
    assert isinstance(comparison, syside.OperatorExpression)
    call = comparison.operands.collect()[0]
    assert isinstance(call, syside.InvocationExpression)

    library_call = _DummyCodeGen()._emit_library_invocation(call)

    assert library_call is not None
    assert library_call[1] is needs_math


def test_function_outside_the_language_library_is_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        _DummyError,
        match=r"NumericalFunctions::max is not in Dummy codegen's supported set",
    ):
        _DummyCodeGen().render_expression(_guard(tmp_path, "max(x, 1) > 1"))
