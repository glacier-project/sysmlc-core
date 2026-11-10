"""The C expression generator."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import syside

from sysmlc.codegen.c import LIBRARY_FUNCTIONS as C_LIBRARY_FUNCTIONS
from sysmlc.codegen.c import CCodeGen, CCodeGenError, c_string
from sysmlc.codegen.python import LIBRARY_FUNCTIONS
from sysmlc.semantics.statemachine.facts import CompositeValue
from sysmlc.sysml.queries import resolve
from tests import _load_inline_model, _single_element

if TYPE_CHECKING:
    from pathlib import Path

_MODEL = """
package Test {{
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import TrigFunctions::*;

    attribute def Point {{
        attribute x : Real default 0.5;
        attribute y : Integer default 2;
    }}

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
        ("a and b or c", "(a && b) || c"),
        ("a or b and c", "a || (b && c)"),
        ("(a or b) and c", "(a || b) && c"),
        ("not a", "!a"),
        ("not (a and b)", "!(a && b)"),
        ("-x < 0", "-x < 0"),
        ("x - (n - 2) > 0", "x - (n - 2) > 0"),
        ("x * 2 >= 1", "x * 2 >= 1"),
        ("a == (b == c)", "a == (b == c)"),
        ("x / 2 > 1", "(double)(x) / (2) > 1"),
        ("n + x / 2 > 1", "n + (double)(x) / (2) > 1"),
    ],
    ids=[
        "and-inside-or",
        "and-inside-or-rhs",
        "or-inside-and",
        "not",
        "not-group",
        "unary-minus",
        "left-associative",
        "multiply",
        "comparison-operand",
        "real-division",
        "division-in-sum",
    ],
)
def test_operators_use_c_spelling(
    tmp_path: Path, guard: str, expected: str
) -> None:
    assert CCodeGen().render_expression(_guard(tmp_path, guard)) == expected


@pytest.mark.parametrize(
    ("guard", "expected"),
    [
        ("true", "true"),
        ("false", "false"),
        ("n == 3", "n == 3"),
        ("x == 0.5", "x == 0.5"),
        ("x == 2.0", "x == 2.0"),
        ("equipment.ready", "equipment.ready"),
    ],
    ids=["true", "false", "integer", "rational", "whole-rational", "chain"],
)
def test_leaves_use_c_spelling(
    tmp_path: Path, guard: str, expected: str
) -> None:
    assert CCodeGen().render_expression(_guard(tmp_path, guard)) == expected


def test_string_literal_is_escaped() -> None:
    assert c_string('say "hi"\n\\') == r'"say \"hi\"\n\\"'


@pytest.mark.parametrize(
    "guard",
    [
        'label == "hi"',
        "label == label",
        'label + "a" == label',
        "label < label",
    ],
    ids=["literal", "attributes", "concatenation", "ordering"],
)
def test_string_operations_are_rejected(tmp_path: Path, guard: str) -> None:
    with pytest.raises(CCodeGenError, match="String"):
        CCodeGen().render_expression(_guard(tmp_path, guard))


def test_double_sign_is_not_a_decrement(tmp_path: Path) -> None:
    rendered = CCodeGen().render_expression(_guard(tmp_path, "-(-x) > 0"))

    assert rendered == "-(-x) > 0"


def test_assignment_is_a_c_statement(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, _MODEL.format(guard="true"))
    assign = _single_element(model, syside.AssignmentActionUsage)

    assert CCodeGen().render_action(assign) == "n = n + 1;"


@pytest.mark.parametrize(
    ("guard", "expected"),
    [
        ("abs(x) > 1", "fabs(x) > 1"),
        ("max(x, 1) > 1", "fmax(x, 1) > 1"),
        ("cos(x) > 1", "cos(x) > 1"),
    ],
    ids=["abs", "max", "cos"],
)
def test_library_calls_use_math_h(
    tmp_path: Path, guard: str, expected: str
) -> None:
    assert CCodeGen().render_expression(_guard(tmp_path, guard)) == expected


def test_library_covers_every_shared_function() -> None:
    assert set(C_LIBRARY_FUNCTIONS) == set(LIBRARY_FUNCTIONS)


def test_composite_value_is_a_compound_literal(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, _MODEL.format(guard="true"))
    point = resolve(model, syside.AttributeDefinition, "Test::Point")
    x = resolve(model, syside.AttributeUsage, "Test::Point::x")
    y = resolve(model, syside.AttributeUsage, "Test::Point::y")
    value = CompositeValue(
        (
            ("x", x.feature_value_expression),
            ("y", y.feature_value_expression),
        ),
        "Point",
        point,
    )
    assert CCodeGen().render_value(value) == "(Point){ .x = 0.5, .y = 2 }"


def test_nested_value_is_one_compound_literal(tmp_path: Path) -> None:
    # A static initializer may not hold a nested compound literal.
    model = _load_inline_model(tmp_path, _MODEL.format(guard="true"))
    point = resolve(model, syside.AttributeDefinition, "Test::Point")
    inner = CompositeValue((("x", 0.25),), "Point", point)
    outer = CompositeValue((("y", inner),), "Point", point)

    assert CCodeGen().render_value(outer) == "(Point){ .y = { .x = 0.25 } }"


def test_unspecified_field_is_left_zero(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, _MODEL.format(guard="true"))
    point = resolve(model, syside.AttributeDefinition, "Test::Point")
    value = CompositeValue((("x", None), ("y", None)), "Point", point)

    assert CCodeGen().render_value(value) == "(Point){ 0 }"


def test_float_value_keeps_a_decimal_point() -> None:
    assert CCodeGen().render_value(3.0) == "3.0"


_ENUM_MODEL = """
package Grades {
    private import ScalarValues::*;

    enum def Grade :> Real {
        enum a = 4.0;
        enum b = 3.0;
    }

    state def Machine {
        attribute g : Grade := Grade::a;
        entry;
            then grading;
        state grading;
        state passed;
        transition first grading if g >= Grade::b then passed;
    }
}
"""


def test_ordering_enumeration_literals_is_rejected(tmp_path: Path) -> None:
    # C enumeration constants are positions, not the literals' values.
    model = _load_inline_model(tmp_path, _ENUM_MODEL)
    guard = _single_element(model, syside.TransitionUsage).guard_expression
    assert guard is not None

    with pytest.raises(CCodeGenError, match="ordered"):
        CCodeGen().render_expression(guard)
