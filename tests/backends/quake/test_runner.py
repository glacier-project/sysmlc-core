from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

from sysmlc.backends.quake.coordinator import StopReason
from sysmlc.backends.quake.runner import run_part_system, run_state_def
from sysmlc.errors import ExecutionError
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model

if TYPE_CHECKING:
    from pathlib import Path

FIX = SM_EXAMPLES_DIR / "part01-two-parts"
MUX = SM_EXAMPLES_DIR / "part-mux"
RAMP = SM_EXAMPLES_DIR / "sm15-external"
PART_EXTERNAL = SM_EXAMPLES_DIR / "part-external"

TIMED_MODEL = """
package RunTimed {
    private import SI::*;

    state def Machine {
        entry; then idle;
        state idle;
        transition first idle accept after 0.1 [s] then done;
    }
}
"""

FLAT_MODEL = """
package RunFlat {
    state def Machine {
        entry; then idle;
        state idle;
        transition first idle then done;
    }
}
"""

LOOP_MODEL = """
package RunLoop {
    private import SI::*;

    state def Machine {
        entry; then running;
        state running;
        transition running accept after 1 [s] then running;
    }
}
"""


def test_run_part_system_drains_pingsystem() -> None:
    report = run_part_system(load_model(FIX), "Part01::pingSystem")

    # tb pings, plant pongs back and returns to idle; tb reaches its final
    # state (so its configuration is empty), the plant idles on forever.
    assert report.clock_time == 0.1
    assert report.configurations["plant"] == ["PlantBehavior", "idle"]
    assert report.all_final is False
    events = {
        step.step.event.name
        for step in report.trace
        if step.step.event is not None
    }
    assert {"Ping", "Pong"} <= events


def test_run_state_def_advances_clock_for_a_timer(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, TIMED_MODEL)

    report = run_state_def(model, "RunTimed::Machine")

    assert report.clock_time == 0.1
    assert report.all_final is True


def test_run_state_def_settles_at_zero_without_a_timer(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, FLAT_MODEL)

    report = run_state_def(model, "RunFlat::Machine")

    assert report.clock_time == 0.0
    assert report.all_final is True


def test_render_distinguishes_never_started_from_final() -> None:
    # With a one-step budget on a three-part system, at least one machine
    # is starved before its first step; an uninitialized interpreter has
    # an empty configuration, which must not read as terminated.
    report = run_part_system(load_model(MUX), "PartMux::mux", max_steps=1)

    rendered = report.render()
    assert "(never ran)" in rendered
    assert "(final)" not in rendered


def test_render_marks_final_machines() -> None:
    report = run_part_system(load_model(FIX), "Part01::pingSystem")

    assert "tb: (final)" in report.render()


def test_run_part_system_keeps_trace_at_step_cap() -> None:
    report = run_part_system(load_model(FIX), "Part01::pingSystem", max_steps=1)

    assert report.hit_step_cap is True
    # The trace up to the cap is preserved, and the cap is exact: no
    # extra macro step runs beyond it.
    assert len(report.trace) == 1


def test_run_state_def_stops_at_time_bound(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, LOOP_MODEL)

    report = run_state_def(model, "RunLoop::Machine", until=3)

    assert report.stop_reason is StopReason.TIME_BOUND
    assert report.clock_time == 3.0
    assert report.all_final is False


def test_run_state_def_advances_clock_to_the_time_bound(
    tmp_path: Path,
) -> None:
    # The bound falls between the ticks at 2 and 3: nothing runs there,
    # but the clock still reports the full simulated span.
    model = _load_inline_model(tmp_path, LOOP_MODEL)

    report = run_state_def(model, "RunLoop::Machine", until=2.5)

    assert report.stop_reason is StopReason.TIME_BOUND
    assert report.clock_time == 2.5


@pytest.mark.usefixtures("fresh_external_modules")
def test_run_state_def_with_external_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # sm15 Ramp calls step() from ramp.py each 0.1s and never terminates;
    # bound it with until. The runner does not import the module itself:
    # the caller must make it importable, so put the fixture directory on
    # sys.path for the preamble's `from ramp import step`.
    monkeypatch.syspath_prepend(str(RAMP))
    report = run_state_def(
        load_model(RAMP),
        "SM15::Ramp",
        until=0.25,
        external=("ramp", frozenset({"step"})),
    )

    assert report.stop_reason is StopReason.TIME_BOUND
    assert report.trace


@pytest.mark.usefixtures("fresh_external_modules")
def test_run_part_system_with_external_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(PART_EXTERNAL))
    report = run_part_system(
        load_model(PART_EXTERNAL),
        "PartExt::counterSystem",
        until=0.25,
        external=("bump", frozenset({"bump"})),
    )

    assert report.stop_reason is StopReason.TIME_BOUND
    assert report.trace


NONDETERMINISTIC_MODEL = """
package RunNondet {
    private import ScalarValues::*;

    state def Machine {
        attribute x : Integer := 1;
        entry; then idle;
        state idle;
        state left;
        state right;
        transition first idle if x > 0 then left;
        transition first idle if x < 2 then right;
    }
}
"""

INCOMPLETE_GUARD_MODEL = """
package RunIncomplete {
    private import ScalarValues::*;

    state def Machine {
        attribute threshold : Integer;
        entry; then waiting;
        state waiting;
        transition first waiting if threshold > 0 then done;
    }
}
"""

INCOMPLETE_PART_MODEL = """
package PartIncomplete {
    private import ScalarValues::*;

    state def Behavior {
        attribute threshold : Integer;
        entry; then waiting;
        state waiting;
        transition first waiting if threshold > 0 then done;
    }
    part def Machine { exhibit state : Behavior; }
    part sys { part m : Machine; }
}
"""


def test_run_state_def_wraps_nondeterminism(tmp_path: Path) -> None:
    # Both guards are true at once; quake deliberately preserves the
    # nondeterminism and sismic rejects it at runtime.
    model = _load_inline_model(tmp_path, NONDETERMINISTIC_MODEL)

    with pytest.raises(ExecutionError, match=r"[Nn]on-determinis"):
        run_state_def(model, "RunNondet::Machine")


def test_run_state_def_wraps_evaluation_errors(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, INCOMPLETE_GUARD_MODEL)

    with pytest.raises(ExecutionError, match="not defined"):
        run_state_def(model, "RunIncomplete::Machine")


def test_run_part_system_wraps_evaluation_errors(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, INCOMPLETE_PART_MODEL)

    with pytest.raises(ExecutionError, match="not defined"):
        run_part_system(model, "PartIncomplete::sys")
