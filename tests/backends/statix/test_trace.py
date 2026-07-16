"""Structural + compile-level tests for the SC_MACHINE_TRACE generator output.

See docs/superpowers/specs/2026-07-16-statix-trace-hook-design.md.
"""

from __future__ import annotations

from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.serialize import emit_source


def test_mask_setup_emitted_for_every_machine(sm_models: dict) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    source = emit_source(program)
    prefix_upper = program.prefix.upper()
    assert f"#ifndef {prefix_upper}_TRACE_MASK" in source
    assert f"#define {prefix_upper}_TRACE_MASK SC_TRACE_MASK_ALL" in source
    assert (
        f"#if (({prefix_upper}_TRACE_MASK) & ~(SC_TRACE_MASK_ALL)) != 0u" in source
    )
    assert f'#error "{prefix_upper}_TRACE_MASK contains unsupported bits"' in source
    assert "#define SC_MACHINE_TRACE_MASK" in source
    assert "#undef SC_MACHINE_TRACE_MASK" in source


def test_untimed_machine_excludes_timer_check_from_available_mask(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    source = emit_source(program)
    prefix_upper = program.prefix.upper()
    assert (
        f"#define {prefix_upper}_TRACE_AVAILABLE_MASK "
        "(SC_TRACE_MASK_ALL & ~SC_TRACE_MASK_TIMER_CHECK)" in source
    )


def test_timed_machine_available_mask_is_all(sm_models: dict) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterGuard")
    source = emit_source(program)
    prefix_upper = program.prefix.upper()
    assert (
        f"#define {prefix_upper}_TRACE_AVAILABLE_MASK SC_TRACE_MASK_ALL" in source
    )


def test_guard_name_generated_for_a_real_guard(sm_models: dict) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterGuard")
    source = emit_source(program)
    assert "#if (SC_MACHINE_TRACE_MASK & SC_TRACE_MASK_GUARD)" in source
    assert "static const char *guard_name(sc_guard_id_t guard)" in source
    assert len(program.guards) >= 1
    first_guard_const = f"{program.prefix.upper()}_GUARD_" + "".join(
        ch.upper() if ch.isalnum() else "_" for ch in program.guards[0].name
    )
    assert f'return "{program.guards[0].name}";' in source
    assert first_guard_const in source or program.guards[0].name in source


def test_action_name_generated_for_a_real_action(sm_models: dict) -> None:
    program = build_statix(sm_models["sm12"], "SM12::MachineDoAssign")
    source = emit_source(program)
    assert "#if (SC_MACHINE_TRACE_MASK & SC_TRACE_MASK_TRANSITION)" in source
    assert "static const char *action_name(sc_action_id_t action)" in source
    assert 'case SC_ACTION_NONE:\n        return "SC_ACTION_NONE";' in source


def test_trace_hook_generated_with_all_five_cases_by_default(
    sm_models: dict,
) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterGuard")
    source = emit_source(program)
    assert "static void trace_hook(" in source
    for kind in (
        "SC_TRACE_ENTER",
        "SC_TRACE_EXIT",
        "SC_TRACE_TRANSITION",
        "SC_TRACE_GUARD",
        "SC_TRACE_TIMER_CHECK",
    ):
        assert f"case {kind}:" in source
    assert "#define SC_MACHINE_HAS_TRACE 1" in source
    assert "#define SC_MACHINE_TRACE trace_hook" in source
