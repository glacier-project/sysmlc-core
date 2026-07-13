from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.serialize import _paths
from sysmlc.sysml.loading import load_model

if TYPE_CHECKING:
    from collections.abc import Callable

    from sysmlc.backends.statix.program import CProgram

pytestmark = pytest.mark.statix

_WHENENTRYDO = Path(__file__).resolve().parent / "fixtures" / "whenentrydo"


def _compile_and_run(
    tmp_path: Path, program: CProgram, name: str, source: str
) -> subprocess.CompletedProcess[str]:
    """Write, compile, and run one custom C harness against a built program."""
    pkg_dir, stem = _paths(program)
    harness = tmp_path / f"{name}.c"
    harness.write_text(source)
    exe = tmp_path / name
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Iinclude",
            f"{name}.c",
            f"src/{pkg_dir}/{stem}.c",
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
    return subprocess.run(
        [str(exe)], capture_output=True, text=True, cwd=tmp_path
    )


_BARE_HARNESS = """\
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
    if (sm16_machine_when_bare_get_state(&sm) !=
        SM16_MACHINE_WHEN_BARE_STATE_IDLE) {
        (void)printf("unexpected state after init\\n");
        return 1;
    }
    /* hot starts false: settling now must be a no-op. */
    if (sm16_machine_when_bare_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle with hot=false unexpectedly failed\\n");
        return 1;
    }
    if (sm16_machine_when_bare_get_state(&sm) !=
        SM16_MACHINE_WHEN_BARE_STATE_IDLE) {
        (void)printf("unexpected state after no-op settle\\n");
        return 1;
    }
    ctx.hot = true;
    if (sm16_machine_when_bare_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle after hot=true failed\\n");
        return 1;
    }
    if (!sm16_machine_when_bare_is_final(&sm)) {
        (void)printf("did not reach done after hot=true\\n");
        return 1;
    }
    return 0;
}
"""


def test_bare_rise_fires_via_settle(
    build_and_compile: Callable[[str, str], tuple[CProgram, Path]],
    tmp_path: Path,
) -> None:
    program, _build = build_and_compile("sm16", "SM16::MachineWhenBare")
    result = _compile_and_run(tmp_path, program, "bare_harness", _BARE_HARNESS)
    assert result.returncode == 0, result.stdout + result.stderr


_ALREADY_TRUE_HARNESS = """\
#include "sm16/machine_when_bare.h"
#include <stdio.h>

int main(void)
{
    sm16_machine_when_bare_context_t ctx;
    sm16_machine_when_bare_t sm;

    sm16_machine_when_bare_context_init(&ctx);
    ctx.hot = true; /* already true before _init */
    if (sm16_machine_when_bare_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    if (!sm16_machine_when_bare_is_final(&sm)) {
        (void)printf("did not fire immediately at entry\\n");
        return 1;
    }
    return 0;
}
"""


def test_already_true_at_entry_fires_immediately(
    build_and_compile: Callable[[str, str], tuple[CProgram, Path]],
    tmp_path: Path,
) -> None:
    program, _build = build_and_compile("sm16", "SM16::MachineWhenBare")
    result = _compile_and_run(
        tmp_path, program, "already_true_harness", _ALREADY_TRUE_HARNESS
    )
    assert result.returncode == 0, result.stdout + result.stderr


_GUARD_TRUE_HARNESS = """\
#include "sm16/machine_when_guard.h"
#include <stdio.h>

int main(void)
{
    sm16_machine_when_guard_context_t ctx;
    sm16_machine_when_guard_t sm;

    sm16_machine_when_guard_context_init(&ctx); /* enabled defaults true */
    if (sm16_machine_when_guard_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    ctx.hot = true;
    if (sm16_machine_when_guard_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle failed\\n");
        return 1;
    }
    if (!sm16_machine_when_guard_is_final(&sm)) {
        (void)printf("did not fire with guard true\\n");
        return 1;
    }
    return 0;
}
"""


def test_guard_true_at_delivery_fires(
    build_and_compile: Callable[[str, str], tuple[CProgram, Path]],
    tmp_path: Path,
) -> None:
    program, _build = build_and_compile("sm16", "SM16::MachineWhenGuard")
    result = _compile_and_run(
        tmp_path, program, "guard_true_harness", _GUARD_TRUE_HARNESS
    )
    assert result.returncode == 0, result.stdout + result.stderr


