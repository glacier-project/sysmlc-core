"""Port-aware signal interface (drives port-based connection routing)."""

from pathlib import Path

from sysmlc.semantics.statemachine.interface import machine_interface
from sysmlc.sysml.loading import load_model

FIX = Path("models/sm-examples/part01-two-parts")


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
