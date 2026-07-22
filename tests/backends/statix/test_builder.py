from pathlib import Path

import pytest

from sysmlc.backends.statix.builder import StatixBuilder, build_statix
from sysmlc.backends.statix.program import (
    COMPLETION_EVENT,
    INTERNAL_TARGET,
    TIMEOUT_EVENT,
    CProgram,
    CSend,
)
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine.facts import StateFact, StateKind
from sysmlc.sysml.loading import load_model

_INTCALL = Path(__file__).resolve().parent / "fixtures" / "intcall"
_DEEPCHAIN = Path(__file__).resolve().parent / "fixtures" / "deepchain"
_TIMERREJECT = Path(__file__).resolve().parent / "fixtures" / "timerreject"
_WHENREJECT = Path(__file__).resolve().parent / "fixtures" / "whenreject"
_ENUMREJECT = Path(__file__).resolve().parent / "fixtures" / "enumreject"
_ENUMCOMPOSITE = Path(__file__).resolve().parent / "fixtures" / "enumcomposite"


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


def test_parallel_root_builds_without_rejection(sm_models: dict) -> None:
    program = build_statix(sm_models["sm09"], "SM09::MachineParallel")
    assert program.active_capacity == 2
    root = next(s for s in program.states if s.name == "MachineParallel")
    assert root.region_count == 2
    assert root.parent is None
    assert program.initial == "MachineParallel"
    lights = next(s for s in program.states if s.name == "lights")
    sound = next(s for s in program.states if s.name == "sound")
    assert lights.slot != sound.slot
    assert {lights.slot, sound.slot} == {0, 1}


def test_nested_parallel_builds_without_rejection(sm_models: dict) -> None:
    program = build_statix(sm_models["sm09"], "SM09::MachineNestedParallel")
    dual = next(s for s in program.states if s.name == "dual")
    assert dual.region_count == 2
    assert dual.parent is None  # top-level substate under composite root
    assert (
        program.active_capacity == 2
    )  # idle (cap=1) vs dual (cap=2): max, not sum


def test_microwave_behavior_builds_without_rejection(
    sm_models_showcase: dict,
) -> None:
    program = build_statix(
        sm_models_showcase["microwave"], "Microwave::MicrowaveBehavior"
    )
    heating = next(s for s in program.states if s.name == "cooking::heating")
    assert heating.region_count == 2
    assert (
        program.active_capacity == 2
    )  # idle/paused (cap=1) vs heating (cap=2): max, not sum


def test_nested_parallel_under_active_parallel_is_rejected() -> None:
    builder = StatixBuilder("Synthetic::Nested")
    builder.add_state(
        StateFact(
            name="Nested",
            parent=None,
            kind=StateKind.COMPOSITE,
            initial_substate="outer",
            entry_action=None,
            do_action=None,
            exit_action=None,
        )
    )
    builder.add_state(
        StateFact(
            name="outer",
            parent="Nested",
            kind=StateKind.PARALLEL,
            initial_substate=None,
            entry_action=None,
            do_action=None,
            exit_action=None,
        )
    )
    builder.add_state(
        StateFact(
            name="regionA",
            parent="outer",
            kind=StateKind.COMPOSITE,
            initial_substate="inner",
            entry_action=None,
            do_action=None,
            exit_action=None,
        )
    )
    with pytest.raises(UnsupportedConstructError, match="fork level"):
        builder.add_state(
            StateFact(
                name="inner",
                parent="regionA",
                kind=StateKind.PARALLEL,
                initial_substate=None,
                entry_action=None,
                do_action=None,
                exit_action=None,
            )
        )


def test_final_state_is_still_rejected() -> None:
    builder = StatixBuilder("Synthetic::Final")
    with pytest.raises(UnsupportedConstructError, match="FINAL"):
        builder.add_state(
            StateFact(
                name="done",
                parent="root",
                kind=StateKind.FINAL,
                initial_substate=None,
                entry_action=None,
                do_action=None,
                exit_action=None,
            )
        )


