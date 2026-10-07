"""Port-aware signal interface (drives port-based connection routing)."""

from pathlib import Path

from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

from sysmlc.semantics.statemachine.interface import machine_interface
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model

FIX = SM_EXAMPLES_DIR / "part01-two-parts"


def test_interface_records_accept_and_send_ports() -> None:
    model = load_model(FIX)

    plant = machine_interface(model, "Part01::PlantBehavior")
    # name-level sets unchanged (existing rig path relies on these):
    assert plant.accepted == frozenset({"Ping"})
    assert plant.sent == frozenset({"Pong"})
    # new port-scoped maps: signal grouped by its `via` port.
    assert plant.accepted_via == {"commPort": frozenset({"Ping"})}
    assert plant.sent_via == {"commPort": frozenset({"Pong"})}

    tester = machine_interface(model, "Part01::TesterBehavior")
    assert tester.sent_via == {"commPort": frozenset({"Ping"})}
    assert tester.accepted_via == {"commPort": frozenset({"Pong"})}


def test_interface_collects_nested_sends_and_peer_accepts(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(
        tmp_path,
        """
        package Interface {
            item def Go;
            item def Done;
            state def Plant {
                port commPort;
                entry; then idle;
                state idle;
                state working {
                    entry; then active;
                    state active { entry send new Done() via commPort; }
                }
                transition first idle accept Go then working;
            }
            state def Tester {
                port commPort;
                entry; then waiting;
                state waiting { entry send new Go() via commPort; }
                transition first waiting accept Done then done;
            }
        }
    """,
    )
    plant = machine_interface(model, "Interface::Plant")
    assert plant.accepted == frozenset({"Go"})
    assert plant.sent == frozenset({"Done"})
    assert plant.sent_via == {"commPort": frozenset({"Done"})}
    tester = machine_interface(model, "Interface::Tester")
    assert tester.accepted == frozenset({"Done"})
    assert tester.sent == frozenset({"Go"})
