from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.loader import load_syside_model
from tests.generator.sismic.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside
    from sismic.model import Statechart

EXAMPLE = SM_EXAMPLES_BY_DIR["sm11-send-effect"]


def _action_of(sc: Statechart, source: str, target: str) -> str | None:
    """The action string of the transition from ``source`` to ``target``."""
    for transition in sc.transitions:
        if transition.source == source and transition.target == target:
            action: str | None = transition.action
            return action
    raise AssertionError(f"no transition {source} -> {target}")


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(EXAMPLE.model_dir)


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
