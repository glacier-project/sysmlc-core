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

EXAMPLE = SM_EXAMPLES_BY_DIR["sm04-assignment"]

# Every sm04 state def carries its action(s) on substate ``idle`` and
# leaves substate ``running`` action free.
ACTION_STATE = "idle"
ACTION_FREE_STATE = "running"


@dataclass(frozen=True)
class AssignCase:
    """One sm04 assignment-action variation.

    Attributes:
        state_def_qn: Qualified name of the SM04 state def under test.
        expected_on_entry: Python statement string the builder must place
            in the ``idle`` state's ``on_entry`` slot, or ``None`` when
            ``idle`` declares no entry action.
        expected_on_exit: Python statement string the builder must place
            in the ``idle`` state's ``on_exit`` slot, or ``None`` when
            ``idle`` declares no exit action.
        expected_context: Attribute name -> value that
            ``Interpreter.execute()`` must leave in the interpreter
            context once the seeded preamble and the emitted
            entry/exit statements have run.
    """

    state_def_qn: str
    expected_on_entry: str | None
    expected_on_exit: str | None
    expected_context: dict[str, int]


CASES: list[AssignCase] = [
    # Single self-referential increment in an entry action.
    AssignCase(
        "SM04::MachineEntryIncrement",
        expected_on_entry="counter = counter + 1",
        expected_on_exit=None,
        expected_context={"counter": 1},
    ),
    # Single decrement in an exit action.
    AssignCase(
        "SM04::MachineExitDecrement",
        expected_on_entry=None,
        expected_on_exit="counter = counter - 1",
        expected_context={"counter": 0},
    ),
    # Two assigns in one entry action, joined in declaration order.
    AssignCase(
        "SM04::MachineMultiEntry",
        expected_on_entry="a = 1\nb = a + 2",
        expected_on_exit=None,
        expected_context={"a": 1, "b": 3},
    ),
    # Entry and exit assigns on the same substate, distinct attributes.
    AssignCase(
        "SM04::MachineEntryAndExit",
        expected_on_entry="entered = entered + 1",
        expected_on_exit="exited = exited + 1",
        expected_context={"entered": 1, "exited": 1},
    ),
    # Shorthand entry assign (`entry assign x := e;`, no `action { }`).
    AssignCase(
        "SM04::MachineEntryShorthand",
        expected_on_entry="counter = counter + 1",
        expected_on_exit=None,
        expected_context={"counter": 1},
    ),
    # Shorthand exit assign (`exit assign x := e;`).
    AssignCase(
        "SM04::MachineExitShorthand",
        expected_on_entry=None,
        expected_on_exit="counter = counter - 1",
        expected_context={"counter": 0},
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
def case(request: pytest.FixtureRequest) -> AssignCase:
    """Yield every ``assign`` action shape sm04 exercises."""
    param: AssignCase = request.param
    return param


def test_substate_on_entry_is_emitted_assignment(
    model: syside.Model,
    case: AssignCase,
) -> None:
    """The substate's ``on_entry`` is the emitted assignment statement.

    Per SysML v2 §7.18.1, an entry action "starts when the state is
    activated"; §7.17.9 makes ``assign a := expr`` mutate ``a``.
    """
    sc = build_statechart(model, case.state_def_qn)
    assert sc.state_for(ACTION_STATE).on_entry == case.expected_on_entry
    assert sc.state_for(ACTION_FREE_STATE).on_entry is None


def test_substate_on_exit_is_emitted_assignment(
    model: syside.Model,
    case: AssignCase,
) -> None:
    """The substate's ``on_exit`` is the emitted assignment statement.

    Per SysML v2 §7.18.1, an exit action "starts when the state is
    exited".
    """
    sc = build_statechart(model, case.state_def_qn)
    assert sc.state_for(ACTION_STATE).on_exit == case.expected_on_exit
    assert sc.state_for(ACTION_FREE_STATE).on_exit is None


def test_assignment_mutates_context(
    model: syside.Model,
    case: AssignCase,
) -> None:
    """Executing the statechart mutates the context to the expected value.

    Per SysML v2 §7.17.9, an assignment action sets the attribute to the
    value of its right-hand-side expression.
    """
    sc = build_statechart(model, case.state_def_qn)
    interpreter = Interpreter(sc)
    interpreter.execute()
    for name, value in case.expected_context.items():
        assert interpreter.context[name] == value