def test_self_send_lowers_to_csend(sm_models: dict) -> None:
    program = build_statix(sm_models["sm11"], "SM11::MachineSelfSend")
    assert program.has_send
    # The sent Ping is a registered event even on the send side.
    assert "Ping" in program.events
    effect = next(a for a in program.actions if "idle_completion" in a.name)
    assert effect.statements == (CSend(event="Ping"),)


def test_send_payload_args_are_ignored(sm_models: dict) -> None:
    # `send new Reading(current)`: id-only enqueue, argument dropped.
    program = build_statix(sm_models["sm11"], "SM11::MachinePayload")
    assert program.has_send
    assert "Reading" in program.events
    effect = next(a for a in program.actions if "idle_completion" in a.name)
    assert effect.statements == (CSend(event="Reading"),)


def test_mixed_effect_preserves_assign_then_send_order(sm_models: dict) -> None:
    program = build_statix(sm_models["sm11"], "SM11::MachineMixed")
    effect = next(a for a in program.actions if "idle_completion" in a.name)
    assert len(effect.statements) == 2
    assert isinstance(effect.statements[0], str)  # the assign
    assert "count" in effect.statements[0]
    assert effect.statements[1] == CSend(event="Ping")


def test_send_only_event_still_registered(sm_models: dict) -> None:
    # MachineMixed sends Ping but never accepts it: the id must still exist.
    program = build_statix(sm_models["sm11"], "SM11::MachineMixed")
    assert "Ping" in program.events


def test_non_send_machine_has_no_send(sm_models: dict) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    assert not program.has_send


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


def test_parallel_done_builds_without_rejection(sm_models: dict) -> None:
    program = build_statix(sm_models["sm10"], "SM10::MachineParallelDone")
    finals = [s for s in program.states if s.is_final]
    assert len(finals) == 2


def _entry_statements(
    program: CProgram,
    state_name: str,
) -> tuple[str | CSend, ...]:
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


def test_do_send_lowers_to_entry_csend(sm_models: dict) -> None:
    # A `do send` fuses into the entry action like any other do body.
    program = build_statix(sm_models["sm12"], "SM12::MachineDoSend")
    assert program.has_send
    working = next(a for a in program.actions if "working_entry" in a.name)
    assert working.statements == (CSend(event="Ping"),)