_GUARD_FALSE_HARNESS = """\
#include "sm16/machine_when_guard.h"
#include <stdio.h>

int main(void)
{
    sm16_machine_when_guard_context_t ctx;
    sm16_machine_when_guard_t sm;

    sm16_machine_when_guard_context_init(&ctx);
    ctx.enabled = false;
    if (sm16_machine_when_guard_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    ctx.hot = true;
    if (sm16_machine_when_guard_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle (consumer) failed\\n");
        return 1;
    }
    if (sm16_machine_when_guard_get_state(&sm) !=
        SM16_MACHINE_WHEN_GUARD_STATE_IDLE) {
        (void)printf("consumer did not stay in idle\\n");
        return 1;
    }
    /* Permanently consumed this activation: still no fire, even once
     * enabled flips true and hot cycles false/true again. */
    ctx.enabled = true;
    if (sm16_machine_when_guard_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle after enabled flip failed\\n");
        return 1;
    }
    if (sm16_machine_when_guard_get_state(&sm) !=
        SM16_MACHINE_WHEN_GUARD_STATE_IDLE) {
        (void)printf("fired after being permanently consumed\\n");
        return 1;
    }
    ctx.hot = false;
    if (sm16_machine_when_guard_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle (hot=false) failed\\n");
        return 1;
    }
    ctx.hot = true;
    if (sm16_machine_when_guard_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle (hot=true again) failed\\n");
        return 1;
    }
    if (sm16_machine_when_guard_get_state(&sm) !=
        SM16_MACHINE_WHEN_GUARD_STATE_IDLE) {
        (void)printf("fired after a second hot rise in the same activation\\n");
        return 1;
    }
    return 0;
}
"""


def test_guard_false_at_delivery_permanently_consumes(
    build_and_compile: Callable[[str, str], tuple[CProgram, Path]],
    tmp_path: Path,
) -> None:
    program, _build = build_and_compile("sm16", "SM16::MachineWhenGuard")
    result = _compile_and_run(
        tmp_path, program, "guard_false_harness", _GUARD_FALSE_HARNESS
    )
    assert result.returncode == 0, result.stdout + result.stderr


_REENTRY_REARMS_HARNESS = """\
#include "sm16/machine_when_guard.h"
#include <stdio.h>

int main(void)
{
    sm16_machine_when_guard_context_t ctx;
    sm16_machine_when_guard_t sm;
    sc_event_id_t kick = SM16_MACHINE_WHEN_GUARD_EVENT_KICK;

    sm16_machine_when_guard_context_init(&ctx);
    ctx.enabled = false;
    if (sm16_machine_when_guard_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    ctx.hot = true;
    if (sm16_machine_when_guard_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle (consume) failed\\n");
        return 1;
    }
    if (sm16_machine_when_guard_get_state(&sm) !=
        SM16_MACHINE_WHEN_GUARD_STATE_IDLE) {
        (void)printf("unexpected state before reentry\\n");
        return 1;
    }
    ctx.enabled = true;
    if (sm16_machine_when_guard_post(&sm, kick) != SC_STATUS_OK) {
        (void)printf("Kick to away failed\\n");
        return 1;
    }
    if (sm16_machine_when_guard_get_state(&sm) !=
        SM16_MACHINE_WHEN_GUARD_STATE_AWAY) {
        (void)printf("Kick did not reach away\\n");
        return 1;
    }
    if (sm16_machine_when_guard_post(&sm, kick) != SC_STATUS_OK) {
        (void)printf("Kick back to idle failed\\n");
        return 1;
    }
    if (!sm16_machine_when_guard_is_final(&sm)) {
        (void)printf("fresh observation on reentry did not fire\\n");
        return 1;
    }
    return 0;
}
"""


def test_reentry_after_consumption_arms_a_fresh_observation(
    build_and_compile: Callable[[str, str], tuple[CProgram, Path]],
    tmp_path: Path,
) -> None:
    program, _build = build_and_compile("sm16", "SM16::MachineWhenGuard")
    result = _compile_and_run(
        tmp_path, program, "reentry_rearms_harness", _REENTRY_REARMS_HARNESS
    )
    assert result.returncode == 0, result.stdout + result.stderr


