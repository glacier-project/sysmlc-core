from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sismic.exceptions import CodeEvaluationError
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import (
    SM_EXAMPLES_BY_DIR,
    quake_preamble,
    transition_from,
)

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm13-time-trigger"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "no-default-duration"
)


@pytest.fixture(scope="module")
def no_default_model() -> syside.Model:
    return load_model(FIXTURES_DIR)


@pytest.mark.parametrize(
    ("state_def_qn", "expected_delay"),
    [
        ("SM13::MachineAfterSeconds", "5.0"),
        ("SM13::MachineAfterMinutes", "120.0"),
        ("SM13::MachineAfterAttribute", "pickDuration"),
        ("SM13::MachineAfterChain", "holder.delay"),
    ],
    ids=[
        "literal-seconds",
        "minutes-normalized",
        "attribute-default",
        "chained-reference",
    ],
)
def test_relative_time_trigger_emits_delayed_event(
    model: syside.Model,
    state_def_qn: str,
    expected_delay: str,
) -> None:
    """A time trigger becomes a delayed `_tick_*` event armed on entry."""
    sc = build_statechart(model, state_def_qn)
    assert len(sc.transitions) == 2
    timed = transition_from(sc, "idle")
    assert timed.target == "running"
    assert timed.event == "_tick_idle_t1"
    assert timed.guard == "event.n == _n_idle"
    assert sc.state_for("idle").on_entry == (
        "_n_idle = _n_idle + 1\n"
        f"send('_tick_idle_t1', n=_n_idle, delay={expected_delay}, "
        "_sysmlc_tick=('idle', '_n_idle'))"
    )


def test_activation_counter_is_initialized_in_preamble(
    model: syside.Model,
) -> None:
    """The timed source state's activation counter starts at zero."""
    sc = build_statechart(model, "SM13::MachineAfterSeconds")
    assert sc.preamble == quake_preamble("_n_idle = 0")


def test_attribute_duration_default_seeds_preamble(
    model: syside.Model,
) -> None:
    """A ``DurationValue`` attribute's default is seeded as its SI scalar."""
    sc = build_statechart(model, "SM13::MachineAfterAttribute")
    assert sc.preamble == quake_preamble("pickDuration = 120.0", "_n_idle = 0")


def test_chained_reference_duration_is_read_at_entry(
    model: syside.Model,
) -> None:
    """A chained ``holder.delay`` duration is read when the state is entered.

    The arming instant is state entry: the duration expression is evaluated
    by the on-entry ``send``, so overriding the seeded default before the
    machine starts moves the deadline.
    """
    sc = build_statechart(model, "SM13::MachineAfterChain")
    interp = Interpreter(sc)
    interp.context["holder"].delay = 10.0
    interp.execute()
    interp.clock.time = 3.0
    interp.execute()
    assert not interp.final
    interp.clock.time = 10.0
    interp.execute()
    assert interp.final


def test_time_trigger_does_not_fire_before_duration_elapses(
    model: syside.Model,
) -> None:
    """The transition fires once the clock reaches entry+t, not before."""
    sc = build_statechart(model, "SM13::MachineAfterSeconds")
    interp = Interpreter(sc)
    interp.execute()
    assert not interp.final
    interp.clock.time = 4.9
    interp.execute()
    assert not interp.final
    interp.clock.time = 5.0
    interp.execute()
    assert interp.final


def test_after_with_guard_conjoins_condition_and_fires_when_true(
    model: syside.Model,
) -> None:
    """``accept after ... if g`` guards the tick delivery with ``g``.

    The emitted guard conjoins the activation-counter check with the
    condition; with the condition true at the deadline, the transition
    fires.
    """
    sc = build_statechart(model, "SM13::MachineAfterGuard")
    timed = transition_from(sc, "idle")
    assert timed.event == "_tick_idle_t1"
    assert timed.guard == "event.n == _n_idle and (ready)"
    assert sc.preamble == quake_preamble("ready = True", "_n_idle = 0")
    interp = Interpreter(sc)
    interp.execute()
    interp.clock.time = 5.0
    interp.execute()
    assert interp.final


def test_after_with_guard_false_at_deadline_consumes_the_occurrence(
    model: syside.Model,
) -> None:
    """A false condition at the deadline consumes the occurrence for good.

    The deadline is a one-shot signal occurrence: delivered while the
    condition is false, it is consumed, and the transition must not fire
    later when the condition becomes true.
    """
    sc = build_statechart(model, "SM13::MachineAfterGuard")
    interp = Interpreter(sc)
    interp.execute()
    interp.context["ready"] = False
    interp.clock.time = 5.0
    interp.execute()
    assert not interp.final
    interp.context["ready"] = True
    interp.clock.time = 50.0
    interp.execute()
    assert not interp.final


