from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

import syside

from sysmlc.codegen.python import PythonCodeGen, PythonCodeGenContext
from tests import _load_inline_model, _single_element


def _get_py_codegen(quote: str) -> PythonCodeGen:
    context = PythonCodeGenContext(string_delimiter=quote)
    return PythonCodeGen(context)


@dataclass(frozen=True)
class OperatorCase:
    """One operator-grammar shape rendered by ``render_expression``.

    Attributes:
        case_id: Test id.
        attributes: SysML attribute declarations the guard needs, one
            complete declaration per tuple entry.
        guard: SysML guard expression source text.
        expected: Python source ``render_expression`` must emit.
    """

    case_id: str
    attributes: tuple[str, ...]
    guard: str
    expected: str


OPERATOR_CASES: list[OperatorCase] = [
    OperatorCase("literal-true", (), "true", "True"),
    OperatorCase("literal-false", (), "false", "False"),
    OperatorCase(
        "bare-reference",
        ("attribute enabled : Boolean := true;",),
        "enabled",
        "enabled",
    ),
    OperatorCase(
        "not",
        ("attribute enabled : Boolean := false;",),
        "not enabled",
        "not enabled",
    ),
    OperatorCase(
        "unary-minus",
        ("attribute x : Integer := 1;",),
        "-x < 0",
        "-x < 0",
    ),
    OperatorCase(
        "and",
        (
            "attribute a : Boolean := true;",
            "attribute b : Boolean := true;",
        ),
        "a and b",
        "a and b",
    ),
    OperatorCase(
        "or",
        (
            "attribute a : Boolean := true;",
            "attribute b : Boolean := false;",
        ),
        "a or b",
        "a or b",
    ),
    OperatorCase(
        "eq",
        ("attribute x : Integer := 1;",),
        "x == 1",
        "x == 1",
    ),
    OperatorCase(
        "neq",
        ("attribute x : Integer := 1;",),
        "x != 0",
        "x != 0",
    ),
    OperatorCase(
        "lt",
        ("attribute x : Integer := 1;",),
        "x < 2",
        "x < 2",
    ),
    OperatorCase(
        "le",
        ("attribute x : Integer := 1;",),
        "x <= 1",
        "x <= 1",
    ),
    OperatorCase(
        "gt",
        ("attribute x : Integer := 1;",),
        "x > 0",
        "x > 0",
    ),
    OperatorCase(
        "ge",
        ("attribute x : Integer := 1;",),
        "x >= 1",
        "x >= 1",
    ),
    OperatorCase(
        "arith-plus",
        ("attribute x : Integer := 1;",),
        "x + 1 > 1",
        "x + 1 > 1",
    ),
    OperatorCase(
        "arith-minus",
        ("attribute x : Integer := 2;",),
        "x - 1 > 0",
        "x - 1 > 0",
    ),
    OperatorCase(
        "arith-mul",
        ("attribute x : Integer := 2;",),
        "x * 2 > 1",
        "x * 2 > 1",
    ),
    OperatorCase(
        "arith-div",
        ("attribute x : Integer := 4;",),
        "x / 2 > 1",
        "x / 2 > 1",
    ),
    OperatorCase(
        "real-literal",
        ("attribute x : Real := 1.0;",),
        "x > 0.5",
        "x > 0.5",
    ),
    OperatorCase(
        "logical-chain",
        (
            "attribute a : Boolean := true;",
            "attribute b : Boolean := true;",
            "attribute c : Boolean := false;",
        ),
        "a and b or c",
        "a and b or c",
    ),
    OperatorCase(
        "lower-prec-lhs",
        (
            "attribute a : Boolean := true;",
            "attribute b : Boolean := false;",
            "attribute c : Boolean := true;",
        ),
        "(a or b) and c",
        "(a or b) and c",
    ),
    OperatorCase(
        "left-assoc-rhs",
        ("attribute x : Integer := 5;",),
        "x - (1 - 2) > 0",
        "x - (1 - 2) > 0",
    ),
]

_GUARD_MODEL_TEMPLATE = """
package Test {{
    private import ScalarValues::*;

    state def Machine {{
{attributes}
        entry;
            then idle;
        state idle;
        state running;

        transition first idle if {guard} then running;
    }}
}}
"""


def _guard_model_source(case: OperatorCase) -> str:
    attribute_block = "\n".join(
        f"        {declaration}" for declaration in case.attributes
    )
    return _GUARD_MODEL_TEMPLATE.format(
        attributes=attribute_block, guard=case.guard
    )


