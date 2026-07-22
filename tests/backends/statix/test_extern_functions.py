"""Tests for bodyless-calc extern function support.

See docs/superpowers/plans/2026-07-16-statix-extern-functions.md.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.builder import build_statix
from sysmlc.sysml.loading import load_model


def test_bodyless_calc_becomes_an_extern_function() -> None:
    model = load_model("models/sm-examples/sm15-external")
    program = build_statix(model, "SM15::Ramp")
    assert len(program.extern_functions) == 1
    fn = program.extern_functions[0]
    assert fn.name == "SM15::P::step"
    assert fn.c_name == "sm15_p_step"
    assert fn.param_types == ("double", "double")
    assert fn.param_names == ("x", "dt")
    assert fn.return_type == "double"


def test_extern_call_site_uses_the_c_name() -> None:
    from sysmlc.backends.statix.serialize import emit_source

    model = load_model("models/sm-examples/sm15-external")
    program = build_statix(model, "SM15::Ramp")
    source = emit_source(program)
    assert "sm15_p_step(ctx->x, 0.1)" in source


def test_bodyless_calc_with_structured_param_reuses_the_attribute_struct() -> (
    None
):
    model = load_model(
        "models/showcase/furuta-pendulum/deterministic/with-dataclass"
    )
    program = build_statix(model, "FurutaPendulum::PendulumSimulation")
    step = next(
        fn for fn in program.extern_functions if fn.name.endswith("::step")
    )
    # PendulumState is already registered as a struct via the `attribute x :
    # PendulumState` binding; the calc's own x/return parameters must reuse
    # that exact same generated struct type name, not a duplicate.
    struct_names = {s.name for s in program.context.structs}
    assert step.param_types[0] in struct_names
    assert step.return_type in struct_names
    assert step.param_types[0] == step.return_type
    assert len(program.context.structs) == 2


def test_cmake_configure_fails_without_extern_impl(tmp_path: Path) -> None:
    model = load_model("models/sm-examples/sm15-external")
    program = build_statix(model, "SM15::Ramp")
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    build = tmp_path / "build"
    result = subprocess.run(
        ["cmake", "-S", str(tmp_path), "-B", str(build)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "external calculations" in result.stdout + result.stderr
    assert "src/extern_impl.c" in result.stdout + result.stderr


def test_project_without_extern_calcs_has_no_requirement(
    tmp_path: Path,
) -> None:
    model = load_model("models/sm-examples/sm01-helloworld")
    program = build_statix(model, "SM01::Machine")
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    assert not (tmp_path / "include" / "statix_extern.h").exists()
    build = tmp_path / "build"
    result = subprocess.run(
        ["cmake", "-S", str(tmp_path), "-B", str(build)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_full_build_and_link_with_a_hand_written_stub(tmp_path: Path) -> None:
    model = load_model("models/sm-examples/sm15-external")
    program = build_statix(model, "SM15::Ramp")
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    (tmp_path / "src" / "extern_impl.c").write_text(
        '#include "statix_extern.h"\n\n'
        "double sm15_p_step(double x, double dt)\n"
        "{\n"
        "    return x + dt;\n"
        "}\n"
    )
    build = tmp_path / "build"
    subprocess.run(
        ["cmake", "-S", str(tmp_path), "-B", str(build)],
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["cmake", "--build", str(build)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_regeneration_preserves_extern_impl(tmp_path: Path) -> None:
    model = load_model("models/sm-examples/sm15-external")
    program = build_statix(model, "SM15::Ramp")
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    stub = (
        '#include "statix_extern.h"\n\n'
        "double sm15_p_step(double x, double dt)\n"
        "{\n"
        "    return x + dt;\n"
        "}\n"
    )
    (tmp_path / "src" / "extern_impl.c").write_text(stub)
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
    assert (tmp_path / "src" / "extern_impl.c").read_text() == stub