def test_do_send_shorthand_lowers_to_entry_csend(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineDoSendShorthand")
    working = next(a for a in program.actions if "working_entry" in a.name)
    assert working.statements == (CSend(event="Ping"),)


def test_machine_level_do_is_rejected(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm12"], "SM12::MachineRootDo")


def test_machine_level_entry_then_do_is_rejected(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        build_statix(sm_models["sm12"], "SM12::MachineRootEntryThenDo")


def test_parallel_do_fuses_into_region_entry(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineParallelDo")
    assert _entry_statements(program, "regionA") == (
        "ctx->counter = ctx->counter + 1;",
    )


def test_builder_compiles_asserted_constraints(sm_models: dict) -> None:
    prog = build_statix(sm_models["sm17"], "SM17::MachineScoped")
    # Two constraints on this model: root (always) level > 0.0, and
    # idle-scoped level <= 2.0. Both lower into prog.invariants.
    assert len(prog.invariants) == 2
    root, scoped = prog.invariants[0], prog.invariants[1]
    assert root.scope is None
    assert scoped.scope == "idle"
    # Guards are deduped into prog.guards; neither is empty.
    guard_map = {g.name: g.expr for g in prog.guards}
    assert guard_map[root.guard] == "ctx->level > 0.0"
    assert guard_map[scoped.guard] == "ctx->level <= 2.0"


def test_builder_compiles_negated_constraint(sm_models: dict) -> None:
    prog = build_statix(sm_models["sm17"], "SM17::MachineNegated")
    assert len(prog.invariants) == 1
    inv = prog.invariants[0]
    guard_map = {g.name: g.expr for g in prog.guards}
    # assert not (level > 2.0) -> wrapped in !(...).
    assert guard_map[inv.guard] == "!(ctx->level > 2.0)"


def test_function_constraint_now_builds_with_math(sm_models: dict) -> None:
    program = build_statix(sm_models["sm17"], "SM17::MachineFunctionViolation")
    assert program.needs_math is True
    assert any(g.expr == "cos(ctx->x) <= 0.0" for g in program.guards)


def test_integer_library_assignment_is_rejected() -> None:
    model = load_model(_INTCALL)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "INTCALL::Machine")


def test_readable_guard_machine_builds(sm_models: dict) -> None:
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadGuard"
    )
    # The guard reads the payload...
    guard = next(g for g in program.guards)
    assert guard.expr == "sc_event_payload_f64(event) > 0.5"
    # ...so the send marshals ctx->current.
    effect = next(a for a in program.actions if "idle_completion" in a.name)
    assert effect.statements == (
        CSend(event="Measurement", value_expr="ctx->current"),
    )


def test_readable_effect_machine_builds(sm_models: dict) -> None:
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadEffect"
    )
    # The action id hint embeds the raw event name: "armed_Measurement_effect".
    capture = next(
        a for a in program.actions if a.name == "armed_Measurement_effect"
    )
    assert capture.statements == (
        "ctx->captured = sc_event_payload_f64(event);",
    )


def test_unread_payload_sends_stay_id_only(sm_models: dict) -> None:
    # Integer / String constructor args must never be rendered: these
    # machines' payloads are not read, so their sends stay id-only.
    for qn, event in (
        ("SM11::MachinePayload", "Reading"),
        ("SM11::MachineStringPayload", "Note"),
    ):
        program = build_statix(sm_models["sm11"], qn)
        effect = next(a for a in program.actions if "idle_completion" in a.name)
        assert effect.statements == (CSend(event=event, value_expr=None),)


def test_two_segment_chain_machine_builds(sm_models: dict) -> None:
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadChain"
    )
    guard = next(g for g in program.guards)
    assert guard.expr == "sc_event_payload_f64(event) > 0.5"
    # The send marshals ctx->sample.value; the unread `current` argument
    # (bound to Measurement.value) is dropped, never rendered.
    effect = next(a for a in program.actions if "idle_completion" in a.name)
    assert effect.statements == (
        CSend(event="Measurement", value_expr="ctx->sample.value"),
    )


def test_three_segment_chain_is_rejected(sm_models: dict) -> None:
    model = load_model(_DEEPCHAIN)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "DEEPCHAIN::MachineDeepChain")


def test_chain_on_non_real_leaf_is_rejected() -> None:
    model = load_model(_DEEPCHAIN)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "DEEPCHAIN::MachineChainOnIntegerLeaf")


def test_chain_with_no_matching_send_argument_is_rejected() -> None:
    model = load_model(_DEEPCHAIN)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "DEEPCHAIN::MachineChainNoMatchingArg")


def test_chain_on_non_reference_send_argument_is_rejected() -> None:
    model = load_model(_DEEPCHAIN)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "DEEPCHAIN::MachineChainOnInlineArg")


def test_after_literal_seconds_builds_timeout_row(sm_models: dict) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterSeconds")
    assert program.has_timer
    assert not program.timeouts_use_ctx
    assert len(program.timeouts) == 1
    row = program.timeouts[0]
    assert row.source == "idle"
    assert row.is_at is False
    assert row.literal_ticks == "(5u * SC_TICKS_PER_SECOND)"
    assert row.attr_expr is None
    timed = next(
        t
        for t in program.transitions
        if t.source == "idle" and t.target == "running"
    )
    assert timed.event == TIMEOUT_EVENT


def test_after_literal_minutes_normalizes_to_seconds(sm_models: dict) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterMinutes")
    assert program.timeouts[0].literal_ticks == "(120u * SC_TICKS_PER_SECOND)"


