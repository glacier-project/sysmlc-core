from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sysmlc.backends.quake.runner import run_part_system, run_state_def
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model
from tests.backends.test_sm_examples import SM_EXAMPLES_DIR

if TYPE_CHECKING:
    from pathlib import Path

FIX = SM_EXAMPLES_DIR / "part01-two-parts"

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


def test_run_part_system_respects_max_steps() -> None:
    with pytest.raises(RuntimeError, match="exceeded"):
        run_part_system(load_model(FIX), "Part01::pingSystem", max_steps=1)
