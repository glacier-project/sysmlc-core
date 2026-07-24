from pathlib import Path

import pytest
import syside
from sysmlc_models.catalog import model_path

from sysmlc.semantics.statemachine import states
from sysmlc.semantics.statemachine.facts import StateKind
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import resolve

SM_DIR = model_path("sm-examples")


def test_parallel_root_is_parallel_kind() -> None:
    model = load_model(SM_DIR / "sm09-parallel")
    machine = resolve(model, syside.StateDefinition, "SM09::MachineParallel")
    assert states.state_kind(machine) is StateKind.PARALLEL


def test_composite_and_leaf_kinds() -> None:
    model = load_model(SM_DIR / "sm08-nested-composite")
    machine = resolve(model, syside.StateDefinition, "SM08::MachineNested")
    assert states.state_kind(machine) is StateKind.COMPOSITE
    subs = {s.name: s for s in states.substates(machine)}
    assert states.state_kind(subs["running"]) is StateKind.COMPOSITE
    assert states.state_kind(subs["idle"]) is StateKind.LEAF


def test_state_path_strips_definition_prefix() -> None:
    model = load_model(SM_DIR / "sm08-nested-composite")
    machine = resolve(model, syside.StateDefinition, "SM08::MachineNested")
    running = next(s for s in states.substates(machine) if s.name == "running")
    assert states.state_path(machine, running) == "running"
    warming = next(s for s in states.substates(running) if s.name == "warming")
    assert states.state_path(machine, warming) == "running::warming"


def test_resolve_initial_returns_state_usage() -> None:
    model = load_model(SM_DIR / "sm08-nested-composite")
    machine = resolve(model, syside.StateDefinition, "SM08::MachineNested")
    initial = states.resolve_initial(machine)
    assert isinstance(initial, syside.StateUsage)
    assert initial.name == "idle"


def test_resolve_initial_does_not_treat_user_state_start_as_initial(
    tmp_path: Path,
) -> None:
    (tmp_path / "model.sysml").write_text(
        """
        package Test {
            state def Machine {
                state start;
                state idle;

                first start then idle;
            }
        }
        """
    )
    model = load_model(tmp_path)
    machine = resolve(model, syside.StateDefinition, "Test::Machine")

    with pytest.raises(ValueError, match="No initial state for"):
        states.resolve_initial(machine)
