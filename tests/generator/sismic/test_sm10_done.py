from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter
from sismic.model import FinalState

from sysmlc.generator.sismic import build_statechart
from sysmlc.loader import load_syside_model
from tests.generator.sismic.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside
    from sismic.model import Statechart

EXAMPLE = SM_EXAMPLES_BY_DIR["sm10-done"]


def _has_transition(sc: Statechart, source: str, target: str) -> bool:
    """Whether ``sc`` has a transition from ``source`` to ``target``."""
    return any(
        t.source == source and t.target == target for t in sc.transitions
    )


def _final_states(sc: Statechart) -> list[str]:
    """The names of every ``FinalState`` in ``sc``, sorted."""
    return sorted(
        name for name in sc.states if isinstance(sc.state_for(name), FinalState)
    )


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(EXAMPLE.model_dir)


def test_root_done_synthesizes_final_state(model: syside.Model) -> None:
    """A root-level ``then done`` becomes a ``FinalState`` named ``done``."""
    sc = build_statechart(model, "SM10::MachineRootDone")
    assert isinstance(sc.state_for("done"), FinalState)
    assert sc.parent_for("done") == "MachineRootDone"


def test_root_done_transition_targets_final(model: syside.Model) -> None:
    """The root ``then done`` transition is pointed at the final state."""
    sc = build_statechart(model, "SM10::MachineRootDone")
    assert _has_transition(sc, "running", "done")


def test_root_done_synthesized_once(model: syside.Model) -> None:
    """The root scope gets exactly one ``done`` final state."""
    sc = build_statechart(model, "SM10::MachineRootDone")
    assert _final_states(sc) == ["done"]


def test_nested_done_final_scoped_under_composite(
    model: syside.Model,
) -> None:
    """A ``then done`` inside a composite gets a scope-named final."""
    sc = build_statechart(model, "SM10::MachineNestedDone")
    assert isinstance(sc.state_for("running::done"), FinalState)
    assert sc.parent_for("running::done") == "running"
    assert _final_states(sc) == ["running::done"]


def test_nested_done_transition_targets_scoped_final(
    model: syside.Model,
) -> None:
    """The nested ``then done`` transition targets the scoped final."""
    sc = build_statechart(model, "SM10::MachineNestedDone")
    assert _has_transition(sc, "running::hot", "running::done")


def test_parallel_region_dones_are_scoped_finals(
    model: syside.Model,
) -> None:
    """Each region's ``then done`` becomes a final under that region."""
    sc = build_statechart(model, "SM10::MachineParallelDone")
    assert isinstance(sc.state_for("lights::done"), FinalState)
    assert isinstance(sc.state_for("sound::done"), FinalState)
    assert sc.parent_for("lights::done") == "lights"
    assert sc.parent_for("sound::done") == "sound"
    assert _has_transition(sc, "lights::on", "lights::done")
    assert _has_transition(sc, "sound::beeping", "sound::done")


def test_root_done_completes_machine(model: syside.Model) -> None:
    """Reaching a root-level ``done`` completes the whole machine."""
    sc = build_statechart(model, "SM10::MachineRootDone")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert interpreter.configuration == []
    assert interpreter.final


def test_nested_done_keeps_machine_alive(model: syside.Model) -> None:
    """A nested ``done`` completes its region, not the whole machine."""
    sc = build_statechart(model, "SM10::MachineNestedDone")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "stopped" in interpreter.configuration
    assert not interpreter.final


def test_two_dones_in_one_scope_share_final(model: syside.Model) -> None:
    """Two ``then done`` in one scope share a single ``FinalState``."""
    sc = build_statechart(model, "SM10::MachineTwoDone")
    assert _final_states(sc) == ["done"]
    assert _has_transition(sc, "idle", "done")
    assert _has_transition(sc, "running", "done")
