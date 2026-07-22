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
_ENUMCOMPOSITE = Path(__file__).resolve().parent / "fixtures" / "enumcomposite"


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


def test_enum_valued_composite_field_compiles_and_runs(
    statix_run: Callable,
) -> None:
    # Proves the enum-before-nested-struct placement fix (Task 7) end to
    # end: the generated header must actually compile, not just look right
    # textually. Uses the fixture-path model directly (not sm_models),
    # since enumcomposite is a statix-only interaction test, never added to
    # the shared sm18-enum-literals corpus.
    model = load_model(_ENUMCOMPOSITE)
    program = build_statix(model, "ENUMCOMPOSITE::MachineEnumComposite")
    assert statix_run(program) == "matched"


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
            "src/sc_runtime_impl.c",
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
    # truncated.
    program, build = _build_and_compile(
        sm_models, tmp_path, "SM13::MachineAfterSeconds"
    )
    result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--tick", "99999999999"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "invalid tick value: 99999999999" in result.stderr


def test_tick_missing_and_negative_values_are_rejected(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "SM13::MachineAfterSeconds"
    )
    missing = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--tick"],
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 2
    assert "--tick requires a value" in missing.stderr

    negative = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--tick", "-1"],
        capture_output=True,
        text=True,
    )
    assert negative.returncode == 2
    assert "invalid tick value: -1" in negative.stderr

    negative_eq = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--tick=-1"],
        capture_output=True,
        text=True,
    )
    assert negative_eq.returncode == 2
    assert "invalid tick value: -1" in negative_eq.stderr


def test_tick_equals_and_space_forms_agree(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "SM13::MachineAfterSeconds"
    )
    space = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--tick", "5000"],
        capture_output=True,
        text=True,
        check=True,
    )
    equals = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--tick=5000"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert (
        space.stdout.strip().splitlines()[-1]
        == equals.stdout.strip().splitlines()[-1]
    )


def test_legacy_colon_syntax_is_rejected_with_migration_error(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(
        sm_models, tmp_path, "SM13::MachineAfterSeconds"
    )
    result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "tick:5000"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "'tick:5000' is no longer supported" in result.stderr
    assert "--tick" in result.stderr


def test_tick_option_rejected_on_untimed_machine(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(sm_models, tmp_path, "SM01::Machine")
    result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--tick", "5"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "option '--tick' is not supported by this machine" in result.stderr


def test_unknown_option_distinct_from_unknown_event(
    sm_models: dict, tmp_path: Path
) -> None:
    program, build = _build_and_compile(sm_models, tmp_path, "SM01::Machine")
    option_result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "--foo"],
        capture_output=True,
        text=True,
    )
    assert option_result.returncode == 2
    assert "unknown option: --foo" in option_result.stderr

    event_result = subprocess.run(
        [str(build / f"{program.prefix}_runner"), "Foo"],
        capture_output=True,
        text=True,
    )
    assert event_result.returncode == 2
    assert "unknown event: Foo" in event_result.stderr


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
            "src/sc_runtime_impl.c",
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
            "src/sc_runtime_impl.c",
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


def test_whole_payload_roundtrips_end_to_end(
    sm_models: dict, tmp_path: Path
) -> None:
    program = build_statix(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
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
        [str(build / f"{program.prefix}_runner")],
        capture_output=True,
        text=True,
        check=True,
    )
    last_line = result.stdout.strip().splitlines()[-1]
    assert "state=fired" in last_line
    assert "ctx.captured.value=0.9" in last_line
    assert "ctx.captured.sample.value=0.75" in last_line
