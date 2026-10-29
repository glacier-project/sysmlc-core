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


@pytest.mark.parametrize(
    "declaration",
    [
        "ref occurrence start;",
        "action start assign c := c * 10;",
        "action done assign c := c * 10;",
    ],
)
def test_shadowed_action_boundary_is_rejected_upstream(
    tmp_path: Path, declaration: str
) -> None:
    # Syside 0.11 rejects these before the compiler's ordering policy applies.
    (tmp_path / "model.sysml").write_text(
        """package Test {
            private import ScalarValues::*;
            state def Machine {
                attribute c : Integer := 0;
                entry; then idle;
                state idle {
                    entry action {
                        DECLARATION
                    }
                }
            }
        }""".replace("DECLARATION", declaration)
    )
    with pytest.raises(ValueError, match="namespace-distinguishability"):
        load_model(tmp_path)


def test_qualified_user_start_is_not_an_action_boundary(
    tmp_path: Path,
) -> None:
    (tmp_path / "model.sysml").write_text(
        """package Test {
            private import ScalarValues::*;
            action start;
            state def Machine {
                attribute c : Integer := 0;
                entry; then idle;
                state idle {
                    entry action {
                        action initialize assign c := 1;
                        first Test::start then initialize;
                    }
                }
            }
        }"""
    )
    model = load_model(tmp_path)
    machine = resolve(model, syside.StateDefinition, "Test::Machine")
    with pytest.raises(UnsupportedConstructError, match="succession"):
        actions.inline_actions(machine.owned_states.collect()[0].entry_action)
