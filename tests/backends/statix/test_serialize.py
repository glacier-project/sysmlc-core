import dataclasses
from collections import namedtuple
from pathlib import Path

import syside

from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.program import (
    CAction,
    CProgram,
    CProject,
    CSend,
)
from sysmlc.backends.statix.serialize import (
    _paths,
    emit_cmakelists,
    emit_files,
    emit_header,
    emit_source,
)
from sysmlc.sysml.loading import load_model

SerializedCode = namedtuple("SerializedCode", ["header", "source"])
_ENUMCOMPOSITE = Path(__file__).resolve().parent / "fixtures" / "enumcomposite"


def serialize_statix(program: CProgram) -> SerializedCode:
    return SerializedCode(
        header=emit_header(program), source=emit_source(program)
    )


def _files_for(model: syside.Model, qn: str) -> tuple[dict[str, str], str, str]:
    program = build_statix(model, qn)
    d, s = _paths(program)
    return emit_files(program), d, s


def test_ids_header_lists_states(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm01"], "SM01::Machine")
    header = files[f"include/{d}/{s}.h"]
    assert "SM01_MACHINE_STATE_IDLE = 0" in header
    assert "SM01_MACHINE_STATE_RUNNING = 1" in header
    assert "#define SM01_MACHINE_STATE_COUNT 2u" in header
    assert "/// @brief Initialize a statechart instance" in header


def test_config_has_states_table_and_completion_rows(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm01"], "SM01::Machine")
    config = files[f"src/{d}/{s}.c"]
    assert "static const sc_state_def_t states[] = {" in config
    assert "SC_EVENT_COMPLETION" in config
    assert "    states,\n" in config  # wired into the machine_def literal


def test_generated_guard_body(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm03"], "SM03::MachineRef")
    actions_c = files[f"src/{d}/{s}.c"]
    assert "static bool guard_eval(sc_guard_id_t guard_id" in actions_c
    assert "return ctx->enabled;" in actions_c


def test_generated_action_body(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm04"], "SM04::MachineEntryIncrement")
    actions_c = files[f"src/{d}/{s}.c"]
    assert "ctx->counter = ctx->counter + 1;" in actions_c
    assert "return SC_STATUS_OK;" in actions_c


def test_context_struct(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm04"], "SM04::MachineEntryIncrement")
    ctx_h = files[f"include/{d}/{s}.h"]
    assert "int32_t counter;" in ctx_h


def test_deterministic(sm_models: dict) -> None:
    a = emit_files(build_statix(sm_models["sm01"], "SM01::Machine"))
    b = emit_files(build_statix(sm_models["sm01"], "SM01::Machine"))
    assert a == b


def test_composite_state_rows_and_max_depth(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm08"], "SM08::MachineNested")
    config = files[f"src/{d}/{s}.c"]
    # running is composite: descends into warming; top-level so parent INVALID.
    assert (
        "{SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, "
        "SM08_MACHINE_NESTED_STATE_RUNNING_WARMING, false, (sc_state_id_t)0u, SC_STATE_INVALID, (sc_state_id_t)0u},"
        in config
    )
    # warming is a leaf under running.
    assert (
        "{SC_ACTION_NONE, SC_ACTION_NONE, SM08_MACHINE_NESTED_STATE_RUNNING, "
        "SC_STATE_INVALID, false, (sc_state_id_t)0u, SC_STATE_INVALID, (sc_state_id_t)0u},"
        in config
    )
    # Depth of running::warming is 2.
    assert "(sc_state_id_t)2u," in config


def test_composite_state_name_is_dotted(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm08"], "SM08::MachineNested")
    config = files[f"src/{d}/{s}.c"]
    # The display name returned by state_name matches Sismic's dotted path.
    assert 'return "running::warming";' in config


def test_final_state_row_and_prototype(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm10"], "SM10::MachineRootDone")
    config = files[f"src/{d}/{s}.c"]
    header = files[f"include/{d}/{s}.h"]
    # The synthesized `done` row is top-level absorbing: is_final = true.
    assert (
        "{SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, "
        "SC_STATE_INVALID, true, (sc_state_id_t)0u, SC_STATE_INVALID, (sc_state_id_t)0u},"
        in config
    )
    # Normal leaves stay is_final = false.
    assert (
        "{SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, "
        "SC_STATE_INVALID, false, (sc_state_id_t)0u, SC_STATE_INVALID, (sc_state_id_t)0u},"
        in config
    )
    assert "bool sm10_machine_root_done_is_final(" in header


def test_nested_final_row_scoped(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm10"], "SM10::MachineNestedDone")
    config = files[f"src/{d}/{s}.c"]
    # running::done sits under running and is final.
    assert (
        "SM10_MACHINE_NESTED_DONE_STATE_RUNNING, SC_STATE_INVALID, true, (sc_state_id_t)0u, SC_STATE_INVALID, (sc_state_id_t)0u},"
        in config
    )
    assert 'return "running::done";' in config


def test_entry_then_do_emits_both_statements_in_order(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm12"], "SM12::MachineEntryThenDo")
    config = files[f"src/{d}/{s}.c"]
    # The working entry action runs the entry assign, then the do assign.
    entry_idx = config.index("ctx->log = 1;")
    do_idx = config.index("ctx->log = ctx->log + 10;")
    assert entry_idx < do_idx, "entry statement must precede the do statement"


def test_cmakelists_is_byte_stable(sm_models: dict) -> None:
    # Characterization: pins the exact CMakeLists bytes for a single-program
    # project so the Jinja migration cannot drift them.
    program = build_statix(sm_models["sm04"], "SM04::MachineEntryIncrement")
    project = CProject(programs=(program,))
    expected = (
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(statix_statecharts C)\n\n"
        "set(CMAKE_C_STANDARD 99)\n"
        "set(CMAKE_C_STANDARD_REQUIRED ON)\n\n"
        "add_compile_options(-Wall -Wextra -Wpedantic -Wconversion"
        " -Wsign-conversion -Wdouble-promotion -Werror)\n\n"
        "include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)\n\n"
        "add_library(statix_statecharts STATIC\n"
        "  src/sc_runtime_impl.c\n"
        "  src/sm04/machine_entry_increment.c)\n\n"
        "add_executable(sm04_machine_entry_increment_runner"
        " host/sm04/machine_entry_increment_runner.c)\n"
        "target_link_libraries(sm04_machine_entry_increment_runner"
        " statix_statecharts)\n"
    )
    assert emit_cmakelists(project) == expected


def test_serializer_emits_queue_and_send(sm_models: dict) -> None:
    program = build_statix(sm_models["sm11"], "SM11::MachineSelfSend")
    code = serialize_statix(program)
    # Header: queue storage and SC_MACHINE_HAS_QUEUE define.
    assert "sc_event_queue_t queue;" in code.header
    assert "sc_event_t queue_storage[8];" in code.header
    # Source: SC_MACHINE_HAS_QUEUE set before template include.
    assert "#define SC_MACHINE_HAS_QUEUE 1" in code.source
    assert '#include "sc/sc_machine.h"' in code.source
    # The action body calls sc_runtime_enqueue with the generated event id.
    assert (
        "sc_runtime_enqueue(\n"
        "                runtime, "
        "(sc_event_id_t)SM11_MACHINE_SELF_SEND_EVENT_PING);" in code.source
    )
    assert "return send_status;" in code.source
    assert "sc_event_queue.h" in code.header


def test_serializer_no_send_omits_queue(sm_models: dict) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    code = serialize_statix(program)
    assert "sc_event_queue_t" not in code.header
    assert "SC_MACHINE_HAS_QUEUE" not in code.source
    assert "sc_event_queue.h" not in code.header


def test_send_block_preserves_statement_order(sm_models: dict) -> None:
    # A statement AFTER a send must still execute: the send renders as a
    # scoped status-check block, never as a bare `return`.
    program = build_statix(sm_models["sm11"], "SM11::MachineMixed")
    synthetic = dataclasses.replace(
        program,
        actions=(
            CAction(
                name="probe",
                statements=(CSend(event="Ping"), "ctx->count = 1;"),
            ),
        ),
    )
    source = emit_source(synthetic)
    send_at = source.index("sc_runtime_enqueue")
    assign_at = source.index("ctx->count = 1;")
    assert send_at < assign_at
    between = source[send_at:assign_at]
    # The enqueue's status check returns only on error; the success path
    # must fall through to the next statement.
    assert "return send_status;" in between
    assert "return SC_STATUS_OK;" not in between


def test_marshalled_send_renders_enqueue_payload(sm_models: dict) -> None:
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadGuard"
    )
    source = emit_source(program)
    assert "sc__value.value = ctx->current;" in source
    assert "sc_runtime_enqueue_payload(" in source
    assert "&sc__value, sizeof(sc__value));" in source
    assert "return send_status;" in source


def test_payload_only_guard_omits_unused_ctx(sm_models: dict) -> None:
    # MachineReadablePayloadGuard's only guard reads the payload: guard_eval
    # must not declare an unused ctx (fatal under the project's -Werror).
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadGuard"
    )
    source = emit_source(program)
    body = source[source.index("static bool guard_eval") :]
    body = body[: body.index("}")]
    assert "context_t *ctx" not in body
    assert "(void)runtime;" in body


def test_ctx_using_guards_keep_the_cast(sm_models: dict) -> None:
    program = build_statix(sm_models["sm03"], "SM03::MachineRef")
    source = emit_source(program)
    body = source[source.index("static bool guard_eval") :]
    assert "const sm03_machine_ref_context_t *ctx" in body


def test_timeout_due_emits_literal_case(sm_models: dict) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterSeconds")
    source = emit_source(program)
    assert "#define SC_MACHINE_HAS_TIMER 1" in source
    assert "#define SC_MACHINE_TIMEOUT_DUE timeout_due" in source
    assert (
        "static bool timeout_due(sc_state_id_t state, const sc_runtime_t "
        "*runtime, sc_state_id_t activation_index)" in source
    )
    assert (
        "return (runtime->now - runtime->active[activation_index].entered_at) >= "
        "(5u * SC_TICKS_PER_SECOND);" in source
    )


def test_timeout_due_omits_unused_ctx_when_all_literal(sm_models: dict) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterSeconds")
    source = emit_source(program)
    body = source[source.index("static bool timeout_due") :]
    body = body[: body.index("\n}\n")]
    assert "context_t *ctx" not in body


def test_timeout_due_keeps_ctx_cast_when_attribute_driven(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAt")
    source = emit_source(program)
    body = source[source.index("static bool timeout_due") :]
    assert "const sm13_machine_at_context_t *ctx" in body
    assert "sc_seconds_to_ticks(ctx->deadlineTime, &deadline)" in body
    assert (
        "(runtime->active[activation_index].entered_at <= deadline) && "
        "(runtime->now >= deadline)" in body
    )


def test_no_timer_machine_omits_timer_macros(sm_models: dict) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    source = emit_source(program)
    assert "SC_MACHINE_HAS_TIMER" not in source
    assert "timeout_due" not in source


def test_header_declares_tick_only_when_has_timer(sm_models: dict) -> None:
    timed = emit_header(
        build_statix(sm_models["sm13"], "SM13::MachineAfterSeconds")
    )
    assert (
        "sc_status_t sm13_machine_after_seconds_tick"
        "(sm13_machine_after_seconds_t *sm, sc_time_t now);" in timed
    )
    plain = emit_header(build_statix(sm_models["sm01"], "SM01::Machine"))
    assert "_tick(" not in plain


def test_when_emits_has_when_macro_and_settle_decl(sm_models: dict) -> None:
    program = build_statix(sm_models["sm16"], "SM16::MachineWhenBare")
    source = emit_source(program)
    header = emit_header(program)
    assert "#define SC_MACHINE_HAS_WHEN 1" in source
    assert "#if SC_MAX_WHEN_TRIGGERS < 1u" in source
    assert (
        "sc_status_t sm16_machine_when_bare_settle"
        "(sm16_machine_when_bare_t *sm);" in header
    )


def test_no_when_machine_omits_has_when_and_settle_decl(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    source = emit_source(program)
    header = emit_header(program)
    assert "SC_MACHINE_HAS_WHEN" not in source
    assert "_settle(" not in header


def test_internal_target_emits_sc_state_invalid_in_table(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm16"], "SM16::MachineWhenGuard")
    source = emit_source(program)
    assert ", SC_STATE_INVALID}," in source


def test_generated_enum_typedef_precedes_structs_and_context(
    sm_models: dict,
) -> None:
    model = load_model(_ENUMCOMPOSITE)
    program = build_statix(model, "ENUMCOMPOSITE::MachineEnumComposite")
    files, d, s = _files_for(model, "ENUMCOMPOSITE::MachineEnumComposite")
    header = files[f"include/{d}/{s}.h"]
    enum_idx = header.index(
        "enumcomposite_machine_enum_composite_enum_light_color_e"
    )
    struct_idx = header.index("enumcomposite_machine_enum_composite_holder_t")
    context_idx = header.index("enumcomposite_machine_enum_composite_context_s")
    assert enum_idx < struct_idx < context_idx
    assert program.enums  # sanity: the model actually produced one


def test_generated_enum_typedef_naming(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm18"], "SM18::MachinePlainEnum")
    header = files[f"include/{d}/{s}.h"]
    assert "typedef enum sm18_machine_plain_enum_enum_mode_e {" in header
    assert "SM18_MACHINE_PLAIN_ENUM_ENUM_MODE_IDLE = 0" in header
    assert "SM18_MACHINE_PLAIN_ENUM_ENUM_MODE_BUSY = 1" in header
    assert "} sm18_machine_plain_enum_enum_mode_t;" in header


def test_no_enum_usage_emits_no_generated_enum_block(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm01"], "SM01::Machine")
    header = files[f"include/{d}/{s}.h"]
    assert "_enum_" not in header


def test_active_capacity_macro_and_activation_array(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm09"], "SM09::MachineParallel")
    header = files[f"include/{d}/{s}.h"]
    assert "#define SM09_MACHINE_PARALLEL_ACTIVE_CAPACITY 2u" in header
    assert (
        "sc_activation_t active[SM09_MACHINE_PARALLEL_ACTIVE_CAPACITY];"
        in header
    )


def test_regions_table_and_machine_def_fields(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm09"], "SM09::MachineParallel")
    config = files[f"src/{d}/{s}.c"]
    assert "static const sc_state_id_t regions[] = {" in config
    assert (
        "#define SC_MACHINE_ACTIVE_CAPACITY SM09_MACHINE_PARALLEL_ACTIVE_CAPACITY"
        in config
    )


def test_state_rows_carry_slot_and_region_columns(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm09"], "SM09::MachineNestedParallel")
    config = files[f"src/{d}/{s}.c"]
    # `dual`'s row must reference its own region_first/region_count, not the
    # sentinel.
    assert "(sc_state_id_t)0u, (sc_state_id_t)2u}" in config


def test_example_command_prefers_reachable_transition(sm_models: dict) -> None:
    program = build_statix(sm_models["sm02"], "SM02::Machine")
    from sysmlc.backends.statix.serialize import _example_command

    example = _example_command(program)
    assert example["kind"] == "reachable"
    assert example["event"] == "Tick"


def test_example_command_falls_back_to_timed(sm_models: dict) -> None:
    from sysmlc.backends.statix.serialize import _example_command

    program = build_statix(sm_models["sm13"], "SM13::MachineAfterReentry")
    example = _example_command(program)
    # MachineAfterReentry's initial state ("idle") has both an externally
    # triggered transition (Leave) and a timer -- "reachable" must win.
    assert example["kind"] == "reachable"


def test_example_command_none_when_no_events_or_timer(sm_models: dict) -> None:
    from sysmlc.backends.statix.serialize import _example_command

    program = build_statix(sm_models["sm08"], "SM08::MachineNested")
    example = _example_command(program)
    assert example["kind"] in ("none", "syntax_only")


def test_no_whole_payload_types_emits_no_size_override(sm_models: dict) -> None:
    from sysmlc.backends.statix.program import CProject
    from sysmlc.backends.statix.serialize import emit_cmakelists

    program = build_statix(sm_models["sm01"], "SM01::Machine")
    text = emit_cmakelists(CProject(programs=(program,)))
    assert "SC_EVENT_PAYLOAD_SIZE" not in text


def test_whole_payload_type_emits_computed_size(sm_models: dict) -> None:
    from sysmlc.backends.statix.program import CProject
    from sysmlc.backends.statix.serialize import emit_cmakelists

    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
    )
    text = emit_cmakelists(CProject(programs=(program,)))
    assert 'set(STATIX_EVENT_PAYLOAD_SIZE "16" CACHE STRING' in text
    assert "SC_EVENT_PAYLOAD_SIZE=${STATIX_EVENT_PAYLOAD_SIZE}u" in text


def test_multiple_programs_max_size_wins_not_sum(sm_models: dict) -> None:
    # Two programs in one project, each with its own distinct whole-payload
    # struct type of a different size -- the emitted size must be the
    # MAXIMUM across the whole project, not the sum of both (the buffer is
    # one shared sc_event_t.payload array reused across every queued event,
    # not one slot per program).
    from dataclasses import replace

    from sysmlc.backends.statix.program import CField, CProject, CStruct
    from sysmlc.backends.statix.serialize import emit_cmakelists

    small_program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
    )  # 2 leaves -> 16 bytes
    # Synthesize a second program reusing small_program's own shape but with
    # an additional 4-leaf struct registered as its own whole-payload type
    # -- 4 leaves total -> 32 bytes, the max.
    big_struct = CStruct(
        name="synthetic_big_t",
        fields=(
            CField("a", "double", ""),
            CField("b", "double", ""),
            CField("c", "double", ""),
            CField("d", "double", ""),
        ),
    )
    big_program = replace(
        small_program,
        prefix="synthetic_big",
        context=replace(
            small_program.context,
            structs=(*small_program.context.structs, big_struct),
        ),
        payload_struct_types=("synthetic_big_t",),
    )
    text = emit_cmakelists(CProject(programs=(small_program, big_program)))
    assert 'set(STATIX_EVENT_PAYLOAD_SIZE "32" CACHE STRING' in text
    assert 'set(STATIX_EVENT_PAYLOAD_SIZE "16" CACHE STRING' not in text
    assert 'set(STATIX_EVENT_PAYLOAD_SIZE "48" CACHE STRING' not in text
    assert "SC_EVENT_PAYLOAD_SIZE=${STATIX_EVENT_PAYLOAD_SIZE}u" in text


def test_unrelated_non_double_struct_does_not_affect_sizing(
    sm_models: dict,
) -> None:
    # A struct containing a Boolean field, registered in context.structs but
    # NOT listed in payload_struct_types (an ordinary attribute struct, not
    # a whole-payload type), must never be passed to _flatten_leaf_paths --
    # proving the all-double validation is scoped to actual payload types,
    # not every registered struct in the project.
    from dataclasses import replace

    from sysmlc.backends.statix.program import CField, CProject, CStruct
    from sysmlc.backends.statix.serialize import emit_cmakelists

    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
    )
    bool_struct = CStruct(
        name="synthetic_flags_t",
        fields=(CField("enabled", "bool", ""),),
    )
    augmented = replace(
        program,
        context=replace(
            program.context, structs=(*program.context.structs, bool_struct)
        ),
        # payload_struct_types deliberately unchanged -- bool_struct is NOT
        # a whole-payload type, just an incidental extra registered struct.
    )
    text = emit_cmakelists(CProject(programs=(augmented,)))
    assert 'set(STATIX_EVENT_PAYLOAD_SIZE "16" CACHE STRING' in text  # unaffected by bool_struct


def test_subfield_only_read_sizes_the_project_too(sm_models: dict) -> None:
    # Before this task, a subfield-only read (e.g. .value) never needed the
    # struct's size registered, because it always fit the old fixed 8-byte
    # scalar slot. Now it must: the whole Measurement struct (2 leaves ->
    # 16 bytes) crosses the wire even for a single-field read.
    from sysmlc.backends.statix.program import CProject
    from sysmlc.backends.statix.serialize import emit_cmakelists

    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadGuard"
    )
    text = emit_cmakelists(CProject(programs=(program,)))
    assert 'set(STATIX_EVENT_PAYLOAD_SIZE "16" CACHE STRING' in text


def test_mixed_primitive_padding_sizes_by_leaf_count_not_byte_sum(
    sm_models: dict,
) -> None:
    from sysmlc.backends.statix.program import CProject
    from sysmlc.backends.statix.serialize import emit_cmakelists

    program = build_statix(
        sm_models["sm11"], "SM11::MachineMixedPrimitivePadding"
    )
    text = emit_cmakelists(CProject(programs=(program,)))
    # 3 leaves (armed, value, ready) x 8 bytes = 24 -- NOT 1+8+1=10 rounded
    # to 16, which is what the old "sum sizes, round once" heuristic would
    # have (wrongly) produced.
    assert 'set(STATIX_EVENT_PAYLOAD_SIZE "24" CACHE STRING' in text


def test_payload_struct_gets_a_compile_time_size_proof(sm_models: dict) -> None:
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
    )
    from sysmlc.backends.statix.serialize import emit_header
    header = emit_header(program)
    c_type = "sm11_machine_readable_payload_whole_measurement_t"
    assert (
        f"typedef char sc__payload_size_check_{c_type}"
        f"[(sizeof({c_type}) <= SC_EVENT_PAYLOAD_SIZE) ? 1 : -1];" in header
    )


def test_non_payload_struct_gets_no_size_proof(sm_models: dict) -> None:
    # A struct that is registered (e.g. an ordinary composite attribute)
    # but never listed in payload_struct_types must not get a size-check
    # typedef -- scoped to actual payload types only, same discipline as
    # the sizing computation itself.
    program = build_statix(sm_models["sm05"], "SM05::MachineChainNested")
    from sysmlc.backends.statix.serialize import emit_header
    header = emit_header(program)
    assert "sc__payload_size_check_" not in header
