from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model
from tests.backends.quake.conftest import (
    SM_EXAMPLES_BY_DIR,
    transition_between,
)

if TYPE_CHECKING:
    from pathlib import Path

    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm11-send-effect"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


def test_send_effect_emits_send_and_drives_self_accept(
    model: syside.Model,
) -> None:
    """``do send new Ping()`` emits ``send("Ping")`` and self-delivers.

    The emitted internal event drives the same-machine accept
    transition end to end.
    """
    sc = build_statechart(model, "SM11::MachineSelfSend")
    assert transition_between(sc, "idle", "armed").action == 'send("Ping")'
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


def test_payload_args_emitted_as_kwargs_and_accepted(
    model: syside.Model,
) -> None:
    """Positional payload args become ``send()`` kwargs and round-trip.

    The kwargs are named by attribute; the payload-carrying send is
    accepted by the same machine end to end.
    """
    sc = build_statechart(model, "SM11::MachinePayload")
    assert (
        transition_between(sc, "idle", "armed").action
        == 'send("Reading", value=current)'
    )
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


def test_string_payload_arg_emitted_as_kwarg(model: syside.Model) -> None:
    """A string payload arg is emitted as a quoted Python kwarg."""
    sc = build_statechart(model, "SM11::MachineStringPayload")
    assert (
        transition_between(sc, "idle", "armed").action
        == 'send("Note", text="hi")'
    )


def test_payload_guard_reads_event_field_and_gates_at_runtime(
    model: syside.Model,
) -> None:
    """A payload field read in a guard emits and evaluates ``event.<f>``.

    The guard string uses sismic's ``event`` namespace and the
    accepted payload value gates the transition at runtime.
    """
    sc = build_statechart(model, "SM11::MachineReadablePayloadGuard")
    transition = transition_between(sc, "armed", "fired")
    assert transition.event == "Measurement"
    assert transition.guard == "event.value > 0.5"
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


def test_payload_effect_reads_event_field_and_captures_value(
    model: syside.Model,
) -> None:
    """A payload field read in an effect emits and evaluates ``event.<f>``.

    The effect string uses sismic's ``event`` namespace and the fired
    effect captures the accepted payload value.
    """
    sc = build_statechart(model, "SM11::MachineReadablePayloadEffect")
    assert (
        transition_between(sc, "armed", "fired").action
        == "captured = event.value"
    )
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration
    assert interpreter.context["captured"] == 0.9


def test_payload_chain_rewrites_root_and_reads_through_chain(
    model: syside.Model,
) -> None:
    """A payload field chain rewrites only its root to ``event``.

    The emitted guard reads through the chained field and the accepted
    payload is read through it at runtime.
    """
    sc = build_statechart(model, "SM11::MachineReadablePayloadChain")
    transition = transition_between(sc, "armed", "fired")
    assert transition.guard == "event.sample.value > 0.5"
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


def test_accept_payload_whole_uses_event(
    model: syside.Model,
) -> None:
    """A bare reference to the whole payload binding emits ``event``."""
    sc = build_statechart(model, "SM11::MachineReadablePayloadWhole")
    assert transition_between(sc, "armed", "fired").action == "captured = event"


def test_mixed_effect_emits_assign_then_send(model: syside.Model) -> None:
    """A mixed effect body emits the assign and the send, in order."""
    sc = build_statechart(model, "SM11::MachineMixed")
    action = transition_between(sc, "idle", "armed").action
    assert action is not None
    assert "count = count + 1" in action
    assert 'send("Ping")' in action
    assert action.index("count = count + 1") < action.index('send("Ping")')


def test_payload_guard_rejects_sent_value(model: syside.Model) -> None:
    """A false payload guard leaves the accepting state active."""
    sc = build_statechart(model, "SM11::MachineReadablePayloadRejected")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "armed" in interpreter.configuration
    assert "fired" not in interpreter.configuration


VIA_ALONE_MODEL = """
package ViaAlone {
    item def Ping;

    state def Machine {
        port p;
        entry; then idle;
        state idle;
        state armed;
        transition first idle do send new Ping() via p then armed;
    }
}
"""

VIA_MIXED_MODEL = """
package ViaMixed {
    private import ScalarValues::*;

    item def Ping;

    state def Machine {
        attribute count : Integer := 0;
        port p;
        entry; then idle;
        state idle;
        state armed;
        transition first idle do action {
            assign count := count + 1;
            send new Ping() via p;
        } then armed;
    }
}
"""


def test_standalone_via_send_is_dropped(tmp_path: Path) -> None:
    """A send through a port delivers only over the port's connections,
    so with no system context the transfer has no receiver."""
    model = _load_inline_model(tmp_path, VIA_ALONE_MODEL)
    sc = build_statechart(model, "ViaAlone::Machine")
    assert transition_between(sc, "idle", "armed").action is None


def test_standalone_via_send_keeps_sibling_statements(
    tmp_path: Path,
) -> None:
    """Dropping a via-send removes only that statement from the effect."""
    model = _load_inline_model(tmp_path, VIA_MIXED_MODEL)
    sc = build_statechart(model, "ViaMixed::Machine")
    assert transition_between(sc, "idle", "armed").action == "count = count + 1"
