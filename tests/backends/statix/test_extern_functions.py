"""Tests for bodyless-calc extern function support.

See docs/superpowers/plans/2026-07-16-statix-extern-functions.md.
"""

from __future__ import annotations

from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.program import CExternFunction
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


def test_bodyless_calc_with_structured_param_reuses_the_attribute_struct() -> None:
    model = load_model("models/sm-examples/furuta-pendulum")
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
    assert len(program.context.structs) == 1
