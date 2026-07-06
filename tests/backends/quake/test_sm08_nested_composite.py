from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter
from sismic.model import BasicState, CompoundState

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR, has_transition

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm08-nested-composite"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


def test_composite_substate_is_compound_not_basic(model: syside.Model) -> None:
    """A substate that owns substates becomes a ``CompoundState``."""
    sc = build_statechart(model, "SM08::MachineNested")
    assert isinstance(sc.state_for("running"), CompoundState)
    assert isinstance(sc.state_for("idle"), BasicState)


def test_nested_initial_uses_relative_path(model: syside.Model) -> None:
    """A composite's ``initial`` is its entry-selected substate's path."""
    sc = build_statechart(model, "SM08::MachineNested")
    assert sc.state_for("running").initial == "running::warming"


def test_nested_substates_named_by_relative_path(model: syside.Model) -> None:
    """Nested substates carry ``parent::child`` names under their parent."""
    sc = build_statechart(model, "SM08::MachineNested")
    assert "running::warming" in sc.states
    assert "running::hot" in sc.states
    assert sc.parent_for("running::warming") == "running"
    assert sc.parent_for("running::hot") == "running"
    assert sc.parent_for("idle") == "MachineNested"


def test_within_composite_transition_uses_relative_paths(
    model: syside.Model,
) -> None:
    """A transition inside a composite connects relative-path endpoints."""
    sc = build_statechart(model, "SM08::MachineNested")
    assert has_transition(sc, "running::warming", "running::hot")


def test_three_level_nesting_recurses(model: syside.Model) -> None:
    """Nesting recurses past one level."""
    sc = build_statechart(model, "SM08::MachineDeep")
    warming = sc.state_for("running::warming")
    assert isinstance(warming, CompoundState)
    assert warming.initial == "running::warming::low"
    assert "running::warming::low" in sc.states
    assert "running::warming::high" in sc.states


def test_name_collision_disambiguated_by_relative_path(
    model: syside.Model,
) -> None:
    """Substates sharing a name across composites do not collide."""
    sc = build_statechart(model, "SM08::MachineNameCollision")
    for name in (
        "groupA::active",
        "groupA::paused",
        "groupB::active",
        "groupB::paused",
    ):
        assert name in sc.states
    assert has_transition(sc, "groupA::active", "groupA::paused")
    assert has_transition(sc, "groupB::active", "groupB::paused")


def test_execution_descends_into_composite(model: syside.Model) -> None:
    """Executing the machine descends through the built hierarchy."""
    sc = build_statechart(model, "SM08::MachineNested")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "running" in interpreter.configuration
    assert "running::hot" in interpreter.configuration


def test_cross_boundary_out_resolves_dotted_source(
    model: syside.Model,
) -> None:
    """A transition out of a deep state resolves its dotted source."""
    sc = build_statechart(model, "SM08::MachineCrossOut")
    assert has_transition(sc, "running::hot", "stopped")


def test_cross_boundary_in_resolves_dotted_target(
    model: syside.Model,
) -> None:
    """A transition into a deep state resolves its dotted target."""
    sc = build_statechart(model, "SM08::MachineCrossIn")
    assert has_transition(sc, "idle", "running::hot")


def test_cross_boundary_in_enters_specified_deep_state(
    model: syside.Model,
) -> None:
    """Entering a deep state directly bypasses the composite's initial."""
    sc = build_statechart(model, "SM08::MachineCrossIn")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "running::hot" in interpreter.configuration
    assert "running::warming" not in interpreter.configuration
