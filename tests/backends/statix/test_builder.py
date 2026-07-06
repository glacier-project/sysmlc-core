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


def test_composite_state_tree_is_wired(sm_models: dict) -> None:
    program = build_statix(sm_models["sm08"], "SM08::MachineNested")
    by_name = {s.name: s for s in program.states}
    # Composite running descends into initial child; top-level parent None.
    assert by_name["running"].initial_child == "running::warming"
    assert by_name["running"].parent is None
    # Nested leaves carry their dotted display name and parent.
    assert by_name["running::warming"].parent == "running"
    assert by_name["running::hot"].parent == "running"
    assert by_name["running::warming"].initial_child is None
    assert program.initial == "idle"
    assert program.max_depth == 2


def test_deep_nesting_sets_max_depth(sm_models: dict) -> None:
    program = build_statix(sm_models["sm08"], "SM08::MachineDeep")
    assert program.max_depth == 3
    by_name = {s.name: s for s in program.states}
    assert by_name["running::warming"].initial_child == "running::warming::low"


def test_name_collision_kept_distinct(sm_models: dict) -> None:
    program = build_statix(sm_models["sm08"], "SM08::MachineNameCollision")
    names = {s.name for s in program.states}
    expected = {
        "groupA::active",
        "groupA::paused",
        "groupB::active",
        "groupB::paused",
    }
    assert expected <= names


def test_cross_boundary_transitions_use_dotted_endpoints(
    sm_models: dict,
) -> None:
    out = build_statix(sm_models["sm08"], "SM08::MachineCrossOut")
    assert any(
        t.source == "running::hot" and t.target == "stopped"
        for t in out.transitions
    )
    into = build_statix(sm_models["sm08"], "SM08::MachineCrossIn")
    assert any(
        t.source == "idle" and t.target == "running::hot"
        for t in into.transitions
    )


def test_rejects_parallel_state(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm09"], "SM09::MachineParallel")


def test_rejects_send_effect(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm11"], "SM11::MachineSelfSend")


def test_root_done_synthesizes_final(sm_models: dict) -> None:
    program = build_statix(sm_models["sm10"], "SM10::MachineRootDone")
    done = next(s for s in program.states if s.name == "done")
    assert done.is_final
    assert done.parent is None
    assert done.initial_child is None
    # The `running then done` transition targets the final.
    assert any(
        t.source == "running" and t.target == "done"
        for t in program.transitions
    )


def test_nested_done_scoped_final(sm_models: dict) -> None:
    program = build_statix(sm_models["sm10"], "SM10::MachineNestedDone")
    done = next(s for s in program.states if s.name == "running::done")
    assert done.is_final
    assert done.parent == "running"
    assert any(
        t.source == "running::hot" and t.target == "running::done"
        for t in program.transitions
    )


def test_two_done_shares_one_final(sm_models: dict) -> None:
    program = build_statix(sm_models["sm10"], "SM10::MachineTwoDone")
    finals = [s for s in program.states if s.is_final]
    assert [s.name for s in finals] == ["done"]  # exactly one, shared
    assert sum(1 for t in program.transitions if t.target == "done") == 2


def test_parallel_done_is_rejected(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm10"], "SM10::MachineParallelDone")


def _entry_statements(program, state_name):
    """The statements of a state's entry action, or () if it has none."""
    state = next(s for s in program.states if s.name == state_name)
    if state.entry_action_id is None:
        return ()
    action = next(a for a in program.actions if a.name == state.entry_action_id)
    return action.statements


def test_do_action_fused_into_entry(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineDoAssign")
    assert _entry_statements(program, "working") == (
        "ctx->progress = ctx->progress + 1;",
    )


def test_do_multi_keeps_declaration_order(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineDoMulti")
    assert _entry_statements(program, "working") == (
        "ctx->a = 1;",
        "ctx->b = ctx->a + 2;",
    )


def test_do_shorthand_fused_into_entry(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineDoShorthand")
    assert _entry_statements(program, "working") == (
        "ctx->progress = ctx->progress + 1;",
    )


def test_entry_runs_before_do(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineEntryThenDo")
    assert _entry_statements(program, "working") == (
        "ctx->log = 1;",
        "ctx->log = ctx->log + 10;",
    )


def test_do_on_composite_fuses_into_its_entry(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineCompositeDo")
    assert _entry_statements(program, "working") == (
        "ctx->progress = ctx->progress + 1;",
    )


def test_empty_do_is_a_noop(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineEmptyDo")
    working = next(s for s in program.states if s.name == "working")
    assert working.entry_action_id is None


def test_named_empty_do_is_a_noop(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineNamedEmptyDo")
    working = next(s for s in program.states if s.name == "working")
    assert working.entry_action_id is None


def test_root_empty_do_is_a_noop(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineRootEmptyDo")
    assert all(s.entry_action_id is None for s in program.states)


def test_do_send_is_rejected(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm12"], "SM12::MachineDoSend")


def test_do_send_shorthand_is_rejected(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm12"], "SM12::MachineDoSendShorthand")


def test_machine_level_do_is_rejected(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm12"], "SM12::MachineRootDo")


def test_machine_level_entry_then_do_is_rejected(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm12"], "SM12::MachineRootEntryThenDo")


def test_parallel_do_is_rejected(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm12"], "SM12::MachineParallelDo")