def test_at_attribute_driven_renders_ctx_field(sm_models: dict) -> None:
    # MachineAt's `deadline` is a TimeInstantValue attribute, not a literal.
    program = build_statix(sm_models["sm13"], "SM13::MachineAt")
    row = program.timeouts[0]
    assert row.is_at is True
    assert row.attr_expr == "ctx->deadline"
    assert row.literal_ticks is None
    assert program.timeouts_use_ctx is True


def test_after_attribute_reference_renders_ctx_field(sm_models: dict) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterAttribute")
    assert program.timeouts[0].attr_expr == "ctx->pickDuration"


def test_after_chained_reference_renders_nested_ctx_field(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterChain")
    assert program.timeouts[0].attr_expr == "ctx->holder.delay"


def test_after_with_guard_keeps_its_own_guard(sm_models: dict) -> None:
    # `accept after 5 [s] if ready`: the transition's guard is untouched,
    # the same guard mechanism as any other transition.
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterGuard")
    timed = next(t for t in program.transitions if t.event == TIMEOUT_EVENT)
    assert timed.guard is not None
    guard = next(g for g in program.guards if g.name == timed.guard)
    assert guard.expr == "ctx->ready"


def test_literal_only_machine_has_no_ctx_use(sm_models: dict) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterSeconds")
    assert program.timeouts_use_ctx is False


def test_self_loop_and_reentry_still_build(sm_models: dict) -> None:
    # Not conformance-tested by leaf comparison (Task 7 skips them there),
    # but they must build without raising.
    for qn in (
        "SM13::MachineAfterSelfLoop",
        "SM13::MachineAfterReentry",
        "SM13::MachineAtReentry",
    ):
        program = build_statix(sm_models["sm13"], qn)
        assert program.has_timer


def test_too_many_signal_events_is_rejected() -> None:
    # SC_EVENT_TIMEOUT reserves a second id at the top of the 16-bit event
    # space (alongside the existing SC_EVENT_COMPLETION); a real fixture
    # with 65,534+ distinct signal events isn't practical to write, so this
    # pokes the builder's internal bookkeeping directly instead.
    builder = StatixBuilder("TEST::Machine")
    for i in range(65534):
        builder._events.setdefault(f"E{i}", None)
    builder.add_state(
        StateFact(
            name="TEST::Machine",
            kind=StateKind.COMPOSITE,
            parent=None,
            initial_substate="idle",
            entry_action=None,
            do_action=None,
            exit_action=None,
        )
    )
    builder.add_state(
        StateFact(
            name="idle",
            kind=StateKind.LEAF,
            parent="TEST::Machine",
            initial_substate=None,
            entry_action=None,
            do_action=None,
            exit_action=None,
        )
    )
    with pytest.raises(UnsupportedConstructError):
        builder.result()


def test_timer_on_composite_source_is_rejected() -> None:
    model = load_model(_TIMERREJECT)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "TIMERREJECT::MachineTimerOnComposite")


def test_second_timer_on_same_source_is_rejected() -> None:
    model = load_model(_TIMERREJECT)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "TIMERREJECT::MachineTimerTwice")


def test_literal_duration_out_of_range_is_rejected() -> None:
    model = load_model(_TIMERREJECT)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "TIMERREJECT::MachineTimerOutOfRange")


def test_bare_when_arms_and_guards_a_single_transition(sm_models: dict) -> None:
    program = build_statix(sm_models["sm16"], "SM16::MachineWhenBare")
    assert program.has_when
    assert program.when_count == 1
    when = next(t for t in program.transitions if t.target == "running")
    assert when.event == COMPLETION_EVENT
    guard = next(g for g in program.guards if g.name == when.guard)
    assert guard.expr == "runtime->when_armed[0] && (ctx->hot)"
    entry = next(a for a in program.actions if a.name == "idle_entry")
    assert entry.statements == ("runtime->when_armed[0] = true;",)