def test_absolute_time_trigger_arms_delta_and_fires_at_instant(
    model: syside.Model,
) -> None:
    """An absolute time trigger arms a delta tick and fires on time.

    Entry computes the remaining delta and arms the tick only for a
    non-past instant; the transition fires when the clock reaches the
    absolute instant.
    """
    sc = build_statechart(model, "SM13::MachineAt")
    assert sc.preamble == quake_preamble("deadlineTime = 8.0", "_n_idle = 0")
    assert len(sc.transitions) == 2
    timed = transition_from(sc, "idle")
    assert timed.target == "running"
    assert timed.event == "_tick_idle_t1"
    assert timed.guard == "event.n == _n_idle"
    assert sc.state_for("idle").on_entry == (
        "_n_idle = _n_idle + 1\n"
        "_d_idle_t1 = (deadlineTime) - time\n"
        "if _d_idle_t1 >= 0:\n"
        "    send('_tick_idle_t1', n=_n_idle, delay=_d_idle_t1, "
        "_sysmlc_tick=('idle', '_n_idle'))"
    )
    interp = Interpreter(sc)
    interp.execute()
    interp.clock.time = 7.9
    interp.execute()
    assert not interp.final
    interp.clock.time = 8.0
    interp.execute()
    assert interp.final


def test_absolute_time_reentry_after_instant_never_fires(
    model: syside.Model,
) -> None:
    """Re-entry after the instant has passed does not arm a new tick."""
    sc = build_statechart(model, "SM13::MachineAtReentry")
    interp = Interpreter(sc)
    interp.execute()
    interp.clock.time = 2.0
    interp.queue("Leave")
    interp.execute()
    assert "away" in interp.configuration
    interp.clock.time = 6.0
    interp.queue("Back")
    interp.execute()
    assert "idle" in interp.configuration
    interp.clock.time = 50.0
    interp.execute()
    assert "idle" in interp.configuration
    assert not interp.final


def test_timed_self_loop_rearms_a_fresh_deadline_each_entry(
    model: syside.Model,
) -> None:
    """A timed self-loop fires once per period, re-arming on re-entry."""
    sc = build_statechart(model, "SM13::MachineAfterSelfLoop")
    interp = Interpreter(sc)
    interp.execute()
    assert interp.context["entries"] == 1
    interp.clock.time = 5.0
    interp.execute()
    assert interp.context["entries"] == 2
    interp.clock.time = 7.0
    interp.execute()
    assert interp.context["entries"] == 2
    interp.clock.time = 10.0
    interp.execute()
    assert interp.context["entries"] == 3


def test_reentry_invalidates_the_stale_deadline(model: syside.Model) -> None:
    """Only the deadline armed by the current activation can fire.

    Sismic never cancels a scheduled delayed event, so leaving `idle` before
    the deadline leaves a stale tick in the queue. The activation-counter
    guard must reject it: after a re-entry, the transition fires at the
    fresh deadline, never at the stale one.
    """
    sc = build_statechart(model, "SM13::MachineAfterReentry")
    interp = Interpreter(sc)
    interp.execute()
    # First activation of `idle` arms a deadline at t=10.
    interp.clock.time = 2.0
    interp.queue("Leave")
    interp.execute()
    assert "away" in interp.configuration
    # Re-enter at t=3: the fresh deadline is t=13.
    interp.clock.time = 3.0
    interp.queue("Back")
    interp.execute()
    assert "idle" in interp.configuration
    # t=10: the stale tick from the first activation is delivered and must
    # be consumed without firing.
    interp.clock.time = 10.0
    interp.execute()
    assert "idle" in interp.configuration
    # t=13: the fresh deadline fires.
    interp.clock.time = 13.0
    interp.execute()
    assert "running" in interp.configuration


def test_no_default_duration_builds_but_errors_in_simulation(
    no_default_model: syside.Model,
) -> None:
    """A no-default duration builds cleanly and fails only when run.

    The attribute is left uninitialized (machinery only in the
    preamble): the model is valid but incomplete, so the failure
    surfaces at simulation, by design.
    """
    sc = build_statechart(
        no_default_model, "SM13NoDefault::MachineAfterNoDefault"
    )
    assert sc.preamble == quake_preamble("_n_idle = 0")
    assert len(sc.transitions) == 1
    timed = sc.transitions[0]
    assert timed.event == "_tick_idle_t1"
    assert timed.guard == "event.n == _n_idle"
    interp = Interpreter(sc)
    with pytest.raises(CodeEvaluationError):
        interp.execute()
