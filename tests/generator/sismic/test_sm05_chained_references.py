from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.loader import load_syside_model
from tests.generator.sismic.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm05-chained-references"]

# Every sm05 state def carries its action(s) on substate ``idle`` and
# leaves substate ``running`` action free.
ACTION_STATE = "idle"


@dataclass(frozen=True)
class ChainCase:
    """One sm05 chained-reference variation.

    Attributes:
        state_def_qn: Qualified name of the SM05 state def under test.
        expected_guard: Python source the builder must place in
            ``Transition.guard``, or ``None`` for an eventless,
            unguarded transition.
        expected_on_entry: Python statement the builder must place in the
            ``idle`` state's ``on_entry`` slot, or ``None``.
        expected_context: Dotted path -> value that the interpreter
            context must hold after ``execute()``. A dotted key (e.g.
            ``"pt.x"``) is resolved through the bound structured object.
    """

    state_def_qn: str
    expected_guard: str | None
    expected_on_entry: str | None
    expected_context: dict[str, float]


CASES: list[ChainCase] = [
    # Two-segment chain in a guard: pt.x
    ChainCase(
        "SM05::MachineChainGuard",
        expected_guard="pt.x > 0.0",
        expected_on_entry=None,
        expected_context={"pt.x": 0.5},
    ),
    # Three-segment chain in a guard: box.inner.z
    ChainCase(
        "SM05::MachineChainNested",
        expected_guard="box.inner.z > 0.0",
        expected_on_entry=None,
        expected_context={"box.inner.z": 0.25},
    ),
    # Chained reference on an assignment right-hand side: reached := pt.x
    ChainCase(
        "SM05::MachineChainAssign",
        expected_guard=None,
        expected_on_entry="reached = pt.x",
        expected_context={"reached": 0.5, "pt.x": 0.5},
    ),
]


def _resolve(context: dict[str, Any], path: str) -> Any:
    """Resolve a dotted ``path`` against the interpreter ``context``."""
    head, *tail = path.split(".")
    value = context[head]
    for segment in tail:
        value = getattr(value, segment)
    return value


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(EXAMPLE.model_dir)


@pytest.fixture(
    scope="module",
    params=CASES,
    ids=lambda c: c.state_def_qn.split("::", 1)[1],
)
def case(request: pytest.FixtureRequest) -> ChainCase:
    """Yield every chained-reference shape sm05 exercises."""
    param: ChainCase = request.param
    return param


def test_chain_reference_guard_is_emitted_python(
    model: syside.Model,
    case: ChainCase,
) -> None:
    """The guard is the emitted dotted Python for the chained reference."""
    sc = build_statechart(model, case.state_def_qn)
    assert sc.transitions[0].guard == case.expected_guard


def test_chain_reference_on_entry_is_emitted(
    model: syside.Model,
    case: ChainCase,
) -> None:
    """The substate's ``on_entry`` is the emitted assignment statement."""
    sc = build_statechart(model, case.state_def_qn)
    assert sc.state_for(ACTION_STATE).on_entry == case.expected_on_entry


def test_binding_and_execution_resolve_chain(
    model: syside.Model,
    case: ChainCase,
) -> None:
    """Bound structured root + emitted chain reach the expected values."""
    sc = build_statechart(model, case.state_def_qn)
    interpreter = Interpreter(sc)
    interpreter.execute()
    for path, value in case.expected_context.items():
        assert _resolve(interpreter.context, path) == value
