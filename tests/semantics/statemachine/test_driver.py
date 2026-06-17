from pathlib import Path

from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import StateKind
from sysmlc.sysml.loading import load_model
from tests.test_recording import RecordingBuilder

SM_DIR = Path(__file__).resolve().parents[3] / "models" / "sm-examples"


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
