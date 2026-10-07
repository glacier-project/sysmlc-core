from pathlib import Path

import pytest
import syside
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR as SM_DIR

from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import StateKind
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model
from tests.test_recording import RecordingBuilder


def test_driver_walks_simple_machine(
    recording_builder: RecordingBuilder,
) -> None:
    model = load_model(SM_DIR / "sm01-helloworld")
    StateMachineDriver(model).run("SM01::Machine", recording_builder)

    by_name = {state.name: state for state in recording_builder.states}
    assert by_name["Machine"].kind is StateKind.COMPOSITE
    assert by_name["Machine"].initial_substate == "idle"
    assert by_name["idle"].kind is StateKind.LEAF
    assert by_name["running"].kind is StateKind.LEAF

    edges = {(t.source, t.target) for t in recording_builder.transitions}
    assert edges == {("idle", "running")}
    assert recording_builder.attributes == []


@pytest.mark.parametrize(
    ("second_guard", "enabled"),
    [
        ("not ready", [True, False]),
        ("ready", [True, True]),
    ],
)
def test_driver_preserves_exclusive_and_competing_guards(
    tmp_path: Path,
    second_guard: str,
    enabled: list[bool],
) -> None:
    model = _load_inline_model(
        tmp_path,
        f"""
        package Guards {{
            private import ScalarValues::*;
            item def Tick;
            state def Machine {{
                attribute ready : Boolean := true;
                entry; then idle;
                state idle;
                state a;
                state b;
                transition first idle accept Tick if ready then a;
                transition first idle accept Tick if {second_guard} then b;
            }}
        }}
    """,
    )
    builder = RecordingBuilder()
    StateMachineDriver(model).run("Guards::Machine", builder)
    assert [(t.source, t.target) for t in builder.transitions] == [
        ("idle", "a"),
        ("idle", "b"),
    ]
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    evaluated = []
    for transition in builder.transitions:
        assert transition.guard is not None
        evaluated.append(compiler.evaluate(transition.guard, stdlib=stdlib)[0])
    assert evaluated == enabled
