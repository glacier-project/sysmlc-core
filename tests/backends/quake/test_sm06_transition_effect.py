from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR, transition_from

if TYPE_CHECKING:
    import syside

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


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


@pytest.mark.parametrize(
    "case", CASES, ids=lambda case: case.state_def_qn.split("::", 1)[1]
)
def test_effect_emitted_on_its_transition_only_and_mutates_context(
    model: syside.Model,
    case: EffectCase,
) -> None:
    """The effect is emitted on its transition alone and runs on fire.

    Per SysML v2 §7.18.3, a transition's effect action "is performed
    if the transition usage is triggered". Sibling transitions carry
    no action.
    """
    sc = build_statechart(model, case.state_def_qn)
    assert transition_from(sc, EFFECT_SOURCE).action == case.expected_action
    sources_with_action = {
        t.source for t in sc.transitions if t.action is not None
    }
    assert sources_with_action == {EFFECT_SOURCE}
    interpreter = Interpreter(sc)
    interpreter.execute()
    for name, value in case.expected_context.items():
        assert interpreter.context[name] == value
