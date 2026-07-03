from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    from pathlib import Path

    import syside
    from sismic.model import Statechart, Transition

EXAMPLE = SM_EXAMPLES_BY_DIR["sm11-send-effect"]


def _action_of(sc: Statechart, source: str, target: str) -> str | None:
    """The action string of the transition from ``source`` to ``target``."""
    for transition in sc.transitions:
        if transition.source == source and transition.target == target:
            action: str | None = transition.action
            return action
    raise AssertionError(f"no transition {source} -> {target}")


def _transition(sc: Statechart, source: str, target: str) -> Transition:
    """The transition from ``source`` to ``target``."""
    for transition in sc.transitions:
        if transition.source == source and transition.target == target:
            return transition
    raise AssertionError(f"no transition {source} -> {target}")


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


def test_send_effect_emits_event(model: syside.Model) -> None:
    """A ``do send new Ping()`` effect emits a sismic ``send('Ping')`` call."""
    sc = build_statechart(model, "SM11::MachineSelfSend")
    assert _action_of(sc, "idle", "armed") == 'send("Ping")'


def test_payload_args_emitted_as_kwargs(model: syside.Model) -> None:
    """Positional payload args become ``send()`` kwargs by attribute name."""
    sc = build_statechart(model, "SM11::MachinePayload")
    assert _action_of(sc, "idle", "armed") == 'send("Reading", value=current)'


def test_string_payload_arg_emitted_as_kwarg(model: syside.Model) -> None:
    """A string payload arg is emitted as a quoted Python kwarg."""
    sc = build_statechart(model, "SM11::MachineStringPayload")
    assert _action_of(sc, "idle", "armed") == 'send("Note", text="hi")'


def test_accept_payload_guard_uses_event_field(
    model: syside.Model,
) -> None:
    """A payload field read in a guard emits sismic's ``event.<field>``."""
    sc = build_statechart(model, "SM11::MachineReadablePayloadGuard")
    transition = _transition(sc, "armed", "fired")
    assert transition.event == "Measurement"
    assert transition.guard == "event.value > 0.5"


def test_accept_payload_effect_uses_event_field(
    model: syside.Model,
) -> None:
    """A payload field read in an effect emits sismic's ``event.<field>``."""
    sc = build_statechart(model, "SM11::MachineReadablePayloadEffect")
    assert _action_of(sc, "armed", "fired") == "captured = event.value"


def test_accept_payload_chain_uses_event_root(
    model: syside.Model,
) -> None:
    """A payload field chain rewrites only the payload root to ``event``."""
    sc = build_statechart(model, "SM11::MachineReadablePayloadChain")
    transition = _transition(sc, "armed", "fired")
    assert transition.guard == "event.sample.value > 0.5"


def test_mixed_effect_emits_assign_then_send(model: syside.Model) -> None:
    """A mixed effect body emits the assign and the send, in order."""
    sc = build_statechart(model, "SM11::MachineMixed")
    action = _action_of(sc, "idle", "armed")
    assert action is not None
    assert "count = count + 1" in action
    assert 'send("Ping")' in action
    assert action.index("count = count + 1") < action.index('send("Ping")')


def test_self_send_drives_accept_end_to_end(model: syside.Model) -> None:
    """The sent internal event drives the same-machine accept transition."""
    sc = build_statechart(model, "SM11::MachineSelfSend")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


def test_payload_send_drives_accept_end_to_end(model: syside.Model) -> None:
    """A payload-carrying send is accepted by the same machine end-to-end."""
    sc = build_statechart(model, "SM11::MachinePayload")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


def test_payload_guard_reads_sent_value(model: syside.Model) -> None:
    """The accepted payload value gates the transition at runtime."""
    sc = build_statechart(model, "SM11::MachineReadablePayloadGuard")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


def test_payload_guard_rejects_sent_value(model: syside.Model) -> None:
    """A false payload guard leaves the accepting state active."""
    sc = build_statechart(model, "SM11::MachineReadablePayloadRejected")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "armed" in interpreter.configuration
    assert "fired" not in interpreter.configuration


def test_payload_effect_reads_sent_value(model: syside.Model) -> None:
    """The transition effect can read the accepted payload value."""
    sc = build_statechart(model, "SM11::MachineReadablePayloadEffect")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration
    assert interpreter.context["captured"] == 0.9


def test_payload_chain_reads_sent_value(model: syside.Model) -> None:
    """The accepted payload can be read through a chained field."""
    sc = build_statechart(model, "SM11::MachineReadablePayloadChain")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


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
    assert _action_of(sc, "idle", "armed") is None


def test_standalone_via_send_keeps_sibling_statements(
    tmp_path: Path,
) -> None:
    """Dropping a via-send removes only that statement from the effect."""
    model = _load_inline_model(tmp_path, VIA_MIXED_MODEL)
    sc = build_statechart(model, "ViaMixed::Machine")
    assert _action_of(sc, "idle", "armed") == "count = count + 1"
