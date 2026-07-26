import syside
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR as SM_DIR

from sysmlc.semantics.statemachine import actions, states
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import resolve


def _idle_entry(model: syside.Model, qn: str) -> syside.ActionUsage | None:
    machine = resolve(model, syside.StateDefinition, qn)
    idle = next(s for s in states.substates(machine) if s.name == "idle")
    return idle.entry_action


def test_inline_actions_block_form() -> None:
    model = load_model(SM_DIR / "sm04-assignment")
    entry = _idle_entry(model, "SM04::MachineEntryIncrement")
    result = actions.inline_actions(entry)
    assert len(result) == 1
    assert isinstance(result[0], syside.AssignmentActionUsage)


def test_inline_actions_shorthand_form() -> None:
    model = load_model(SM_DIR / "sm04-assignment")
    entry = _idle_entry(model, "SM04::MachineEntryShorthand")
    result = actions.inline_actions(entry)
    assert len(result) == 1
    assert isinstance(result[0], syside.AssignmentActionUsage)


def test_inline_actions_multiple_statements() -> None:
    model = load_model(SM_DIR / "sm04-assignment")
    entry = _idle_entry(model, "SM04::MachineMultiEntry")
    result = actions.inline_actions(entry)
    assert len(result) == 2


def test_inline_actions_none_is_empty() -> None:
    assert actions.inline_actions(None) == []
