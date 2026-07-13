import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.program import CProgram
from sysmlc.backends.statix.serialize import _paths
from sysmlc.sysml.loading import load_model

pytestmark = pytest.mark.statix

_SELFLOOP = Path(__file__).resolve().parent / "fixtures" / "selfloop"


def test_sm01_settles_in_running(sm_models: dict, statix_run: Callable) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    assert statix_run(program) == "running"


def test_sm07_firing_order_reaches_b(
    sm_models: dict, statix_run: Callable
) -> None:
    program = build_statix(sm_models["sm07"], "SM07::MachineFiringOrder")
    assert statix_run(program) == "b"


def test_self_transition_is_external(statix_run: Callable) -> None:
    # External self-loop re-enters `a` (n -> 2), so completion fires a -> b.
    model = load_model(_SELFLOOP)
    program = build_statix(model, "SELFLOOP::MachineSelfLoop")
    assert statix_run(program, ("E",)) == "b"


_CAPTURE_HARNESS = """\
#include "sm11/machine_readable_payload_effect.h"
#include <stdio.h>

int main(void)
{
    sm11_machine_readable_payload_effect_context_t ctx;
    sm11_machine_readable_payload_effect_t sm;
    sm11_machine_readable_payload_effect_context_init(&ctx);
    if (sm11_machine_readable_payload_effect_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    /* Bit-exact roundtrip: same double marshalled and unmarshalled. */
    if (ctx.captured != 0.9) {
        (void)printf("captured=%.17g\\n", ctx.captured);
        return 1;
    }
    return 0;
}
"""