def test_guarded_when_emits_real_and_negated_consumer(sm_models: dict) -> None:
    program = build_statix(sm_models["sm16"], "SM16::MachineWhenGuard")
    assert program.when_count == 1
    real = next(t for t in program.transitions if t.target == "running")
    consumer = next(
        t
        for t in program.transitions
        if t.target == INTERNAL_TARGET and t.source == "idle"
    )
    real_guard = next(g for g in program.guards if g.name == real.guard)
    consumer_guard = next(g for g in program.guards if g.name == consumer.guard)
    assert real_guard.expr == (
        "runtime->when_armed[0] && (ctx->hot) && (ctx->enabled)"
    )
    assert consumer_guard.expr == (
        "runtime->when_armed[0] && (ctx->hot) && !(ctx->enabled)"
    )
    consumer_action = next(
        a for a in program.actions if a.name == consumer.action
    )
    assert consumer_action.statements == ("runtime->when_armed[0] = false;",)


def test_two_when_triggers_on_one_source_get_independent_slots(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm16"], "SM16::MachineWhenTwo")
    assert program.when_count == 2
    entry = next(a for a in program.actions if a.name == "idle_entry")
    assert entry.statements == (
        "runtime->when_armed[0] = true;",
        "runtime->when_armed[1] = true;",
    )


def test_when_self_loop_is_rejected() -> None:
    model = load_model(_WHENREJECT)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "WHENREJECT::MachineWhenSelfLoop")


def test_when_on_composite_source_is_rejected() -> None:
    model = load_model(_WHENREJECT)
    with pytest.raises(UnsupportedConstructError):
        build_statix(model, "WHENREJECT::MachineWhenOnComposite")


