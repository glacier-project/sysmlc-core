"""Tests for the generated runner's --help output and CLI grammar.

See docs/superpowers/plans/2026-07-16-statix-runner-help.md.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.builder import build_statix

if TYPE_CHECKING:
    from pathlib import Path

    from sysmlc.backends.statix.program import CProgram

pytestmark = pytest.mark.statix


def _build_and_compile(
    sm_models: dict, tmp_path: Path, stem: str, qn: str
) -> tuple[CProgram, Path]:
    program = build_statix(sm_models[stem], qn)
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    build = tmp_path / "build"
    subprocess.run(
        ["cmake", "-S", str(tmp_path), "-B", str(build)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["cmake", "--build", str(build)], check=True, capture_output=True
    )
    return program, build


def test_help_does_not_initialize_the_machine(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "sm13", "SM13::MachineAfterSeconds"
    )
    result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "init status=" not in result.stdout
    assert "  trace:" not in result.stdout


def test_help_via_short_flag_matches_long_flag(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "sm13", "SM13::MachineAfterSeconds"
    )
    short = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "-h"],
        capture_output=True,
        text=True,
        check=True,
    )
    long = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert short.stdout == long.stdout


def test_help_lists_machine_name_states_events_transitions(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "sm13", "SM13::MachineAfterSeconds"
    )
    result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert program.qualified_name in result.stdout
    assert program.initial in result.stdout
    for s in program.states:
        assert s.name in result.stdout
    for e in program.events:
        assert e in result.stdout
    for t in program.transitions:
        assert t.source in result.stdout
        assert t.target in result.stdout
    assert "SC_TICKS_PER_SECOND=" in result.stdout
    assert "Example" in result.stdout
    assert "TRACE_MASK" in result.stdout


def test_help_shows_parallel_region_info_when_applicable(
    sm_models_showcase: dict, tmp_path: Path
) -> None:
    program = build_statix(
        sm_models_showcase["microwave"], "Microwave::MicrowaveBehavior"
    )
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    build = tmp_path / "build"
    subprocess.run(
        ["cmake", "-S", str(tmp_path), "-B", str(build)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["cmake", "--build", str(build)], check=True, capture_output=True
    )
    result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Parallel regions:" in result.stdout
    assert f"active_capacity={program.active_capacity}" in result.stdout


def test_untimed_machine_help_omits_tick_advance(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "sm01", "SM01::Machine"
    )
    result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--tick" not in result.stdout
    assert "--advance" not in result.stdout


def test_events_and_ticks_interleave_correctly(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "sm13", "SM13::MachineAfterReentry"
    )
    result = subprocess.run(
        [
            str(build / f"{program.prefix}_runner"),
            "--tick",
            "2000",
            "Leave",
            "--tick",
            "3000",
            "Back",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.lstrip().startswith("trace:")
    ]
    kinds = [line.split(" ", 1)[0] for line in lines]
    assert kinds == ["init", "tick", "event", "tick", "event"]


def test_advance_zero_produces_no_step_output(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "sm13", "SM13::MachineAfterSeconds"
    )
    result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--advance", "0"],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.lstrip().startswith("trace:")
    ]
    assert len(lines) == 1
    assert lines[0].startswith("init ")
