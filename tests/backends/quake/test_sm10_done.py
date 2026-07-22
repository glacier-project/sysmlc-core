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


def test_composite_completion_waits_for_inner_done(
    model: syside.Model,
) -> None:
    """A completion transition leaving a plain composite is a join of one.

    ``working`` is an ordinary composite whose own ``done`` is reached only
    after ``EventA`` arrives. The eventless transition first working then
    finished may fire only once ``working`` has completed, not as soon as
    the composite is entered.
    """
    sc = build_statechart(model, "SM10::MachineCompositeJoin")
    assert has_transition(sc, "working", "finished")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "working::w1" in interpreter.configuration
    assert "finished" not in interpreter.configuration

    interpreter.queue("EventA")
    interpreter.execute()
    assert interpreter.configuration == ["MachineCompositeJoin", "finished"]


def test_parallel_join_waits_for_all_three_regions(
    model: syside.Model,
) -> None:
    """A three-region join fires only once every region completes.

    ``working`` has three regions, each reaching its own scoped ``done``
    on a distinct event. With two of the three complete the join must not
    fire; only the third completion releases it.
    """
    sc = build_statechart(model, "SM10::MachineParallelJoinThree")
    assert has_transition(sc, "working", "finished")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "working::a::a1" in interpreter.configuration
    assert "working::b::b1" in interpreter.configuration
    assert "working::c::c1" in interpreter.configuration

    interpreter.queue("EventA")
    interpreter.execute()
    interpreter.queue("EventB")
    interpreter.execute()
    assert "working::a::done" in interpreter.configuration
    assert "working::b::done" in interpreter.configuration
    assert "working::c::c1" in interpreter.configuration
    assert "finished" not in interpreter.configuration

    interpreter.queue("EventC")
    interpreter.execute()
    assert "finished" in interpreter.configuration
    assert "working" not in interpreter.configuration


def test_join_re_arms_completion_flags_on_restart(
    model: syside.Model,
) -> None:
    """Re-entering a parallel state clears stale completion flags.

    ``working`` is paused mid-completion, with region ``a`` already done,
    then resumed. Re-entry must reset both region flags, so completing
    only region ``b`` afterward cannot fire the join off the stale ``a``
    flag: the join waits for a fresh completion of every region.
    """
    sc = build_statechart(model, "SM10::MachineParallelRestart")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "working::a::a1" in interpreter.configuration
    assert "working::b::b1" in interpreter.configuration

    interpreter.queue("EventA")
    interpreter.execute()
    assert "working::a::done" in interpreter.configuration

    interpreter.queue("Pause")
    interpreter.execute()
    assert interpreter.configuration == ["MachineParallelRestart", "paused"]

    interpreter.queue("Resume")
    interpreter.execute()
    assert "working::a::a1" in interpreter.configuration
    assert "working::b::b1" in interpreter.configuration

    # Region a's earlier completion was discarded on re-entry, so
    # completing only region b must not fire the join off a stale flag.
    interpreter.queue("EventB")
    interpreter.execute()
    assert "working::b::done" in interpreter.configuration
    assert "finished" not in interpreter.configuration

    # Freshly completing region a as well now releases the join.
    interpreter.queue("EventA")
    interpreter.execute()
    assert interpreter.configuration == ["MachineParallelRestart", "finished"]


def test_user_guard_and_completion_flag_both_gate(
    model: syside.Model,
) -> None:
    """A completion-gated eventless transition also honors its ``if`` guard.

    ``working`` completes on ``EventA``. Its outgoing eventless transition
    to ``rejected`` has guard ``not go``, true from the start, yet the
    completion gate holds it inside ``working`` until ``EventA`` arrives;
    only then, with the guard still satisfied, does it fire.
    """
    sc = build_statechart(model, "SM10::MachineGuardedJoin")
    interpreter = Interpreter(sc)
    interpreter.execute()
    # `not go` is already true, but completion has not been reached.
    assert "working::w1" in interpreter.configuration
    assert "rejected" not in interpreter.configuration

    interpreter.queue("EventA")
    interpreter.execute()
    assert interpreter.configuration == ["MachineGuardedJoin", "rejected"]


def test_two_guarded_eventless_share_completion_gate(
    model: syside.Model,
) -> None:
    """Both eventless branches from one source carry the completion gate.

    ``working`` sources two guarded eventless transitions, ``if go`` and
    ``if not go``. With ``go`` set, the ``go`` branch's guard is satisfied
    from the start, yet it too waits for ``working`` to complete before
    firing to ``approved``.
    """
    sc = build_statechart(model, "SM10::MachineGuardedJoin")
    interpreter = Interpreter(sc)
    interpreter.context["go"] = True
    interpreter.execute()
    # The `go` branch's guard holds, but completion has not been reached.
    assert "working::w1" in interpreter.configuration
    assert "approved" not in interpreter.configuration

    interpreter.queue("EventA")
    interpreter.execute()
    assert interpreter.configuration == ["MachineGuardedJoin", "approved"]


def test_deep_completion_chain_waits_for_full_descent(
    model: syside.Model,
) -> None:
    """A nested completion chain fires the outer join only at the bottom.

    Three composites nest, each with its own ``done``. The outermost
    eventless transition to ``finished`` may fire only once the innermost
    ``done`` has propagated up through every level, which a single
    ``EventA`` cascades in one run.
    """
    sc = build_statechart(model, "SM10::MachineDeepJoin")
    assert has_transition(sc, "l1", "finished")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "l1::l2::l3::leaf" in interpreter.configuration
    assert "finished" not in interpreter.configuration

    interpreter.queue("EventA")
    interpreter.execute()
    assert interpreter.configuration == ["MachineDeepJoin", "finished"]


def test_join_never_fires_when_one_region_has_no_done(
    model: syside.Model,
) -> None:
    """A region with no ``done`` of its own permanently blocks the join.

    ``working`` has two regions: ``a`` reaches its own scoped ``done``,
    ``b`` never does. Once any region uses the done/join pattern, every
    region is required: completing ``a`` alone must not release the join,
    and ``b`` progressing on its own (with no ``done`` to reach) can never
    release it either. The transition stays permanently unreachable rather
    than silently firing on the subset of regions that happen to have a
    ``done``.
    """
    sc = build_statechart(model, "SM10::MachinePartialJoin")
    interpreter = Interpreter(sc)
    interpreter.execute()

    interpreter.queue("EventA")
    interpreter.execute()
    assert "working::a::done" in interpreter.configuration
    assert "finished" not in interpreter.configuration

    interpreter.queue("EventB")
    interpreter.execute()
    assert "working::b::b2" in interpreter.configuration
    assert "finished" not in interpreter.configuration
