from pathlib import Path

import syside

from sysmlc.semantics.statemachine import states, transitions
from sysmlc.semantics.statemachine.facts import (
    CompletionTarget,
    TransitionFact,
    Trigger,
    TriggerKind,
)
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import resolve

SM_DIR = Path(__file__).resolve().parents[3] / "models" / "sm-examples"


def _transition_from(
    state_def: syside.StateDefinition,
    container: syside.StateDefinition | syside.StateUsage,
    source_name: str,
) -> syside.TransitionUsage:
    for trans in transitions.container_transitions(container):
        if transitions.source_path(state_def, trans) == source_name:
            return trans
    raise AssertionError(f"no transition from {source_name!r}")


def test_root_done_yields_completion_target_root_scope() -> None:
    model = load_model(SM_DIR / "sm10-done")
    machine = resolve(model, syside.StateDefinition, "SM10::MachineRootDone")
    trans = _transition_from(machine, machine, "running")
    assert transitions.target(machine, trans, machine) == CompletionTarget(
        scope=""
    )


def test_nested_done_yields_scoped_completion_target() -> None:
    model = load_model(SM_DIR / "sm10-done")
    machine = resolve(model, syside.StateDefinition, "SM10::MachineNestedDone")
    running = next(s for s in states.substates(machine) if s.name == "running")
    trans = _transition_from(machine, running, "running::hot")
    assert transitions.target(machine, trans, running) == CompletionTarget(
        scope="running"
    )


def test_cross_boundary_target_is_dotted_path() -> None:
    model = load_model(SM_DIR / "sm08-nested-composite")
    machine = resolve(model, syside.StateDefinition, "SM08::MachineCrossIn")
    trans = _transition_from(machine, machine, "idle")
    assert transitions.target(machine, trans, machine) == "running::hot"


def test_self_loop_detection() -> None:
    unstable = TransitionFact(
        source="a", target="a", trigger=None, guard=None, effect=None
    )
    assert transitions.self_loop_is_unstable(unstable) is True

    with_event = TransitionFact(
        source="a",
        target="a",
        trigger=Trigger(TriggerKind.SIGNAL, signal_name="E"),
        guard=None,
        effect=None,
    )
    assert transitions.self_loop_is_unstable(with_event) is False

    non_self = TransitionFact(
        source="a", target="b", trigger=None, guard=None, effect=None
    )
    assert transitions.self_loop_is_unstable(non_self) is False

    to_completion = TransitionFact(
        source="a",
        target=CompletionTarget(scope=""),
        trigger=None,
        guard=None,
        effect=None,
    )
    assert transitions.self_loop_is_unstable(to_completion) is False
