import pytest

from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.program import COMPLETION_EVENT
from sysmlc.errors import UnsupportedConstructError


def test_helloworld_is_two_states_one_completion(sm_models: dict) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    assert [s.name for s in program.states] == ["idle", "running"]
    assert program.initial == "idle"
    assert program.transitions[0].event is COMPLETION_EVENT
    assert program.events == ()


def test_event_trigger_makes_a_signal_event(sm_models: dict) -> None:
    program = build_statix(sm_models["sm02"], "SM02::Machine")
    assert "Tick" in program.events
    assert program.transitions[0].event == "Tick"


def test_guard_becomes_a_cguard(sm_models: dict) -> None:
    program = build_statix(sm_models["sm03"], "SM03::MachineRef")
    assert program.transitions[0].guard is not None
    guard = next(
        g for g in program.guards if g.name == program.transitions[0].guard
    )
    assert guard.expr == "ctx->enabled"
    assert any(
        f.name == "enabled" and f.c_type == "bool"
        for f in program.context.fields
    )


def test_entry_action_is_captured(sm_models: dict) -> None:
    program = build_statix(sm_models["sm04"], "SM04::MachineEntryIncrement")
    idle = next(s for s in program.states if s.name == "idle")
    assert idle.entry_action_id is not None
    action = next(a for a in program.actions if a.name == idle.entry_action_id)
    assert action.statements == ("ctx->counter = ctx->counter + 1;",)


def test_integer_and_real_types(sm_models: dict) -> None:
    program = build_statix(sm_models["sm03"], "SM03::MachineRealLiteral")
    assert any(
        f.name == "x" and f.c_type == "double" for f in program.context.fields
    )


def test_composite_struct_and_chain(sm_models: dict) -> None:
    program = build_statix(sm_models["sm05"], "SM05::MachineChainNested")
    # nested structs registered inner-first (Inner before Box)
    struct_names = [s.name for s in program.context.structs]
    assert struct_names.index(
        "sm05_machine_chain_nested_inner_t"
    ) < struct_names.index("sm05_machine_chain_nested_box_t")
    guard = program.guards[0]
    assert guard.expr == "ctx->box.inner.z > 0.0"


def test_rejects_composite_state(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm08"], "SM08::MachineNested")


def test_rejects_parallel_state(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm09"], "SM09::MachineParallel")


def test_rejects_send_effect(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm11"], "SM11::MachineSelfSend")
