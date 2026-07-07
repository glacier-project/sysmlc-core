import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.builder import build_statix
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


def test_effect_captures_payload_value(sm_models: dict, tmp_path) -> None:
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