def test_native_real_enum_projects_scalar_and_renders_declared_value(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm18"], "SM18::MachineRealEnum")
    assert any(
        f.name == "g" and f.c_type == "double" for f in program.context.fields
    )
    g_field = next(f for f in program.context.fields if f.name == "g")
    assert g_field.init == "4.0"  # GradePoints::A
    assert program.guards[0].expr == "ctx->g >= 3.0"  # GradePoints::B
    assert program.enums == ()  # no CEnum for a native projection


def test_string_enum_projects_generated_enum_and_dedupes_names(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm18"], "SM18::MachineStringEnum")
    (enum,) = program.enums
    assert enum.base == "sm18_machine_string_enum_enum_light_color"
    assert enum.literals == (
        "SM18_MACHINE_STRING_ENUM_ENUM_LIGHT_COLOR_RED",
        "SM18_MACHINE_STRING_ENUM_ENUM_LIGHT_COLOR_GREEN",
        "SM18_MACHINE_STRING_ENUM_ENUM_LIGHT_COLOR_YELLOW",
    )
    c_field = next(f for f in program.context.fields if f.name == "c")
    assert c_field.c_type == "sm18_machine_string_enum_enum_light_color_t"
    assert c_field.init == "SM18_MACHINE_STRING_ENUM_ENUM_LIGHT_COLOR_RED"
    # The effect (idle -> green) and the guard (green -> matched) both
    # reference LightColor::green; both must resolve to the SAME constant.
    effect = next(a for a in program.actions if "idle_completion" in a.name)
    assert effect.statements == (
        "ctx->c = SM18_MACHINE_STRING_ENUM_ENUM_LIGHT_COLOR_GREEN;",
    )
    assert (
        program.guards[0].expr
        == "ctx->c == SM18_MACHINE_STRING_ENUM_ENUM_LIGHT_COLOR_GREEN"
    )


def test_plain_enum_projects_generated_enum_with_ordinal_constants(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm18"], "SM18::MachinePlainEnum")
    (enum,) = program.enums
    assert enum.base == "sm18_machine_plain_enum_enum_mode"
    assert enum.literals == (
        "SM18_MACHINE_PLAIN_ENUM_ENUM_MODE_IDLE",
        "SM18_MACHINE_PLAIN_ENUM_ENUM_MODE_BUSY",
    )
    m_field = next(f for f in program.context.fields if f.name == "m")
    assert m_field.c_type == "sm18_machine_plain_enum_enum_mode_t"
    assert m_field.init == "SM18_MACHINE_PLAIN_ENUM_ENUM_MODE_IDLE"


def test_enum_valued_composite_field_resolves(sm_models: dict) -> None:
    model = load_model(_ENUMCOMPOSITE)
    program = build_statix(model, "ENUMCOMPOSITE::MachineEnumComposite")
    (enum,) = program.enums
    assert enum.base == "enumcomposite_machine_enum_composite_enum_light_color"
    (struct,) = program.context.structs
    assert struct.name == "enumcomposite_machine_enum_composite_holder_t"
    color_field = next(f for f in struct.fields if f.name == "color")
    assert (
        color_field.c_type
        == "enumcomposite_machine_enum_composite_enum_light_color_t"
    )
    box_field = next(f for f in program.context.fields if f.name == "box")
    assert box_field.init == (
        "{.color = ENUMCOMPOSITE_MACHINE_ENUM_COMPOSITE_ENUM_LIGHT_COLOR_RED}"
    )
    assert program.guards[0].expr == (
        "ctx->box.color == "
        "ENUMCOMPOSITE_MACHINE_ENUM_COMPOSITE_ENUM_LIGHT_COLOR_RED"
    )


def test_structured_enum_is_rejected() -> None:
    model = load_model(_ENUMREJECT)
    with pytest.raises(UnsupportedConstructError, match="structured"):
        build_statix(model, "ENUMREJECT::MachineStructuredEnum")


def test_mixed_declared_value_kinds_is_rejected() -> None:
    model = load_model(_ENUMREJECT)
    with pytest.raises(UnsupportedConstructError, match="mix"):
        build_statix(model, "ENUMREJECT::MachineMixedKindEnum")


def test_computed_declared_value_is_rejected() -> None:
    model = load_model(_ENUMREJECT)
    with pytest.raises(UnsupportedConstructError, match="bare"):
        build_statix(model, "ENUMREJECT::MachineComputedDefaultEnum")


def test_colliding_sanitized_enum_names_is_rejected() -> None:
    model = load_model(_ENUMREJECT)
    with pytest.raises(UnsupportedConstructError, match="sanitiz"):
        build_statix(model, "ENUMREJECT::MachineCollidingEnumNames")


def test_relational_literal_comparison_against_generated_enum_is_rejected() -> (
    None
):
    model = load_model(_ENUMREJECT)
    with pytest.raises(UnsupportedConstructError, match="relational"):
        build_statix(model, "ENUMREJECT::MachineRelationalLiteral")


def test_relational_attribute_to_attribute_generated_enum_is_rejected() -> None:
    model = load_model(_ENUMREJECT)
    with pytest.raises(UnsupportedConstructError, match="relational"):
        build_statix(model, "ENUMREJECT::MachineRelationalAttributes")


def test_single_shape_per_event_is_not_rejected() -> None:
    from sysmlc.backends.statix.builder import _validate_payload_shapes

    result = _validate_payload_shapes(
        {"Measurement": {("value",)}, "Reading": {()}}
    )
    assert result == {"Measurement": ("value",), "Reading": ()}


def test_whole_vs_subfeature_shape_conflict_rejected() -> None:
    from sysmlc.backends.statix.builder import _validate_payload_shapes

    with pytest.raises(UnsupportedConstructError, match="Measurement"):
        _validate_payload_shapes({"Measurement": {(), ("value",)}})


def test_two_different_subfeature_paths_rejected() -> None:
    from sysmlc.backends.statix.builder import _validate_payload_shapes

    with pytest.raises(
        UnsupportedConstructError,
        match=r"\.sample\.value.*\.value|\.value.*\.sample\.value",
    ):
        _validate_payload_shapes(
            {"Measurement": {("value",), ("sample", "value")}}
        )


def test_shape_diagnostic_is_deterministically_ordered() -> None:
    from sysmlc.backends.statix.builder import _validate_payload_shapes

    with pytest.raises(UnsupportedConstructError) as exc_info:
        _validate_payload_shapes(
            {"Measurement": {("value",), ("sample", "value")}}
        )
    # Sorted by canonical display text: ".sample.value" < ".value"
    # lexicographically, so it must appear first regardless of Python set
    # iteration order (which is not insertion-ordered for tuples of strings).
    message = str(exc_info.value)
    assert message.index(".sample.value") < message.index("'.value'")


def test_same_event_read_the_same_way_twice_is_not_rejected(
    sm_models: dict,
) -> None:
    # End-to-end sanity check that the new validation path doesn't disturb
    # an ordinary, already-passing single-shape model.
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadEffect"
    )
    assert program is not None


def test_empty_shape_set_is_skipped_not_crashed() -> None:
    from sysmlc.backends.statix.builder import _validate_payload_shapes

    # An event with an empty shape set (defensive case -- the real caller,
    # _detect_payload_reads, is fixed in Step 3 to never insert one) must be
    # skipped, not crash trying to unpack a 1-tuple from zero elements.
    result = _validate_payload_shapes({"Unread": set()})
    assert result == {}


def test_named_but_unreferenced_payload_is_dropped_not_marshalled(
    sm_models: dict,
) -> None:
    # A transition accepts a NAMED payload (`reading : Measurement`) but its
    # guard/effect never reference `reading` at all -- this must build
    # cleanly and the event must simply be treated as unread (an id-only
    # send elsewhere in the same machine, exactly as an entirely payload-
    # less event would be), not crash _detect_payload_reads/
    # _validate_payload_shapes on an empty shape set. See Step 0 below for
    # the model addition this exercises.
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadUnused"
    )
    assert "Measurement" not in program.events or all(
        s.value_expr is None and not getattr(s, "payload_lines", ())
        for a in program.actions
        for s in a.statements
        if isinstance(s, CSend) and s.event == "Measurement"
    )


def test_inconsistent_shapes_rejected_through_the_real_pipeline(
    sm_models: dict,
) -> None:
    # Unlike the pure _validate_payload_shapes tests above, this exercises
    # _detect_payload_reads itself end to end -- proving it actually
    # collects shapes from every transition (not just one), through the
    # real driver/SignalTrigger/payload_feature machinery.
    with pytest.raises(UnsupportedConstructError, match="Measurement"):
        build_statix(
            sm_models["sm11"],
            "SM11::MachineReadablePayloadInconsistentShapes",
        )


def test_whole_payload_materializes_omitted_attribute_defaults(
    sm_models: dict,
) -> None:
    # send new Measurement(current) binds only `value`; `sample` is
    # omitted (KerML permits fewer constructor args than attributes) and
    # must be materialized from Sample's own default (0.75).
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
    )
    effect = next(a for a in program.actions if "idle" in a.name)
    send = next(s for s in effect.statements if isinstance(s, CSend))
    assert send.value_expr is None
    joined = "\n".join(send.payload_lines)
    assert "sc__value" in joined
    assert ".value = ctx->current" in joined
    assert "0.75" in joined
    assert "sc_runtime_enqueue_payload" in joined


def test_whole_payload_read_reconstructs_nested_literal(
    sm_models: dict,
) -> None:
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
    )
    effect = next(a for a in program.actions if "armed" in a.name)
    (stmt,) = effect.statements
    assert "sc_event_payload_read" in stmt
    assert "payload_status" in stmt
    assert "return payload_status" in stmt
    assert "sc__payload[0]" in stmt
    assert "sc__payload[1]" in stmt
    assert "sample" in stmt and "sc__payload[1]" in stmt