_REENTRY_HELD_TRUE_HARNESS = """\
#include "sm16/machine_when_reentry.h"
#include <stdio.h>

int main(void)
{
    sm16_machine_when_reentry_context_t ctx;
    sm16_machine_when_reentry_t sm;
    sc_event_id_t reset = SM16_MACHINE_WHEN_REENTRY_EVENT_RESET;

    sm16_machine_when_reentry_context_init(&ctx);
    if (sm16_machine_when_reentry_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    ctx.hot = true;
    if (sm16_machine_when_reentry_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle failed\\n");
        return 1;
    }
    if (sm16_machine_when_reentry_get_state(&sm) !=
        SM16_MACHINE_WHEN_REENTRY_STATE_RUNNING) {
        (void)printf("did not reach running\\n");
        return 1;
    }
    if (sm16_machine_when_reentry_post(&sm, reset) != SC_STATUS_OK) {
        (void)printf("Reset failed\\n");
        return 1;
    }
    if (sm16_machine_when_reentry_get_state(&sm) !=
        SM16_MACHINE_WHEN_REENTRY_STATE_RUNNING) {
        (void)printf("held-true condition did not re-fire on reentry\\n");
        return 1;
    }
    return 0;
}
"""


def test_reentry_with_condition_held_true_fires_each_activation(
    build_and_compile: Callable[[str, str], tuple[CProgram, Path]],
    tmp_path: Path,
) -> None:
    program, _build = build_and_compile("sm16", "SM16::MachineWhenReentry")
    result = _compile_and_run(
        tmp_path,
        program,
        "reentry_held_true_harness",
        _REENTRY_HELD_TRUE_HARNESS,
    )
    assert result.returncode == 0, result.stdout + result.stderr


_TWO_TRIGGERS_HARNESS = """\
#include "sm16/machine_when_two.h"
#include <stdio.h>

static int check_hot_reaches_warmed(void)
{
    sm16_machine_when_two_context_t ctx;
    sm16_machine_when_two_t sm;
    sm16_machine_when_two_context_init(&ctx);
    if (sm16_machine_when_two_init(&sm, &ctx) != SC_STATUS_OK) {
        return 2;
    }
    ctx.hot = true;
    if (sm16_machine_when_two_settle(&sm) != SC_STATUS_OK) {
        return 1;
    }
    if (sm16_machine_when_two_get_state(&sm) !=
        SM16_MACHINE_WHEN_TWO_STATE_WARMED) {
        return 1;
    }
    return 0;
}

static int check_cold_reaches_chilled(void)
{
    sm16_machine_when_two_context_t ctx;
    sm16_machine_when_two_t sm;
    sm16_machine_when_two_context_init(&ctx);
    if (sm16_machine_when_two_init(&sm, &ctx) != SC_STATUS_OK) {
        return 2;
    }
    ctx.cold = true;
    if (sm16_machine_when_two_settle(&sm) != SC_STATUS_OK) {
        return 1;
    }
    if (sm16_machine_when_two_get_state(&sm) !=
        SM16_MACHINE_WHEN_TWO_STATE_CHILLED) {
        return 1;
    }
    return 0;
}

static int check_simultaneous_resolves_by_declaration_order(void)
{
    sm16_machine_when_two_context_t ctx;
    sm16_machine_when_two_t sm;
    sm16_machine_when_two_context_init(&ctx);
    if (sm16_machine_when_two_init(&sm, &ctx) != SC_STATUS_OK) {
        return 2;
    }
    ctx.hot = true;
    ctx.cold = true;
    if (sm16_machine_when_two_settle(&sm) != SC_STATUS_OK) {
        return 1;
    }
    /* `hot` is declared first: deterministic first-match, not an error. */
    if (sm16_machine_when_two_get_state(&sm) !=
        SM16_MACHINE_WHEN_TWO_STATE_WARMED) {
        return 1;
    }
    return 0;
}

int main(void)
{
    if (check_hot_reaches_warmed() != 0) {
        (void)printf("hot-independently-reaches-warmed failed\\n");
        return 1;
    }
    if (check_cold_reaches_chilled() != 0) {
        (void)printf("cold-independently-reaches-chilled failed\\n");
        return 1;
    }
    if (check_simultaneous_resolves_by_declaration_order() != 0) {
        (void)printf("simultaneous-triggers-first-match failed\\n");
        return 1;
    }
    return 0;
}
"""


