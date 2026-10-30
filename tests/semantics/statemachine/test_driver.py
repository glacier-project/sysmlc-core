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


@pytest.mark.parametrize("parent_first", [False, True])
def test_declaration_order_crosses_state_container_boundaries(
    tmp_path: Path, parent_first: bool
) -> None:
    parent = "transition first outer.a accept Event then outer.parentChosen;"
    outer = """state outer {
        entry; then a;
        state a;
        state innerChosen;
        state parentChosen;
        transition first a accept Event then innerChosen;
    }"""
    declarations = parent + outer if parent_first else outer + parent
    model = _load_inline_model(
        tmp_path,
        f"""package DeclarationOrder {{
        item def Event;
        state def Machine {{
            entry; then outer;
            {declarations}
        }}
    }}""",
    )
    builder = RecordingBuilder()
    StateMachineDriver(model).run("DeclarationOrder::Machine", builder)
    # Preserve the existing fact emission order for legacy consumers.
    assert [t.target for t in builder.transitions] == [
        "outer::parentChosen",
        "outer::innerChosen",
    ]
    assert [t.declaration_order for t in builder.transitions] == (
        [0, 1] if parent_first else [1, 0]
    )
    assert {t.source for t in builder.transitions} == {"outer::a"}