class TestPythonCodeGen:
    def test_nested_comparison_lhs_is_parenthesized(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        code_gen = _get_py_codegen(string_delimiter)
        model = _load_inline_model(
            tmp_path,
            """
            package Test {
                private import ScalarValues::*;

                state def Machine {
                    attribute a : Integer := 1;
                    attribute b : Integer := 2;
                    attribute c : Boolean := true;

                    entry;
                        then idle;
                    state idle;
                    state running;

                    transition first idle if (a < b) == c then running;
                }
            }
            """,
        )

        trans = _single_element(model, syside.TransitionUsage)

        assert trans.guard_expression is not None
        assert (
            code_gen.render_expression(trans.guard_expression) == "(a < b) == c"
        )

    def test_nested_comparison_rhs_is_parenthesized(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        code_gen = _get_py_codegen(string_delimiter)
        model = _load_inline_model(
            tmp_path,
            """
            package Test {
                private import ScalarValues::*;

                state def Machine {
                    attribute a : Integer := 1;
                    attribute b : Integer := 2;
                    attribute c : Boolean := true;

                    entry;
                        then idle;
                    state idle;
                    state running;

                    transition first idle if c == (a < b) then running;
                }
            }
            """,
        )

        trans = _single_element(model, syside.TransitionUsage)

        assert trans.guard_expression is not None
        assert (
            code_gen.render_expression(trans.guard_expression) == "c == (a < b)"
        )

    def test_simple_assignment_target_is_emitted(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        code_gen = _get_py_codegen(string_delimiter)
        model = _load_inline_model(
            tmp_path,
            """
            package Test {
                private import ScalarValues::*;

                state def Machine {
                    attribute counter : Integer := 0;

                    entry;
                        then idle;
                    state idle {
                        entry assign counter := counter + 1;
                    }
                    state running;

                    transition first idle then running;
                }
            }
            """,
        )

        assign = _single_element(model, syside.AssignmentActionUsage)
        emitted = code_gen.render_action(assign)

        assert code_gen.render_assignment_target(assign) == "counter"
        assert code_gen.render_assignment(assign) == "counter = counter + 1"
        assert emitted == "counter = counter + 1"

    def test_chained_assignment_target_to_ref_is_emitted(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        code_gen = _get_py_codegen(string_delimiter)
        model = _load_inline_model(
            tmp_path,
            """
            package Test {
                private import ScalarValues::*;

                part def Equipment {
                    attribute flag : Boolean;
                }

                state def Machine {
                    in ref equipment : Equipment;

                    entry;
                        then idle;
                    state idle {
                        entry assign equipment.flag := true;
                    }
                    state running;

                    transition first idle then running;
                }
            }
            """,
        )

        assign = _single_element(model, syside.AssignmentActionUsage)
        emitted = code_gen.render_action(assign)

        assert code_gen.render_assignment_target(assign) == "equipment.flag"
        assert code_gen.render_assignment(assign) == "equipment.flag = True"
        assert emitted == "equipment.flag = True"

    def test_string_literals_emit_valid_python_that_round_trips(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        code_gen = _get_py_codegen(string_delimiter)
        model = _load_inline_model(
            tmp_path,
            r"""
            package Test {
                private import ScalarValues::*;

                state def Machine {
                    attribute plain : String := "hello";
                    attribute with_double_quote : String := "say \"hi\"";
                    attribute with_single_quote : String := "it's";
                    attribute with_backslash : String := "C:\\new";

                    entry;
                        then idle;
                    state idle;
                    state running;

                    transition first idle then running;
                }
            }
            """,
        )

        literals = list(
            model.elements(syside.LiteralString, include_subtypes=True)
        )
        assert len(literals) == 4

        for literal in literals:
            emitted = code_gen.render_expression(literal)
            assert ast.literal_eval(emitted) == literal.value

    @pytest.mark.parametrize(
        "case", OPERATOR_CASES, ids=lambda case: case.case_id
    )
    def test_operator_grammar_renders_expected_python(
        self, case: OperatorCase, tmp_path: Path
    ) -> None:
        code_gen = _get_py_codegen('"')
        model = _load_inline_model(tmp_path, _guard_model_source(case))

        trans = _single_element(model, syside.TransitionUsage)

        assert trans.guard_expression is not None
        assert (
            code_gen.render_expression(trans.guard_expression) == case.expected
        )
