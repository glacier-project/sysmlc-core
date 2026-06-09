from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter
from sismic.model import CompoundState, OrthogonalState

from sysmlc.backends.quake import build_statechart
from sysmlc.loader import load_syside_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm09-parallel"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(EXAMPLE.model_dir)


def test_parallel_root_is_orthogonal_state(model: syside.Model) -> None:
    """A ``parallel`` state def builds as an ``OrthogonalState``.

    Per the book (§28.3): a ``parallel`` state's substates are
    non-exclusive concurrent regions.
    """
    sc = build_statechart(model, "SM09::MachineParallel")
    assert isinstance(sc.state_for("MachineParallel"), OrthogonalState)


def test_regions_are_compound_with_own_initial(model: syside.Model) -> None:
    """Each orthogonal region is a ``CompoundState`` with its own initial.

    A region is itself a composite with an ``entry; then X;`` initial.
    """
    sc = build_statechart(model, "SM09::MachineParallel")
    lights = sc.state_for("lights")
    sound = sc.state_for("sound")
    assert isinstance(lights, CompoundState)
    assert isinstance(sound, CompoundState)
    assert lights.initial == "lights::off"
    assert sound.initial == "sound::silent"


def test_region_substates_named_by_relative_path(model: syside.Model) -> None:
    """Region substates carry ``region::leaf`` names under their region."""
    sc = build_statechart(model, "SM09::MachineParallel")
    assert sc.parent_for("lights") == "MachineParallel"
    assert sc.parent_for("sound") == "MachineParallel"
    assert sc.parent_for("lights::off") == "lights"
    assert sc.parent_for("sound::silent") == "sound"


def test_execution_activates_both_regions_concurrently(
    model: syside.Model,
) -> None:
    """Executing a parallel state activates both regions at once."""
    sc = build_statechart(model, "SM09::MachineParallel")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "lights::on" in interpreter.configuration
    assert "sound::beeping" in interpreter.configuration


def test_nested_parallel_substate_is_orthogonal_state(
    model: syside.Model,
) -> None:
    """A nested ``parallel`` substate builds as an ``OrthogonalState``."""
    sc = build_statechart(model, "SM09::MachineNestedParallel")
    assert isinstance(sc.state_for("dual"), OrthogonalState)
    assert isinstance(sc.state_for("MachineNestedParallel"), CompoundState)


def test_parallel_state_emits_entry_and_exit_actions(
    model: syside.Model,
) -> None:
    """A parallel state's entry/exit assignments are emitted on the state."""
    sc = build_statechart(model, "SM09::MachineNestedParallel")
    dual = sc.state_for("dual")
    assert dual.on_entry == "count = 1"
    assert dual.on_exit == "count = 2"
