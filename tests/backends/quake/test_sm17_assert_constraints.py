from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.exceptions import InvariantError
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.backends.quake.serialize import to_yaml
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm17-assert-constraints"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


def test_constraints_attach_to_root_and_substate(
    model: syside.Model,
) -> None:
    sc = build_statechart(model, "SM17::MachineScoped")

    assert sc.state_for("MachineScoped").invariants == ["level > 0.0"]
    assert sc.state_for("idle").invariants == ["level <= 2.0"]
    Interpreter(sc).execute()


def test_counter_constraint_fails_after_limit_is_exceeded(
    model: syside.Model,
) -> None:
    sc = build_statechart(model, "SM17::MachineCounterLimit")
    assert sc.state_for("MachineCounterLimit").invariants == [
        "counter <= maxCount"
    ]

    interpreter = Interpreter(sc)
    interpreter.execute()
    interpreter.queue("Tick")
    interpreter.execute()
    assert interpreter.context["counter"] == 1

    interpreter.queue("Tick")
    with pytest.raises(InvariantError):
        interpreter.execute()


def test_constraint_serializes_as_yaml_contract(model: syside.Model) -> None:
    sc = build_statechart(model, "SM17::MachineScoped")

    text = to_yaml(sc)

    assert "contract:" in text
    assert "always: level > 0.0" in text
    assert "always: level <= 2.0" in text


def test_constraint_preamble_uses_direct_math_import(
    model: syside.Model,
) -> None:
    sc = build_statechart(model, "SM17::MachineFunctionViolation")

    lines = sc.preamble.splitlines()
    assert lines[:2] == [
        "from math import cos, sin, tan",
        "from types import SimpleNamespace",
    ]
    assert sc.state_for("MachineFunctionViolation").invariants == [
        "cos(x) <= 0.0"
    ]


def test_function_constraint_violation_is_enforced_by_sismic(
    model: syside.Model,
) -> None:
    sc = build_statechart(model, "SM17::MachineFunctionViolation")
    assert sc.state_for("MachineFunctionViolation").invariants == [
        "cos(x) <= 0.0"
    ]

    interpreter = Interpreter(sc)
    interpreter.execute()
    interpreter.queue("Tick")

    with pytest.raises(InvariantError):
        interpreter.execute()
