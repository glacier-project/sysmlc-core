from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysml2frost.loader import load_syside_model
from sysml2frost.generator.sismic import build_statechart
from tests.generator.sismic.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm02-event-trigger"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(EXAMPLE.model_dir)


@pytest.fixture(
    scope="module",
    params=[
        "SM02::Machine",
        "SM02::MachineNamed",
        "SM02::MachinePortless",
    ],
    ids=["canonical", "named-payload", "no-via-port"],
)
def state_def_qn(request: pytest.FixtureRequest) -> str:
    """Yield every signal-trigger ``accept`` form sm02 exercises."""
    param: str = request.param
    return param


def test_only_idle_to_running_transition_is_declared(
    model: syside.Model,
    state_def_qn: str,
) -> None:
    """One ``Transition`` from ``idle`` to ``running``."""
    sc = build_statechart(model, state_def_qn)
    assert len(sc.transitions) == 1
    only = sc.transitions[0]
    assert only.source == "idle"
    assert only.target == "running"


def test_transition_event_is_payload_type_simple_name(
    model: syside.Model,
    state_def_qn: str,
) -> None:
    """The transition's event is the payload type's simple name ``"Tick"``.

    Per SysML v2 OMG spec, §7.17.8 "Accept Action Usages":

        The payload parameter declaration for an accept action usage
        identifies the type of values accepted by the accept action.
        It is declared as a reference usage (see 7.6), but without
        the ref keyword or any body. If the payload parameter
        declaration has the form of a single qualified name (and,
        optionally, a multiplicity), then the qualified name is
        interpreted as the definition (type) of the payload parameter
        (not its name).
    """
    sc = build_statechart(model, state_def_qn)
    assert sc.transitions[0].event == "Tick"


def test_transition_does_not_fire_without_queued_event(
    model: syside.Model,
    state_def_qn: str,
) -> None:
    """A triggered transition does not fire spontaneously.

    Per SysML v2 OMG spec, §7.18.3 "Transition Usages", triggering
    rule 3:

        If a transition has an accepter, and it meets the above
        conditions, then it is triggered if the accepter can accept
        in incoming transfer via its receiver parameter, in which
        case the accepter is performed as described in 7.17.8.

    Per Execution WG:

        The main effect of "completion" is that any un-triggered
        state transitions leaving a state may occur if and only if
        the source state has "completed" and any guards are true.

    The "un-triggered" qualifier excludes accepter-bearing
    transitions: with an accepter present, the transition is
    *triggered*, not eventless, and must NOT fire on source
    completion alone.
    """
    sc = build_statechart(model, state_def_qn)
    interp = Interpreter(sc)
    interp.execute()
    config = list(interp.configuration)
    assert "idle" in config
    assert "running" not in config


def test_queueing_tick_fires_transition_to_running(
    model: syside.Model,
    state_def_qn: str,
) -> None:
    """Queueing the event named ``"Tick"`` fires the transition."""
    sc = build_statechart(model, state_def_qn)
    interp = Interpreter(sc)
    interp.execute()
    interp.queue("Tick")
    interp.execute()
    assert "running" in interp.configuration
