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

EXAMPLE = SM_EXAMPLES_BY_DIR["sm03-guard"]


@dataclass(frozen=True)
class GuardCase:
    """One sm03 guard-expression variation.

    Attributes:
        state_def_qn: Qualified name of the SM03 state def under test.
        expected_guard: Python source string the builder must produce
            in ``Transition.guard``.
        expected_final_state: Substate name that ``Interpreter.execute()``
            must leave in the configuration. ``"running"`` when the
            initial attribute values make the guard evaluate truthy
            and the transition fires; ``"idle"`` when they make it
            evaluate falsy and the transition stays disabled.
    """

    state_def_qn: str
    expected_guard: str
    expected_final_state: str


CASES: list[GuardCase] = [
    # Literals
    GuardCase("SM03::MachineLiteralTrue", "True", "running"),
    GuardCase("SM03::MachineLiteralFalse", "False", "idle"),
    # Bare feature reference
    GuardCase("SM03::MachineRef", "enabled", "running"),
    # Unary operators
    GuardCase("SM03::MachineNot", "not enabled", "running"),
    GuardCase("SM03::MachineUnaryMinus", "-x < 0", "running"),
    # Logical binary operators
    GuardCase("SM03::MachineAnd", "a and b", "running"),
    GuardCase("SM03::MachineOr", "a or b", "running"),
    # Comparison operators
    GuardCase("SM03::MachineEq", "x == 1", "running"),
    GuardCase("SM03::MachineNeq", "x != 0", "running"),
    GuardCase("SM03::MachineLt", "x < 2", "running"),
    GuardCase("SM03::MachineLe", "x <= 1", "running"),
    GuardCase("SM03::MachineGt", "x > 0", "running"),
    GuardCase("SM03::MachineGe", "x >= 1", "running"),
    # Arithmetic operators inside a comparison
    GuardCase("SM03::MachineArithPlus", "x + 1 > 1", "running"),
    GuardCase("SM03::MachineArithMinus", "x - 1 > 0", "running"),
    GuardCase("SM03::MachineArithMul", "x * 2 > 1", "running"),
    GuardCase("SM03::MachineArithDiv", "x / 2 > 1", "running"),
    # Rational literal
    GuardCase("SM03::MachineRealLiteral", "x > 0.5", "running"),
    # Precedence / parenthesization
    GuardCase("SM03::MachineLogicalChain", "a and b or c", "running"),
    GuardCase("SM03::MachineLowerPrecLhs", "(a or b) and c", "running"),
    GuardCase("SM03::MachineLeftAssocRhs", "x - (1 - 2) > 0", "running"),
]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


@pytest.fixture(
    scope="module",
    params=CASES,
    ids=lambda c: c.state_def_qn.split("::", 1)[1],
)
def case(request: pytest.FixtureRequest) -> GuardCase:
    """Yield every ``if expr`` guard shape sm03 exercises."""
    param: GuardCase = request.param
    return param


def test_only_idle_to_running_transition_is_declared(
    model: syside.Model,
    case: GuardCase,
) -> None:
    """One ``Transition`` from ``idle`` to ``running``."""
    sc = build_statechart(model, case.state_def_qn)
    assert len(sc.transitions) == 1
    only = sc.transitions[0]
    assert only.source == "idle"
    assert only.target == "running"


def test_transition_guard_is_emitted_python_source(
    model: syside.Model,
    case: GuardCase,
) -> None:
    """The transition's guard is the emitted Python source."""
    sc = build_statechart(model, case.state_def_qn)
    assert sc.transitions[0].guard == case.expected_guard


def test_transition_event_is_none(
    model: syside.Model,
    case: GuardCase,
) -> None:
    """A guarded-but-not-accept-ed transition has ``event is None``.

    Per KerML §9.2.11.1, the ``trigger [0..1]`` slot on a
    StateTransitionPerformance is populated only when an accepter is
    present. sm03's transitions carry an ``if`` clause but no
    ``accept``, so ``Transition.event`` must be ``None``.
    """
    sc = build_statechart(model, case.state_def_qn)
    assert sc.transitions[0].event is None


def test_guard_evaluation_drives_target_configuration(
    model: syside.Model,
    case: GuardCase,
) -> None:
    """The transition fires iff the guard evaluates truthy.

    Per SysML v2 §7.18.3, triggering rule 2: a transition usage with
    a guard expression "can only be triggered if the guard expression
    evaluates to true". End-to-end check that the preamble bindings,
    the Python emitted by ``render_expression``, and sismic's evaluator
    round-trip to the expected final configuration per case.
    """
    sc = build_statechart(model, case.state_def_qn)
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert case.expected_final_state in interpreter.configuration
