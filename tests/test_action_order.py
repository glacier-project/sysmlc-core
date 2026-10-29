from pathlib import Path

import pytest
import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "action-order"


@pytest.fixture(scope="module")
def order_model() -> syside.Model:
    return load_model(FIXTURES)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Declaration", ["multiply", "initialize"]),
        ("Reversed", ["initialize", "multiply"]),
        ("Boundaries", ["initialize", "multiply"]),
        ("UnitMultiplicity", ["initialize", "multiply"]),
        ("Duplicate", ["initialize", "multiply"]),
        ("LocalStart", ["initialize", "start"]),
        ("LocalDone", ["initialize", "done"]),
        ("Empty", []),
    ],
)
def test_inline_order(
    order_model: syside.Model, name: str, expected: list[str]
) -> None:
    machine = resolve(
        order_model, syside.StateDefinition, f"ActionOrder::{name}"
    )
    slot = machine.owned_states.collect()[0].entry_action
    assert [a.name for a in actions.inline_actions(slot)] == expected


def test_anonymous_then_chain(order_model: syside.Model) -> None:
    machine = resolve(order_model, syside.StateDefinition, "ActionOrder::Then")
    slot = machine.owned_states.collect()[0].entry_action
    assert slot is not None
    statements = actions.inline_actions(slot)
    assert statements == slot.nested_actions.collect()
    assert len(statements) == 2
    assert all(isinstance(a, syside.AssignmentActionUsage) for a in statements)


@pytest.mark.parametrize(
    "name",
    [
        "Partial",
        "Disconnected",
        "WrongStart",
        "WrongDone",
        "Branch",
        "Merge",
        "Cycle",
        "Guarded",
        "Chained",
        "Foreign",
        "ShadowStart",
        "Multiplicity",
        "EndMultiplicity",
        "ActionMultiplicity",
        "SuccessionFlow",
    ],
)
def test_unsupported_sequence_is_rejected(
    order_model: syside.Model, name: str
) -> None:
    machine = resolve(
        order_model, syside.StateDefinition, f"ActionOrder::{name}"
    )
    slot = machine.owned_states.collect()[0].entry_action
    with pytest.raises(
        UnsupportedConstructError, match=r"succession|sequence|multiplicity"
    ) as error:
        actions.inline_actions(slot)
    assert error.value.node is not None
