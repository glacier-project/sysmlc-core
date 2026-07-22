from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter
from sismic.model import FinalState

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR, has_transition

if TYPE_CHECKING:
    import syside
    from sismic.model import Statechart

EXAMPLE = SM_EXAMPLES_BY_DIR["sm10-done"]


def _final_states(sc: Statechart) -> list[str]:
    """The names of every ``FinalState`` in ``sc``, sorted."""
    return sorted(
        name for name in sc.states if isinstance(sc.state_for(name), FinalState)
    )


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


def test_root_done_synthesizes_one_final_and_completes_machine(
    model: syside.Model,
) -> None:
    """A root ``then done`` becomes one FinalState that ends the run.

    The root scope gets exactly one ``FinalState`` named ``done``, the
    transition points at it, and reaching it completes the whole
    machine.
    """
    sc = build_statechart(model, "SM10::MachineRootDone")
    assert sc.parent_for("done") == "MachineRootDone"
    assert _final_states(sc) == ["done"]
    assert has_transition(sc, "running", "done")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert interpreter.configuration == []
    assert interpreter.final


def test_nested_done_scoped_final_completes_region_only(
    model: syside.Model,
) -> None:
    """A ``then done`` inside a composite ends that region, not the run.

    The final state is scope-named under the composite, the transition
    targets it, and reaching it leaves the rest of the machine alive.
    """
    sc = build_statechart(model, "SM10::MachineNestedDone")
    assert sc.parent_for("running::done") == "running"
    assert _final_states(sc) == ["running::done"]
    assert has_transition(sc, "running::hot", "running::done")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "stopped" in interpreter.configuration
    assert not interpreter.final


def test_parallel_region_dones_are_scoped_finals(
    model: syside.Model,
) -> None:
    """Each region's ``then done`` becomes a final under that region."""
    sc = build_statechart(model, "SM10::MachineParallelDone")
    assert isinstance(sc.state_for("lights::done"), FinalState)
    assert isinstance(sc.state_for("sound::done"), FinalState)
    assert sc.parent_for("lights::done") == "lights"
    assert sc.parent_for("sound::done") == "sound"
    assert has_transition(sc, "lights::on", "lights::done")
    assert has_transition(sc, "sound::beeping", "sound::done")


def test_two_dones_in_one_scope_share_final(model: syside.Model) -> None:
    """Two ``then done`` in one scope share a single ``FinalState``."""
    sc = build_statechart(model, "SM10::MachineTwoDone")
    assert _final_states(sc) == ["done"]
    assert has_transition(sc, "idle", "done")
    assert has_transition(sc, "running", "done")


def test_parallel_completion_waits_for_every_region(
    model: syside.Model,
) -> None:
    """A completion transition leaving a parallel state is a join.

    ``working`` has two regions, ``a`` and ``b``, each reaching its own
    scoped ``done`` on a distinct event. The eventless transition first
    working then finished may fire only once *both* regions have
    completed, not as soon as the first one does.
    """
    sc = build_statechart(model, "SM10::MachineParallelJoin")
    assert has_transition(sc, "working", "finished")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "working::a::a1" in interpreter.configuration
    assert "working::b::b1" in interpreter.configuration

    interpreter.queue("EventA")
    interpreter.execute()
    assert "working::a::done" in interpreter.configuration
    assert "working::b::b1" in interpreter.configuration
    assert "finished" not in interpreter.configuration

    interpreter.queue("EventB")
    interpreter.execute()
    assert interpreter.configuration == ["MachineParallelJoin", "finished"]