def test_two_independent_triggers_and_declaration_order(
    build_and_compile: Callable[[str, str], tuple[CProgram, Path]],
    tmp_path: Path,
) -> None:
    program, _build = build_and_compile("sm16", "SM16::MachineWhenTwo")
    result = _compile_and_run(
        tmp_path, program, "two_triggers_harness", _TWO_TRIGGERS_HARNESS
    )
    assert result.returncode == 0, result.stdout + result.stderr


_COMPOSED_HARNESS = """\
#include "sm16/machine_when_composed.h"
#include <stdio.h>

int main(void)
{
    sm16_machine_when_composed_context_t ctx;
    sm16_machine_when_composed_t sm;

    /* hot=false, enabled=false */
    sm16_machine_when_composed_context_init(&ctx);
    if (sm16_machine_when_composed_init(&sm, &ctx) != SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    ctx.hot = true;
    if (sm16_machine_when_composed_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle after hot=true failed\\n");
        return 1;
    }
    if (sm16_machine_when_composed_get_state(&sm) !=
        SM16_MACHINE_WHEN_COMPOSED_STATE_IDLE) {
        (void)printf("fired with enabled still false\\n");
        return 1;
    }
    ctx.enabled = true;
    if (sm16_machine_when_composed_settle(&sm) != SC_STATUS_OK) {
        (void)printf("settle after enabled=true failed\\n");
        return 1;
    }
    if (!sm16_machine_when_composed_is_final(&sm)) {
        (void)printf("did not fire once the whole conjunction became true\\n");
        return 1;
    }
    return 0;
}
"""


def test_composed_condition_observes_the_whole_expression(
    build_and_compile: Callable[[str, str], tuple[CProgram, Path]],
    tmp_path: Path,
) -> None:
    program, _build = build_and_compile("sm16", "SM16::MachineWhenComposed")
    result = _compile_and_run(
        tmp_path, program, "composed_harness", _COMPOSED_HARNESS
    )
    assert result.returncode == 0, result.stdout + result.stderr


_ENTRY_DO_HARNESS = """\
#include "whenentrydo/machine_when_entry_do_mutates.h"
#include <stdio.h>

int main(void)
{
    whenentrydo_machine_when_entry_do_mutates_context_t ctx;
    whenentrydo_machine_when_entry_do_mutates_t sm;

    whenentrydo_machine_when_entry_do_mutates_context_init(&ctx);
    if (whenentrydo_machine_when_entry_do_mutates_init(&sm, &ctx) !=
        SC_STATUS_OK) {
        (void)printf("init failed\\n");
        return 2;
    }
    /* `do assign hot := true;` runs before the arm statement (arm-last), so
     * the guard must see hot=true the first time _init's own completion
     * settle checks it -- no external _settle call needed. */
    if (whenentrydo_machine_when_entry_do_mutates_get_state(&sm) !=
        WHENENTRYDO_MACHINE_WHEN_ENTRY_DO_MUTATES_STATE_RUNNING) {
        (void)printf("did not fire during init's own settle\\n");
        return 1;
    }
    return 0;
}
"""


def test_entry_do_mutation_is_visible_at_first_guard_check(
    tmp_path: Path,
) -> None:
    model = load_model(_WHENENTRYDO)
    program = build_statix(model, "WHENENTRYDO::MachineWhenEntryDoMutates")
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
    result = _compile_and_run(
        tmp_path, program, "entry_do_harness", _ENTRY_DO_HARNESS
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_when_max_triggers_override_too_small_fails_to_compile(
    sm_models: dict, tmp_path: Path
) -> None:
    program = build_statix(sm_models["sm16"], "SM16::MachineWhenTwo")
    assert program.when_count == 2
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    pkg_dir, stem = _paths(program)
    result = subprocess.run(
        [
            "cc",
            "-std=c99",
            "-Iinclude",
            "-DSC_MAX_WHEN_TRIGGERS=1",
            f"src/{pkg_dir}/{stem}.c",
            "-c",
            "-o",
            "out.o",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode != 0
    assert (
        "SC_MAX_WHEN_TRIGGERS too small for this generated machine"
        in result.stderr
    )
