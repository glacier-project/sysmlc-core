"""Structural + compile-level tests for the SC_MACHINE_TRACE generator output.

See docs/superpowers/specs/2026-07-16-statix-trace-hook-design.md.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.serialize import emit_source

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def test_mask_setup_emitted_for_every_machine(sm_models: dict) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    source = emit_source(program)
    prefix_upper = program.prefix.upper()
    assert f"#ifndef {prefix_upper}_TRACE_MASK" in source
    assert f"#define {prefix_upper}_TRACE_MASK SC_TRACE_MASK_ALL" in source
    assert (
        f"#if (({prefix_upper}_TRACE_MASK) & ~(SC_TRACE_MASK_ALL)) != 0u"
        in source
    )
    assert (
        f'#error "{prefix_upper}_TRACE_MASK contains unsupported bits"'
        in source
    )
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
        f"#define {prefix_upper}_TRACE_AVAILABLE_MASK SC_TRACE_MASK_ALL"
        in source
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


_MASK_BITS = {
    "SC_TRACE_MASK_ENTER": 1 << 0,
    "SC_TRACE_MASK_EXIT": 1 << 1,
    "SC_TRACE_MASK_TRANSITION": 1 << 2,
    "SC_TRACE_MASK_GUARD": 1 << 3,
    "SC_TRACE_MASK_TIMER_CHECK": 1 << 4,
}
_MASK_ALL = (1 << 5) - 1


def _write_and_configure(
    sm_models: dict, tmp_path: Path, stem: str, qn: str, mask_value: int
) -> tuple[str, Path]:
    program = build_statix(sm_models[stem], qn)
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    build = tmp_path / "build"
    define = f"-D{program.prefix.upper()}_TRACE_MASK={mask_value}u"
    subprocess.run(
        [
            "cmake",
            "-S",
            str(tmp_path),
            "-B",
            str(build),
            f"-DCMAKE_C_FLAGS={define}",
        ],
        check=True,
        capture_output=True,
    )
    return program.prefix, build


def _build_with_mask(build: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "cmake",
            "--build",
            str(build),
            "--target",
            "statix_statecharts",
        ],
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("mask_value", [0, *_MASK_BITS.values(), _MASK_ALL])
def test_single_bit_masks_compile_clean(
    sm_models: dict, tmp_path: Path, mask_value: int
) -> None:
    _prefix, build = _write_and_configure(
        sm_models, tmp_path, "sm13", "SM13::MachineAfterGuard", mask_value
    )
    result = _build_with_mask(build)
    assert result.returncode == 0, result.stdout + result.stderr


def test_timer_check_only_on_untimed_machine_compiles_clean(
    sm_models: dict, tmp_path: Path
) -> None:
    _prefix, build = _write_and_configure(
        sm_models,
        tmp_path,
        "sm03",
        "SM03::MachineRef",
        _MASK_BITS["SC_TRACE_MASK_TIMER_CHECK"],
    )
    result = _build_with_mask(build)
    assert result.returncode == 0, result.stdout + result.stderr


def test_unsupported_mask_bit_fails_with_intended_error(
    sm_models: dict, tmp_path: Path
) -> None:
    _prefix, build = _write_and_configure(
        sm_models, tmp_path, "sm13", "SM13::MachineAfterGuard", 1 << 10
    )
    result = _build_with_mask(build)
    assert result.returncode != 0
    assert "contains unsupported bits" in (result.stdout + result.stderr)


def test_generated_runner_emits_trace_before_summary_line(
    sm_models_showcase: dict, tmp_path: Path
) -> None:
    prefix, build = _write_and_configure(
        sm_models_showcase,
        tmp_path,
        "microwave",
        "Microwave::MicrowaveBehavior",
        _MASK_ALL,
    )
    subprocess.run(
        ["cmake", "--build", str(build)], check=True, capture_output=True
    )
    result = subprocess.run(
        [str(build / f"{prefix}_runner"), "StartCmd"],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = result.stdout.strip().splitlines()
    assert len(lines) > 2, (
        "expected trace lines between init and the StartCmd summary"
    )
    # The final line remains the ordinary summary line -- unaffected by tracing.
    assert lines[-1].startswith("event StartCmd status=")
    assert "state=" in lines[-1]
    # Every "  trace: " line for the StartCmd command appears before that
    # command's own summary line, never after.
    start_cmd_index = next(
        i for i, line in enumerate(lines) if line.startswith("event StartCmd")
    )
    for line in lines[start_cmd_index + 1 :]:
        assert not line.startswith("  trace:")
    assert any(line.startswith("  trace: enter") for line in lines)
    assert any(line.startswith("  trace: transition") for line in lines)


def test_existing_statix_run_fixtures_unaffected_by_tracing(
    sm_models: dict,
    statix_run: Callable,
    statix_run_final: Callable,
    statix_run_status: Callable,
    statix_run_configuration: Callable,
) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    assert statix_run(program) is not None
    assert statix_run_final(program) is not None
    assert statix_run_status(program) is not None
    assert statix_run_configuration(program) is not None


def test_zero_mask_override_restores_terse_output(
    sm_models_showcase: dict, tmp_path: Path
) -> None:
    _prefix, build = _write_and_configure(
        sm_models_showcase,
        tmp_path,
        "microwave",
        "Microwave::MicrowaveBehavior",
        0,
    )
    result = _build_with_mask(build)
    assert result.returncode == 0, result.stdout + result.stderr
