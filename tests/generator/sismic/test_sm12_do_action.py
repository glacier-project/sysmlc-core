from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.generator.sismic import build_statechart
from sysmlc.loader import load_syside_model
from tests.generator.sismic.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm12-do-action"]


@dataclass(frozen=True)
class DoCase:
    """One sm12 do-action variation.

    Attributes:
        state_def_qn: Qualified name of the SM12 state def under test.
        carrier: The sismic state whose ``on_entry`` carries the emitted do
            action.
        expected_on_entry: The Python statement string the builder must
            place in ``carrier``'s ``on_entry`` slot, or ``None`` when the
            do action is empty.
        expected_context: Attribute name -> value.
    """

    state_def_qn: str
    carrier: str
    expected_on_entry: str | None
    expected_context: dict[str, int]


CASES: list[DoCase] = [
    DoCase(
        "SM12::MachineDoAssign",
        carrier="working",
        expected_on_entry="progress = progress + 1",
        expected_context={"progress": 1},
    ),
    DoCase(
        "SM12::MachineDoMulti",
        carrier="working",
        expected_on_entry="a = 1\nb = a + 2",
        expected_context={"a": 1, "b": 3},
    ),
    DoCase(
        "SM12::MachineDoShorthand",
        carrier="working",
        expected_on_entry="progress = progress + 1",
        expected_context={"progress": 1},
    ),
    DoCase(
        "SM12::MachineDoSend",
        carrier="working",
        expected_on_entry='send("Ping")',
        expected_context={},
    ),
    DoCase(
        "SM12::MachineDoSendShorthand",
        carrier="working",
        expected_on_entry='send("Ping")',
        expected_context={},
    ),
    DoCase(
        "SM12::MachineEntryThenDo",
        carrier="working",
        expected_on_entry="log = 1\nlog = log + 10",
        expected_context={"log": 11},
    ),
    DoCase(
        "SM12::MachineCompositeDo",
        carrier="working",
        expected_on_entry="progress = progress + 1",
        expected_context={"progress": 1},
    ),
    DoCase(
        "SM12::MachineRootDo",
        carrier="MachineRootDo",
        expected_on_entry="progress = progress + 1",
        expected_context={"progress": 1},
    ),
    DoCase(
        "SM12::MachineParallelDo",
        carrier="regionA",
        expected_on_entry="counter = counter + 1",
        expected_context={"counter": 1},
    ),
    DoCase(
        "SM12::MachineEmptyDo",
        carrier="working",
        expected_on_entry=None,
        expected_context={},
    ),
    DoCase(
        "SM12::MachineRootEntryThenDo",
        carrier="MachineRootEntryThenDo",
        expected_on_entry="x = 1\nx = x + 10",
        expected_context={"x": 11},
    ),
    DoCase(
        "SM12::MachineRootEmptyDo",
        carrier="MachineRootEmptyDo",
        expected_on_entry=None,
        expected_context={},
    ),
    DoCase(
        "SM12::MachineNamedEmptyDo",
        carrier="working",
        expected_on_entry=None,
        expected_context={},
    ),
]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(EXAMPLE.model_dir)


@pytest.fixture(
    scope="module",
    params=CASES,
    ids=lambda c: c.state_def_qn.split("::", 1)[1],
)
def case(request: pytest.FixtureRequest) -> DoCase:
    """Yield every do-action shape sm12 exercises."""
    param: DoCase = request.param
    return param


def test_do_action_emitted_into_on_entry(
    model: syside.Model,
    case: DoCase,
) -> None:
    """A state's ``do`` action body is emitted into the state's ``on_entry``."""
    sc = build_statechart(model, case.state_def_qn)
    assert sc.state_for(case.carrier).on_entry == case.expected_on_entry
    for state_name in sc.states:
        if state_name != case.carrier:
            assert sc.state_for(state_name).on_entry is None


def test_do_action_runs_once_on_entry(
    model: syside.Model,
    case: DoCase,
) -> None:
    """Executing the statechart runs the do body and mutates context."""
    sc = build_statechart(model, case.state_def_qn)
    interpreter = Interpreter(sc)
    interpreter.execute()
    for name, value in case.expected_context.items():
        assert interpreter.context[name] == value


def test_do_action_completion_enables_eventless_transition(
    model: syside.Model,
) -> None:
    """A do that sets state enables a completion (eventless) transition.

    ``MachineDoEnablesCompletion`` has ``do action { assign ready := true }``
    and a guarded eventless transition ``first working if ready then
    finished``. The run-once do sets ``ready`` at entry, so the completion
    transition fires in the same stabilization and the machine reaches
    ``finished`` — the observable proof the do body actually ran.
    """
    sc = build_statechart(model, "SM12::MachineDoEnablesCompletion")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "finished" in interpreter.configuration
    assert interpreter.context["ready"] is True


def test_do_send_raises_event(model: syside.Model) -> None:
    """A ``do send`` body actually raises its event at state entry."""
    sc = build_statechart(model, "SM12::MachineDoSend")
    interpreter = Interpreter(sc)
    sent = [
        event.name
        for macrostep in interpreter.execute()
        for event in macrostep.sent_events
    ]
    assert "Ping" in sent
