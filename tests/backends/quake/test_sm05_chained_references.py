from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR

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
    return load_model(EXAMPLE.model_dir)


@pytest.mark.parametrize(
    "case", CASES, ids=lambda case: case.state_def_qn.split("::", 1)[1]
)
def test_chained_reference_emitted_and_resolved_at_runtime(
    model: syside.Model,
    case: ChainCase,
) -> None:
    """A chained reference emits dotted Python that resolves when run.

    The guard and the entry assignment carry the emitted dotted
    source; the bound structured root plus the emitted chain reach the
    expected values after execution.
    """
    sc = build_statechart(model, case.state_def_qn)
    assert sc.transitions[0].guard == case.expected_guard
    assert sc.state_for(ACTION_STATE).on_entry == case.expected_on_entry
    interpreter = Interpreter(sc)
    interpreter.execute()
    for path, value in case.expected_context.items():
        assert _resolve(interpreter.context, path) == value
