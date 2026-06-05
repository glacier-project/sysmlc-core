from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sismic.exceptions import CodeEvaluationError
from sismic.interpreter import Interpreter

from sysml2frost.loader import load_syside_model
from sysml2frost.sismic import build_statechart
from tests.sismic.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm13-time-trigger"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(EXAMPLE.model_dir)


FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "sm13-time-trigger-input"
)


@pytest.fixture(scope="module")
def input_model() -> syside.Model:
    return load_syside_model(FIXTURES_DIR)


@pytest.mark.parametrize(
    ("state_def_qn", "expected_guard"),
    [
        ("SM13::MachineAfterSeconds", "after(5.0)"),
        ("SM13::MachineAfterMinutes", "after(120.0)"),
        ("SM13::MachineAfterAttribute", "after(pickDuration)"),
        ("SM13::MachineAfterChain", "after(holder.delay)"),
        ("SM13::MachineAfterGuard", "after(5.0) and (ready)"),
    ],
    ids=[
        "literal-seconds",
        "minutes-normalized",
        "attribute-default",
        "chained-reference",
        "after-and-if",
    ],
)
def test_relative_time_trigger_emits_after_guard(
    model: syside.Model,
    state_def_qn: str,
    expected_guard: str,
) -> None:
    """A relative time trigger becomes an ``after(<seconds>)`` guard."""
    sc = build_statechart(model, state_def_qn)
    assert len(sc.transitions) == 1
    only = sc.transitions[0]
    assert only.source == "idle"
    assert only.target == "running"
    assert only.event is None
    assert only.guard == expected_guard


def test_attribute_duration_default_seeds_preamble(
    model: syside.Model,
) -> None:
    """A ``DurationValue`` attribute's default is seeded as its SI scalar."""
    sc = build_statechart(model, "SM13::MachineAfterAttribute")
    assert sc.preamble == "pickDuration = 120.0"


def test_guard_attribute_default_seeds_preamble(
    model: syside.Model,
) -> None:
    """MachineAfterGuard's ``ready := true`` is seeded into the preamble."""
    sc = build_statechart(model, "SM13::MachineAfterGuard")
    assert sc.preamble == "ready = True"


def test_chained_reference_duration_is_live(model: syside.Model) -> None:
    """A chained ``holder.delay`` duration reads the field at eval time."""
    sc = build_statechart(model, "SM13::MachineAfterChain")
    interp = Interpreter(sc)
    interp.execute()
    # Override the seeded default (3.0): a baked after(3.0) would fire at
    # t=3.0; a live after(holder.delay) fires at the overridden 10.0.
    interp.context["holder"].delay = 10.0
    interp.clock.time = 3.0
    interp.execute()
    assert "running" not in interp.configuration
    interp.clock.time = 10.0
    interp.execute()
    assert "running" in interp.configuration


def test_attribute_reference_duration_fires_at_seeded_value(
    model: syside.Model,
) -> None:
    """A live attribute-reference duration fires at its seeded SI value."""
    sc = build_statechart(model, "SM13::MachineAfterAttribute")
    interp = Interpreter(sc)
    interp.execute()
    interp.clock.time = 119.0
    interp.execute()
    assert "running" not in interp.configuration
    interp.clock.time = 120.0
    interp.execute()
    assert "running" in interp.configuration


def test_time_trigger_does_not_fire_before_duration_elapses(
    model: syside.Model,
) -> None:
    """The transition fires once the clock reaches entry+t, not before."""
    sc = build_statechart(model, "SM13::MachineAfterSeconds")
    interp = Interpreter(sc)
    interp.execute()
    assert "running" not in interp.configuration
    interp.clock.time = 4.9
    interp.execute()
    assert "running" not in interp.configuration
    interp.clock.time = 5.0
    interp.execute()
    assert "running" in interp.configuration


def test_composed_guard_requires_both_timer_and_condition(
    model: syside.Model,
) -> None:
    """An ``after`` trigger ANDed with an ``if`` guard needs both to hold."""
    sc = build_statechart(model, "SM13::MachineAfterGuard")
    interp = Interpreter(sc)
    interp.execute()
    interp.context["ready"] = False
    interp.clock.time = 6.0
    interp.execute()
    assert "running" not in interp.configuration
    interp.context["ready"] = True
    interp.execute()
    assert "running" in interp.configuration


def test_input_duration_is_left_unseeded(
    input_model: syside.Model,
) -> None:
    """An ``in`` duration with no default: live guard, empty preamble."""
    sc = build_statechart(input_model, "SM13Input::MachineAfterInput")
    assert sc.preamble == ""
    assert len(sc.transitions) == 1
    assert sc.transitions[0].guard == "after(pickDuration)"


def test_input_duration_errors_when_unsupplied(
    input_model: syside.Model,
) -> None:
    """An unbound ``in`` duration errors when simulated, by design."""
    sc = build_statechart(input_model, "SM13Input::MachineAfterInput")
    interp = Interpreter(sc)
    with pytest.raises(CodeEvaluationError):
        interp.execute()
