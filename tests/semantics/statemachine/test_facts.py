from sysmlc.semantics.statemachine.facts import (
    AttributeBinding,
    SignalTrigger,
    StateFact,
    StateKind,
)


def test_signal_trigger_defaults() -> None:
    t = SignalTrigger(signal_name="Tick")
    assert t.payload_name is None
    assert t.payload_feature is None
    assert t.via_port is None


def test_state_fact_constructible() -> None:
    s = StateFact(
        name="idle",
        kind=StateKind.LEAF,
        parent="root",
        initial_substate=None,
        entry_action=None,
        do_action=None,
        exit_action=None,
    )
    assert s.kind is StateKind.LEAF
    assert s.parent == "root"


def test_attribute_binding_constructible() -> None:
    b = AttributeBinding(scope="", name="x", value=1.0)
    assert b.name == "x"
    assert b.value == 1.0
