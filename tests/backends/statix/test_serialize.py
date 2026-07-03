from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.serialize import emit_files


def test_ids_header_lists_states(sm_models):
    files = emit_files(build_statix(sm_models["sm01"], "SM01::Machine"))
    ids = files["machine_statechart_ids.h"]
    assert "MACHINE_STATE_IDLE = 0" in ids
    assert "MACHINE_STATE_RUNNING = 1" in ids
    assert "#define MACHINE_STATE_COUNT 2u" in ids


def test_config_has_states_table_and_completion_rows(sm_models):
    files = emit_files(build_statix(sm_models["sm01"], "SM01::Machine"))
    config = files["machine_statechart_config.c"]
    assert "sc_state_def_t machine_states[]" in config
    assert "SC_EVENT_COMPLETION" in config
    assert "machine_states," in config


def test_generated_guard_body(sm_models):
    files = emit_files(build_statix(sm_models["sm03"], "SM03::MachineRef"))
    actions_c = files["machineref_actions.c"]
    assert "sc_guard_eval" in actions_c
    assert "return ctx->enabled;" in actions_c


def test_generated_action_body(sm_models):
    files = emit_files(
        build_statix(sm_models["sm04"], "SM04::MachineEntryIncrement")
    )
    actions_c = files["machineentryincrement_actions.c"]
    assert "ctx->counter = ctx->counter + 1;" in actions_c
    assert "return SC_STATUS_OK;" in actions_c


def test_context_struct(sm_models):
    files = emit_files(
        build_statix(sm_models["sm04"], "SM04::MachineEntryIncrement")
    )
    ctx_h = files["machineentryincrement_context.h"]
    assert "int32_t counter;" in ctx_h


def test_deterministic(sm_models):
    a = emit_files(build_statix(sm_models["sm01"], "SM01::Machine"))
    b = emit_files(build_statix(sm_models["sm01"], "SM01::Machine"))
    assert a == b
