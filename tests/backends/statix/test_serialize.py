import syside

from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.serialize import _paths, emit_files


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
        "SM08_MACHINE_NESTED_STATE_RUNNING_WARMING, false}," in config
    )
    # warming is a leaf under running.
    assert (
        "{SC_ACTION_NONE, SC_ACTION_NONE, SM08_MACHINE_NESTED_STATE_RUNNING, "
        "SC_STATE_INVALID, false}," in config
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
        "SC_STATE_INVALID, true}," in config
    )
    # Normal leaves stay is_final = false.
    assert (
        "{SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, "
        "SC_STATE_INVALID, false}," in config
    )
    assert "bool sm10_machine_root_done_is_final(" in header


def test_nested_final_row_scoped(sm_models: dict) -> None:
    files, d, s = _files_for(sm_models["sm10"], "SM10::MachineNestedDone")
    config = files[f"src/{d}/{s}.c"]
    # running::done sits under running and is final.
    assert (
        "SM10_MACHINE_NESTED_DONE_STATE_RUNNING, SC_STATE_INVALID, true},"
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
