from pathlib import Path

import pytest
import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions
from sysmlc.semantics.statemachine.interface import machine_interface
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import resolve


@pytest.fixture(scope="module")
def phase_model() -> syside.Model:
    return load_model(Path(__file__).parent / "fixtures" / "phase-actions")


@pytest.mark.parametrize("phase", ["entry", "exit", "effect"])
@pytest.mark.parametrize(
    "form", ["Reference", "ReferenceLocal", "Subsetting", "Typed", "TypedLocal"]
)
def test_referenced_phase_action_is_rejected(
    phase_model: syside.Model, phase: str, form: str
) -> None:
    # Valid SysML actions must fail explicitly, including typed wrappers
    # whose local statements cannot replace the inherited action body.
    with pytest.raises(UnsupportedConstructError, match=phase) as error:
        machine_interface(phase_model, f"PhaseActions::{phase.title()}{form}")
    machine = resolve(
        phase_model,
        syside.StateDefinition,
        f"PhaseActions::{phase.title()}{form}",
    )
    if phase == "effect":
        slot = machine.owned_transitions.collect()[0].effect_action
    else:
        slot = getattr(machine.owned_states.collect()[0], f"{phase}_action")
    assert error.value.node is slot


@pytest.mark.parametrize("phase", ["entry", "exit", "effect", "do"])
@pytest.mark.parametrize(
    "form", ["Reference", "ReferenceLocal", "Subsetting", "Typed", "TypedLocal"]
)
def test_inline_extraction_rejects_the_source_slot(
    phase_model: syside.Model, phase: str, form: str
) -> None:
    machine = resolve(
        phase_model,
        syside.StateDefinition,
        f"PhaseActions::{phase.title()}{form}",
    )
    if phase == "effect":
        slot = machine.owned_transitions.collect()[0].effect_action
    else:
        state = machine.owned_states.collect()[0]
        slot = getattr(state, f"{phase}_action")
    with pytest.raises(UnsupportedConstructError, match=phase) as error:
        actions.inline_actions(slot)
    assert error.value.node is slot


@pytest.mark.parametrize("form", ["Reference", "Typed", "TypedLocal"])
def test_existing_do_rejection_is_preserved(
    phase_model: syside.Model, form: str
) -> None:
    machine = resolve(
        phase_model, syside.StateDefinition, f"PhaseActions::Do{form}"
    )
    slot = machine.owned_states.collect()[0].do_action
    assert slot is not None
    with pytest.raises(
        UnsupportedConstructError, match="only inline `assign`/`send`"
    ) as error:
        actions.require_inline_one_shot(slot)
    assert error.value.node is slot


@pytest.mark.parametrize("state_name", ["named", "anonymous", "shorthand"])
def test_inline_assignment_and_send_are_preserved(
    phase_model: syside.Model, state_name: str
) -> None:
    machine = resolve(
        phase_model, syside.StateDefinition, "InlineControls::Machine"
    )
    state = next(
        s for s in machine.owned_states.collect() if s.name == state_name
    )
    (assignment,) = actions.inline_actions(state.entry_action)
    (send,) = actions.inline_actions(state.exit_action)
    assert isinstance(assignment, syside.AssignmentActionUsage)
    assert isinstance(send, syside.SendActionUsage)


def test_inline_effects_and_empty_slots_are_preserved(
    phase_model: syside.Model,
) -> None:
    machine = resolve(
        phase_model, syside.StateDefinition, "InlineControls::Machine"
    )
    for state in machine.owned_states.collect():
        if state.name in ("empty", "absent"):
            assert actions.inline_actions(state.entry_action) == []
            assert actions.inline_actions(state.exit_action) == []
    effects = [
        actions.inline_actions(t.effect_action)
        for t in machine.owned_transitions.collect()
    ]
    assert [type(effect[0]) for effect in effects] == [
        syside.AssignmentActionUsage,
        syside.AssignmentActionUsage,
        syside.AssignmentActionUsage,
        syside.SendActionUsage,
    ]
    assert machine_interface(phase_model, "InlineControls::Machine").sent == {
        "Ping"
    }
