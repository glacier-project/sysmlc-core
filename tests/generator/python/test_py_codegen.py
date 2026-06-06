from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import syside

from sysml2frost.generator.python.py_codegen import PyCodeGen, PyCodeGenContext

from .. import _load_inline_model, _single_element


def _get_py_codegen(quote: str) -> PyCodeGen:
    context = PyCodeGenContext(string_delimiter=quote)
    return PyCodeGen(context)


class TestPyCodeGen:
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
            code_gen.emit_expression(trans.guard_expression) == "(a < b) == c"
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
            code_gen.emit_expression(trans.guard_expression) == "c == (a < b)"
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
        emitted = code_gen.emit_action(assign)

        assert code_gen.emit_assignment_target(assign) == "counter"
        assert code_gen.emit_assignment(assign) == "counter = counter + 1"
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
        emitted = code_gen.emit_action(assign)

        assert code_gen.emit_assignment_target(assign) == "equipment.flag"
        assert code_gen.emit_assignment(assign) == "equipment.flag = True"
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
            emitted = code_gen.emit_expression(literal)
            assert ast.literal_eval(emitted) == literal.value
