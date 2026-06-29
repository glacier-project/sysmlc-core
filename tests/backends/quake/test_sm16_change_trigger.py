from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.exceptions import NonDeterminismError
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR, quake_preamble

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm16-change-trigger"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


def test_bare_change_trigger_emits_armed_flag_transition(
    model: syside.Model,
) -> None:
    """A bare `accept when` becomes one flag-guarded eventless transition."""
    sc = build_statechart(model, "SM16::MachineWhenBare")
    assert sc.preamble == quake_preamble("hot = False", "_w_idle_t1 = False")
    assert sc.state_for("idle").on_entry == "_w_idle_t1 = True"
    assert len(sc.transitions) == 2
    when = next(t for t in sc.transitions if t.source == "idle")
    assert when.target == "running"
    assert when.event is None
    assert when.guard == "_w_idle_t1 and (hot)"
    assert when.action is None


def test_guarded_change_trigger_emits_real_and_consumer_pair(
    model: syside.Model,
) -> None:
    """`accept when ... if g` adds a negative-priority consumer transition."""
    sc = build_statechart(model, "SM16::MachineWhenGuard")
    pair = [t for t in sc.transitions if t.source == "idle" and t.guard]
    real = next(t for t in pair if t.target == "running")
    consumer = next(t for t in pair if t.target is None)
    assert real.guard == "_w_idle_t1 and (hot) and (enabled)"
    assert real.priority == 0
    assert consumer.priority < real.priority
    assert consumer.internal
    assert consumer.guard == "_w_idle_t1 and (hot)"
    assert consumer.action == "_w_idle_t1 = False"


def test_change_trigger_fires_at_the_rise(model: syside.Model) -> None:
    """The transition fires at the first rise of the condition."""
    sc = build_statechart(model, "SM16::MachineWhenBare")
    interp = Interpreter(sc)
    interp.execute()
    assert "idle" in interp.configuration
    interp.context["hot"] = True
    interp.execute()
    assert interp.final


def test_condition_already_true_at_entry_fires_immediately(
    model: syside.Model,
) -> None:
    """A condition already true at arming fires right after entry.

    The SysML change trigger is not a pure edge: the signal is also sent
    when the expression is already true at its first evaluation.
    """
    sc = build_statechart(model, "SM16::MachineWhenBare")
    interp = Interpreter(sc)
    interp.context["hot"] = True
    interp.execute()
    assert interp.final


def test_guard_true_at_delivery_fires(model: syside.Model) -> None:
    """With the guard true when the condition rises, the transition fires."""
    sc = build_statechart(model, "SM16::MachineWhenGuard")
    interp = Interpreter(sc)
    interp.execute()
    interp.context["hot"] = True
    interp.execute()
    assert interp.final


def test_guard_false_at_delivery_consumes_the_occurrence(
    model: syside.Model,
) -> None:
    """A false guard at delivery consumes the occurrence for good.

    One observation is armed per activation: delivered while the guard is
    false, it is disarmed by the consumer, and nothing may fire for the
    rest of that activation, not even when the guard later becomes true or
    the condition falls and rises again.
    """
    sc = build_statechart(model, "SM16::MachineWhenGuard")
    interp = Interpreter(sc)
    interp.execute()
    interp.context["enabled"] = False
    interp.context["hot"] = True
    interp.execute()
    assert "idle" in interp.configuration
    assert interp.context["_w_idle_t1"] is False
    interp.context["enabled"] = True
    interp.execute()
    assert "idle" in interp.configuration
    interp.context["hot"] = False
    interp.execute()
    interp.context["hot"] = True
    interp.execute()
    assert "idle" in interp.configuration


def test_reentry_after_consumption_arms_a_fresh_observation(
    model: syside.Model,
) -> None:
    """Re-entering the source re-arms; a still-true condition fires again."""
    sc = build_statechart(model, "SM16::MachineWhenGuard")
    interp = Interpreter(sc)
    interp.execute()
    # Consume the first activation's observation under a false guard.
    interp.context["enabled"] = False
    interp.context["hot"] = True
    interp.execute()
    assert "idle" in interp.configuration
    # Leave and re-enter `idle`: a fresh observation is armed, and the
    # still-true condition (with the guard now true) fires immediately.
    interp.context["enabled"] = True
    interp.queue("Kick")
    interp.execute()
    assert "away" in interp.configuration
    interp.queue("Kick")
    interp.execute()
    assert interp.final


def test_reentry_with_condition_held_true_fires_each_activation(
    model: syside.Model,
) -> None:
    """Each fresh activation of the source re-fires on a held-true condition."""
    sc = build_statechart(model, "SM16::MachineWhenReentry")
    interp = Interpreter(sc)
    interp.execute()
    interp.context["hot"] = True
    interp.execute()
    assert "running" in interp.configuration
    interp.queue("Reset")
    interp.execute()
    assert "running" in interp.configuration


def test_two_change_triggers_fire_independently(
    model: syside.Model,
) -> None:
    """Each of two triggers on one source fires on its own rise."""
    sc = build_statechart(model, "SM16::MachineWhenTwo")
    interp = Interpreter(sc)
    interp.execute()
    interp.context["hot"] = True
    interp.execute()
    assert "warmed" in interp.configuration

    sc = build_statechart(model, "SM16::MachineWhenTwo")
    interp = Interpreter(sc)
    interp.execute()
    interp.context["cold"] = True
    interp.execute()
    assert "chilled" in interp.configuration


def test_simultaneous_change_triggers_are_nondeterministic(
    model: syside.Model,
) -> None:
    """Two triggers rising together is an ambiguous model: it fails loud.

    SysML mandates no priority between transitions, so two enabled at the
    same instant from one source is genuinely ambiguous. Both real transitions
    keep the default priority, so sismic raises ``NonDeterminismError``
    at the colliding step.
    """
    sc = build_statechart(model, "SM16::MachineWhenTwo")
    interp = Interpreter(sc)
    interp.execute()
    interp.context["hot"] = True
    interp.context["cold"] = True
    with pytest.raises(NonDeterminismError):
        interp.execute()


def test_composed_condition_observes_the_whole_expression(
    model: syside.Model,
) -> None:
    """`accept when a and b` watches the conjunction, not one conjunct.

    Unlike `accept when a if b` (one shot at the rise of `a`), a rise of
    either conjunct while the other holds is a false-to-true crossing of
    the monitored expression, so it fires.
    """
    sc = build_statechart(model, "SM16::MachineWhenComposed")
    interp = Interpreter(sc)
    interp.execute()
    interp.context["hot"] = True
    interp.execute()
    assert "idle" in interp.configuration
    interp.context["enabled"] = True
    interp.execute()
    assert interp.final
