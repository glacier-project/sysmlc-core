from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside
    from sismic.model import Statechart, Transition

EXAMPLE = SM_EXAMPLES_BY_DIR["sm06-transition-effect"]

EFFECT_SOURCE = "idle"


@dataclass(frozen=True)
class EffectCase:
    """One sm06 transition-effect variation.

    Attributes:
        state_def_qn: Qualified name of the SM06 state def under test.
        expected_action: Python statement string the builder must place
            in the ``Transition.action`` slot of the transition leaving
            ``idle``.
        expected_context: Attribute name -> value that
            ``Interpreter.execute()`` must leave in the interpreter
            context once the seeded preamble and the fired effect have
            run.
    """

    state_def_qn: str
    expected_action: str
    expected_context: dict[str, int]


CASES: list[EffectCase] = [
    # Single increment effect on the first of two transitions; the second
    # transition (armed -> running) carries no effect.
    EffectCase(
        "SM06::MachineEffect",
        expected_action="counter = counter + 1",
        expected_context={"counter": 1},
    ),
    # Two assigns in one effect body, joined in declaration order.
    EffectCase(
        "SM06::MachineEffectMulti",
        expected_action="a = 1\nb = a + 2",
        expected_context={"a": 1, "b": 3},
    ),
]


def _transition_from(statechart: Statechart, source: str) -> Transition:
    """Return the single transition leaving ``source`` in ``statechart``."""
    matches = [t for t in statechart.transitions if t.source == source]
    assert len(matches) == 1, (
        f"expected exactly one transition from {source!r}, found {len(matches)}"
    )
    return matches[0]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


@pytest.fixture(
    scope="module",
    params=CASES,
    ids=lambda c: c.state_def_qn.split("::", 1)[1],
)
def case(request: pytest.FixtureRequest) -> EffectCase:
    """Yield every transition-effect shape sm06 exercises."""
    param: EffectCase = request.param
    return param


def test_effect_transition_action_is_emitted(
    model: syside.Model,
    case: EffectCase,
) -> None:
    """The effect transition's ``action`` is the emitted assignment.

    Per SysML v2 §7.18.3, a transition's effect action "is performed if
    the transition usage is triggered".
    """
    sc = build_statechart(model, case.state_def_qn)
    assert _transition_from(sc, EFFECT_SOURCE).action == case.expected_action


def test_effect_targets_only_its_transition(
    model: syside.Model,
    case: EffectCase,
) -> None:
    """Only the effect transition carries an ``action``; siblings stay empty."""
    sc = build_statechart(model, case.state_def_qn)
    sources_with_action = {
        t.source for t in sc.transitions if t.action is not None
    }
    assert sources_with_action == {EFFECT_SOURCE}


def test_effect_mutates_context(
    model: syside.Model,
    case: EffectCase,
) -> None:
    """Firing the effect mutates the context to the expected value."""
    sc = build_statechart(model, case.state_def_qn)
    interpreter = Interpreter(sc)
    interpreter.execute()
    for name, value in case.expected_context.items():
        assert interpreter.context[name] == value
