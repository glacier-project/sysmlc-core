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


def test_composite_builds_hierarchy_and_execution_descends(
    model: syside.Model,
) -> None:
    """A substate owning substates becomes a CompoundState subtree.

    The composite carries relative-path children and its
    entry-selected initial, the within-composite transition connects
    relative-path endpoints, and execution descends through the built
    hierarchy to the transition's target.
    """
    sc = build_statechart(model, "SM08::MachineNested")
    assert isinstance(sc.state_for("running"), CompoundState)
    assert isinstance(sc.state_for("idle"), BasicState)
    assert sc.state_for("running").initial == "running::warming"
    assert "running::warming" in sc.states
    assert "running::hot" in sc.states
    assert sc.parent_for("running::warming") == "running"
    assert sc.parent_for("running::hot") == "running"
    assert sc.parent_for("idle") == "MachineNested"
    assert has_transition(sc, "running::warming", "running::hot")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "running" in interpreter.configuration
    assert "running::hot" in interpreter.configuration


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


def test_cross_boundary_out_resolves_dotted_source(
    model: syside.Model,
) -> None:
    """A transition out of a deep state resolves its dotted source."""
    sc = build_statechart(model, "SM08::MachineCrossOut")
    assert has_transition(sc, "running::hot", "stopped")


def test_cross_boundary_in_targets_and_enters_deep_state(
    model: syside.Model,
) -> None:
    """A transition into a deep state resolves and enters its target.

    The dotted target resolves at build time; entering the deep state
    directly bypasses the composite's initial.
    """
    sc = build_statechart(model, "SM08::MachineCrossIn")
    assert has_transition(sc, "idle", "running::hot")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "running::hot" in interpreter.configuration
    assert "running::warming" not in interpreter.configuration
