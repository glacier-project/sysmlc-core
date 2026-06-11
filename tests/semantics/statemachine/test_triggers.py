from pathlib import Path

import syside

from sysmlc.semantics.statemachine import transitions, triggers
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import Trigger, TriggerKind
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import resolve
from tests.recording import RecordingBuilder

SM_DIR = Path(__file__).resolve().parents[3] / "models" / "sm-examples"


def _from_idle(
    model: syside.Model, qn: str
) -> tuple[syside.StateDefinition, syside.TransitionUsage]:
    machine = resolve(model, syside.StateDefinition, qn)
    for trans in transitions.container_transitions(machine):
        if transitions.source_path(machine, trans) == "idle":
            return machine, trans
    raise AssertionError(f"no transition from idle in {qn}")


def test_after_literal_seconds() -> None:
    model = load_model(SM_DIR / "sm13-time-trigger")
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    _, trans = _from_idle(model, "SM13::MachineAfterSeconds")
    trigger = triggers.classify(trans, compiler, stdlib)
    assert trigger is not None
    assert trigger.kind is TriggerKind.AFTER
    assert trigger.after == 5.0


def test_after_minutes_normalized_to_si() -> None:
    model = load_model(SM_DIR / "sm13-time-trigger")
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    _, trans = _from_idle(model, "SM13::MachineAfterMinutes")
    trigger = triggers.classify(trans, compiler, stdlib)
    assert trigger is not None
    assert trigger.after == 120.0


def test_after_attribute_reference_keeps_node() -> None:
    model = load_model(SM_DIR / "sm13-time-trigger")
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    _, trans = _from_idle(model, "SM13::MachineAfterAttribute")
    trigger = triggers.classify(trans, compiler, stdlib)
    assert trigger is not None
    assert trigger.kind is TriggerKind.AFTER
    assert isinstance(trigger.after, syside.Expression)


def test_signal_trigger_uses_payload_name() -> None:
    model = load_model(SM_DIR / "sm02-event-trigger")
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    _, trans = _from_idle(model, "SM02::Machine")
    trigger = triggers.classify(trans, compiler, stdlib)
    assert trigger is not None
    assert trigger.kind is TriggerKind.SIGNAL
    assert trigger.signal_name == "Tick"


def test_eventless_transition_is_none() -> None:
    model = load_model(SM_DIR / "sm01-helloworld")
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    _, trans = _from_idle(model, "SM01::Machine")
    assert triggers.classify(trans, compiler, stdlib) is None


# ---------------------------------------------------------------------------
# payload_name and via_port capture tests (use the driver + recording_builder)
# ---------------------------------------------------------------------------


def _signal_triggers(
    model_dir: str,
    qn: str,
    recording_builder: RecordingBuilder,
) -> list[Trigger]:
    model = load_model(SM_DIR / model_dir)
    StateMachineDriver(model).run(qn, recording_builder)
    return [
        t.trigger
        for t in recording_builder.transitions
        if t.trigger is not None and t.trigger.kind is TriggerKind.SIGNAL
    ]


def test_named_payload_is_captured(recording_builder: RecordingBuilder) -> None:
    (trigger,) = _signal_triggers(
        "sm02-event-trigger", "SM02::MachineNamed", recording_builder
    )
    assert trigger.signal_name == "Tick"
    assert trigger.payload_name == "reading"
    assert trigger.via_port == "commPort"


def test_unnamed_payload_is_none(recording_builder: RecordingBuilder) -> None:
    (trigger,) = _signal_triggers(
        "sm02-event-trigger", "SM02::MachinePortless", recording_builder
    )
    assert trigger.signal_name == "Tick"
    assert trigger.payload_name is None
    assert trigger.via_port is None


def test_via_port_is_captured(recording_builder: RecordingBuilder) -> None:
    (trigger,) = _signal_triggers(
        "sm02-event-trigger", "SM02::Machine", recording_builder
    )
    assert trigger.via_port == "commPort"