def test_effect_captures_payload_value(sm_models: dict, tmp_path: Path) -> None:
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadEffect"
    )
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    harness = tmp_path / "capture_harness.c"
    harness.write_text(_CAPTURE_HARNESS)
    exe = tmp_path / "capture_harness"
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Iinclude",
            "capture_harness.c",
            "src/sm11/machine_readable_payload_effect.c",
            "src/sc/sc_status.c",
            "src/sc/sc_event_queue.c",
            "src/sc/sc_runtime.c",
            "-o",
            str(exe),
        ],
        check=True,
        capture_output=True,
        cwd=tmp_path,
    )
    result = subprocess.run(
        [str(exe)], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_after_seconds_fires_on_tick(
    sm_models: dict, statix_run: Callable
) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterSeconds")
    assert statix_run(program, ("tick:5000",)) == "done"


def test_after_seconds_does_not_fire_before_deadline(
    sm_models: dict, statix_run: Callable
) -> None:
    program = build_statix(sm_models["sm13"], "SM13::MachineAfterSeconds")
    assert statix_run(program, ("tick:4999",)) == "idle"


def _build_and_compile(
    sm_models: dict, tmp_path: Path, qn: str
) -> tuple[CProgram, Path]:
    model_key = qn.split("::")[0].lower()
    program = build_statix(sm_models[model_key], qn)
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


def test_tick_overflow_is_rejected(sm_models: dict, tmp_path: Path) -> None:
    # A tick value beyond SC_TIME_MAX must be rejected, not silently
    # truncated: the parser rejects it, so the runner falls through to
    # _event_from_name (which also doesn't recognize it) and exits 2.
    program, build = _build_and_compile(
        sm_models, tmp_path, "SM13::MachineAfterSeconds"
    )
    result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "tick:99999999999"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unknown event: tick:99999999999" in result.stderr


def test_tick_empty_and_negative_are_rejected(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "SM13::MachineAfterSeconds"
    )
    for bad in ("tick:", "tick:-1"):
        result = subprocess.run(
            [str(build / f"{program.prefix}_runner"), bad],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, bad
        assert f"unknown event: {bad}" in result.stderr, bad


_GUARD_HARNESS = """\
#include "sm13/machine_after_guard.h"
#include <stdio.h>

int main(void)
{
    sm13_machine_after_guard_context_t ctx;
    sm13_machine_after_guard_t sm;
    sc_status_t status;

    sm13_machine_after_guard_context_init(&ctx);
    ctx.ready = false;
    if (sm13_machine_after_guard_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    /* Deadline delivered at 5000 ticks with ready=false: consumed. */
    status = sm13_machine_after_guard_tick(&sm, 5000u);
    if (status != SC_STATUS_NO_TRANSITION) {
        (void)printf("unexpected status after false guard: %s\\n",
                     sc_status_str(status));
        return 1;
    }
    if (sm13_machine_after_guard_get_state(&sm) !=
        SM13_MACHINE_AFTER_GUARD_STATE_IDLE) {
        (void)printf("unexpected state after false guard\\n");
        return 1;
    }
    /* ready flips true and time advances further: the latch must still
     * consume the occurrence -- it must never fire retroactively. */
    ctx.ready = true;
    status = sm13_machine_after_guard_tick(&sm, 50000u);
    if (status != SC_STATUS_NO_TRANSITION) {
        (void)printf("unexpected status after ready flip: %s\\n",
                     sc_status_str(status));
        return 1;
    }
    if (sm13_machine_after_guard_get_state(&sm) !=
        SM13_MACHINE_AFTER_GUARD_STATE_IDLE) {
        (void)printf("false guard did not permanently consume occurrence\\n");
        return 1;
    }
    return 0;
}
"""


def test_generated_false_guard_consumes_the_occurrence(
    sm_models: dict, tmp_path: Path
) -> None:
    program, _build = _build_and_compile(
        sm_models, tmp_path, "SM13::MachineAfterGuard"
    )
    harness = tmp_path / "guard_harness.c"
    harness.write_text(_GUARD_HARNESS)
    exe = tmp_path / "guard_harness"
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Iinclude",
            "guard_harness.c",
            f"src/{_paths(program)[0]}/{_paths(program)[1]}.c",
            "src/sc/sc_status.c",
            "src/sc/sc_event_queue.c",
            "src/sc/sc_runtime.c",
            "-o",
            str(exe),
        ],
        check=True,
        capture_output=True,
        cwd=tmp_path,
    )
    result = subprocess.run(
        [str(exe)], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0, result.stdout + result.stderr


_SELF_LOOP_HARNESS = """\
#include "sm13/machine_after_self_loop.h"
#include <stdio.h>

int main(void)
{
    sm13_machine_after_self_loop_context_t ctx;
    sm13_machine_after_self_loop_t sm;

    sm13_machine_after_self_loop_context_init(&ctx);
    if (sm13_machine_after_self_loop_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    if (ctx.entries != 1) {
        (void)printf("entries=%d after init, expected 1\\n", ctx.entries);
        return 1;
    }
    if (sm13_machine_after_self_loop_tick(&sm, 5000u) != SC_STATUS_OK) {
        (void)printf("tick at 5000 did not fire\\n");
        return 1;
    }
    if (ctx.entries != 2) {
        (void)printf("entries=%d after tick 5000, expected 2\\n", ctx.entries);
        return 1;
    }
    /* Only 2000 ticks past the fresh deadline (7000 < 5000+5000=10000). */
    if (sm13_machine_after_self_loop_tick(&sm, 7000u) !=
        SC_STATUS_NO_TRANSITION) {
        (void)printf("tick at 7000 unexpectedly fired\\n");
        return 1;
    }
    if (ctx.entries != 2) {
        (void)printf("entries=%d after tick 7000, expected 2\\n", ctx.entries);
        return 1;
    }
    if (sm13_machine_after_self_loop_tick(&sm, 10000u) != SC_STATUS_OK) {
        (void)printf("tick at 10000 did not fire\\n");
        return 1;
    }
    if (ctx.entries != 3) {
        (void)printf("entries=%d after tick 10000, expected 3\\n", ctx.entries);
        return 1;
    }
    return 0;
}
"""


def test_generated_self_loop_rearms_a_fresh_deadline(
    sm_models: dict, tmp_path: Path
) -> None:
    program, _build = _build_and_compile(
        sm_models, tmp_path, "SM13::MachineAfterSelfLoop"
    )
    harness = tmp_path / "self_loop_harness.c"
    harness.write_text(_SELF_LOOP_HARNESS)
    exe = tmp_path / "self_loop_harness"
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Iinclude",
            "self_loop_harness.c",
            f"src/{_paths(program)[0]}/{_paths(program)[1]}.c",
            "src/sc/sc_status.c",
            "src/sc/sc_event_queue.c",
            "src/sc/sc_runtime.c",
            "-o",
            str(exe),
        ],
        check=True,
        capture_output=True,
        cwd=tmp_path,
    )
    result = subprocess.run(
        [str(exe)], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0, result.stdout + result.stderr


_WHEN_BARE_HARNESS = """\
#include "sm16/machine_when_bare.h"
#include <stdio.h>

int main(void)
{
    sm16_machine_when_bare_context_t ctx;
    sm16_machine_when_bare_t sm;

    sm16_machine_when_bare_context_init(&ctx);
    if (sm16_machine_when_bare_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    if (sm16_machine_when_bare_get_state(&sm) != SM16_MACHINE_WHEN_BARE_STATE_IDLE) {
        (void)printf("expected idle initially\\n");
        return 1;
    }
    ctx.hot = true;
    if (sm16_machine_when_bare_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle failed\\n");
        return 1;
    }
    if (sm16_machine_when_bare_get_state(&sm) != SM16_MACHINE_WHEN_BARE_STATE_DONE) {
        (void)printf("expected done after settle, got %s\\n", sm16_machine_when_bare_state_name(sm16_machine_when_bare_get_state(&sm)));
        return 1;
    }
    if (!sm16_machine_when_bare_is_final(&sm)) {
        (void)printf("expected is_final true\\n");
        return 1;
    }
    return 0;
}
"""


def test_compile_run_sm16_when_bare(sm_models: dict, tmp_path: Path) -> None:
    program, _build = _build_and_compile(
        sm_models, tmp_path, "SM16::MachineWhenBare"
    )
    harness = tmp_path / "when_bare_harness.c"
    harness.write_text(_WHEN_BARE_HARNESS)
    exe = tmp_path / "when_bare_harness"
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Iinclude",
            "when_bare_harness.c",
            f"src/{_paths(program)[0]}/{_paths(program)[1]}.c",
            "src/sc/sc_status.c",
            "src/sc/sc_event_queue.c",
            "src/sc/sc_runtime.c",
            "-o",
            str(exe),
        ],
        check=True,
        capture_output=True,
        cwd=tmp_path,
    )
    result = subprocess.run(
        [str(exe)], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0, result.stdout + result.stderr


_WHEN_GUARD_HARNESS = """\
#include "sm16/machine_when_guard.h"
#include <stdio.h>

int main(void)
{
    sm16_machine_when_guard_context_t ctx;
    sm16_machine_when_guard_t sm;

    sm16_machine_when_guard_context_init(&ctx);
    if (sm16_machine_when_guard_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    /* Set hot = true while enabled = false -> consumer fires on settle */
    ctx.hot = true;
    ctx.enabled = false;
    if (sm16_machine_when_guard_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle with false guard failed\\n");
        return 1;
    }
    if (sm16_machine_when_guard_get_state(&sm) != SM16_MACHINE_WHEN_GUARD_STATE_IDLE) {
        (void)printf("expected idle after consumer disarmed\\n");
        return 1;
    }
    /* Now even when enabled = true, slot is disarmed so no transition */
    ctx.enabled = true;
    if (sm16_machine_when_guard_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle with enabled=true failed\\n");
        return 1;
    }
    if (sm16_machine_when_guard_get_state(&sm) != SM16_MACHINE_WHEN_GUARD_STATE_IDLE) {
        (void)printf("expected still idle after disarmed settle\\n");
        return 1;
    }
    /* Kick -> away */
    if (sm16_machine_when_guard_post(&sm, SM16_MACHINE_WHEN_GUARD_EVENT_KICK) != SC_STATUS_OK) {
        (void)printf("kick to away failed\\n");
        return 1;
    }
    if (sm16_machine_when_guard_get_state(&sm) != SM16_MACHINE_WHEN_GUARD_STATE_AWAY) {
        (void)printf("expected away after kick\\n");
        return 1;
    }
    /* Kick -> re-enter idle (which arms when_armed[0]). Since hot=true and enabled=true, completion fires immediately to running then done! */
    if (sm16_machine_when_guard_post(&sm, SM16_MACHINE_WHEN_GUARD_EVENT_KICK) != SC_STATUS_OK) {
        (void)printf("kick re-entry to idle failed\\n");
        return 1;
    }
    if (sm16_machine_when_guard_get_state(&sm) != SM16_MACHINE_WHEN_GUARD_STATE_DONE) {
        (void)printf("expected done after kick re-entry, got %s\\n", sm16_machine_when_guard_state_name(sm16_machine_when_guard_get_state(&sm)));
        return 1;
    }
    return 0;
}
"""


def test_compile_run_sm16_when_guard(sm_models: dict, tmp_path: Path) -> None:
    program, _build = _build_and_compile(
        sm_models, tmp_path, "SM16::MachineWhenGuard"
    )
    harness = tmp_path / "when_guard_harness.c"
    harness.write_text(_WHEN_GUARD_HARNESS)
    exe = tmp_path / "when_guard_harness"
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Iinclude",
            "when_guard_harness.c",
            f"src/{_paths(program)[0]}/{_paths(program)[1]}.c",
            "src/sc/sc_status.c",
            "src/sc/sc_event_queue.c",
            "src/sc/sc_runtime.c",
            "-o",
            str(exe),
        ],
        check=True,
        capture_output=True,
        cwd=tmp_path,
    )
    result = subprocess.run(
        [str(exe)], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0, result.stdout + result.stderr


_WHEN_TWO_HARNESS = """\
#include "sm16/machine_when_two.h"
#include <stdio.h>

int main(void)
{
    sm16_machine_when_two_context_t ctx;
    sm16_machine_when_two_t sm;

    sm16_machine_when_two_context_init(&ctx);
    if (sm16_machine_when_two_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    ctx.cold = true;
    if (sm16_machine_when_two_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle cold failed\\n");
        return 1;
    }
    if (sm16_machine_when_two_get_state(&sm) != SM16_MACHINE_WHEN_TWO_STATE_CHILLED) {
        (void)printf("expected chilled after cold=true\\n");
        return 1;
    }

    /* Second instance: check both true -> declaration order wins (hot then cold -> warmed) */
    sm16_machine_when_two_context_init(&ctx);
    if (sm16_machine_when_two_init(&sm, &ctx) != SC_STATUS_OK) {
        return 2;
    }
    ctx.hot = true;
    ctx.cold = true;
    if (sm16_machine_when_two_settle(&sm) != SC_STATUS_OK) {
        return 1;
    }
    if (sm16_machine_when_two_get_state(&sm) != SM16_MACHINE_WHEN_TWO_STATE_WARMED) {
        (void)printf("expected warmed when both true\\n");
        return 1;
    }
    return 0;
}
"""


def test_compile_run_sm16_when_two(sm_models: dict, tmp_path: Path) -> None:
    program, _build = _build_and_compile(
        sm_models, tmp_path, "SM16::MachineWhenTwo"
    )
    harness = tmp_path / "when_two_harness.c"
    harness.write_text(_WHEN_TWO_HARNESS)
    exe = tmp_path / "when_two_harness"
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Iinclude",
            "when_two_harness.c",
            f"src/{_paths(program)[0]}/{_paths(program)[1]}.c",
            "src/sc/sc_status.c",
            "src/sc/sc_event_queue.c",
            "src/sc/sc_runtime.c",
            "-o",
            str(exe),
        ],
        check=True,
        capture_output=True,
        cwd=tmp_path,
    )
    result = subprocess.run(
        [str(exe)], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0, result.stdout + result.stderr

