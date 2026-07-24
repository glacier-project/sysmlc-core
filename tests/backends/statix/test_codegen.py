from collections.abc import Callable
from pathlib import Path

import pytest
import syside

from sysmlc.backends.statix.codegen import (
    _C_MATH_FUNCTIONS,
    CCodeGen,
    CCodeGenError,
)
from sysmlc.codegen.python import LIBRARY_FUNCTIONS
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import CompositeValue, SignalTrigger
from sysmlc.sysml.loading import load_model
from tests.test_recording import RecordingBuilder

_DEEPCHAIN = Path(__file__).resolve().parent / "fixtures" / "deepchain"
_ENUMCOMPOSITE = Path(__file__).resolve().parent / "fixtures" / "enumcomposite"
_ENUMREJECT = Path(__file__).resolve().parent / "fixtures" / "enumreject"


def _guards(
    model: syside.Model, qn: str, gen: CCodeGen | None = None
) -> list[str]:
    """Return rendered guards for every guarded transition of a state def."""
    gen = gen or CCodeGen()
    builder = RecordingBuilder()
    StateMachineDriver(model).run(qn, builder)
    return [
        gen.render_expression(t.guard)
        for t in builder.transitions
        if t.guard is not None
    ]


def test_enum_literal_reference_uses_resolver(sm_models: dict) -> None:
    calls: list[str] = []

    def resolver(
        literal: syside.EnumerationUsage,
    ) -> tuple[str, str, bool]:
        assert literal.name is not None
        calls.append(literal.name)
        return "my_enum_t", f"MY_CONST_{literal.name.upper()}", True

    gen = CCodeGen(attribute_names=frozenset({"c"}), enum_resolver=resolver)
    guards = _guards(sm_models["sm18"], "SM18::MachineStringEnum", gen)
    assert guards == ["ctx->c == MY_CONST_GREEN"]
    assert calls == ["green"]


def test_enum_literal_reference_ignores_allow_context(
    sm_models: dict,
) -> None:
    # A composite field's own default (e.g. Holder.color = LightColor::red)
    # is rendered through an allow_context=False generator (_init_gen); the
    # enum-literal branch must resolve before the allow_context rejection,
    # not after -- otherwise every enum-valued composite field would break.
    def resolver(
        literal: syside.EnumerationUsage,
    ) -> tuple[str, str, bool]:
        assert literal.name == "red"
        return "my_enum_t", "MY_CONST_RED", True

    builder = RecordingBuilder()
    enumcomposite = load_model(_ENUMCOMPOSITE)
    StateMachineDriver(enumcomposite).run(
        "ENUMCOMPOSITE::MachineEnumComposite", builder
    )
    (box_binding,) = [b for b in builder.attributes if b.name == "box"]
    assert isinstance(box_binding.value, CompositeValue)
    (color_value,) = [
        v for name, v in box_binding.value.fields if name == "color"
    ]
    gen = CCodeGen(allow_context=False, enum_resolver=resolver)
    assert isinstance(color_value, syside.Expression)
    assert gen.render_expression(color_value) == "MY_CONST_RED"


def test_enum_literal_reference_with_no_resolver_raises(
    sm_models: dict,
) -> None:
    # No enum_resolver configured (the default): an enum-literal referent
    # must fail loud, never silently mis-render as a plain feature name.
    with pytest.raises(UnsupportedConstructError):
        _guards(sm_models["sm18"], "SM18::MachineStringEnum")


def test_boolean_ref_guard(sm_models: dict) -> None:
    assert "ctx->enabled" in _guards(sm_models["sm03"], "SM03::MachineRef")


def test_operators_and_precedence(sm_models: dict) -> None:
    assert _guards(sm_models["sm03"], "SM03::MachineLogicalChain") == [
        "ctx->a && ctx->b || ctx->c"
    ]


def test_not_and_unary_minus(sm_models: dict) -> None:
    assert _guards(sm_models["sm03"], "SM03::MachineNot") == ["!ctx->enabled"]
    assert _guards(sm_models["sm03"], "SM03::MachineUnaryMinus") == [
        "-ctx->x < 0"
    ]


def test_chained_reference(sm_models: dict) -> None:
    assert _guards(sm_models["sm05"], "SM05::MachineChainNested") == [
        "ctx->box.inner.z > 0.0"
    ]


def _effect_values(model: syside.Model, qn: str) -> tuple[list[str], CCodeGen]:
    """Rendered value expressions of transition effects (bypasses builder)."""
    gen = CCodeGen()
    builder = RecordingBuilder()
    StateMachineDriver(model).run(qn, builder)
    out: list[str] = []
    for t in builder.transitions:
        if t.effect is None:
            continue
        for a in actions.inline_actions(t.effect):
            assert isinstance(a, syside.AssignmentActionUsage)
            assert a.value_expression is not None
            out.append(gen.render_expression(a.value_expression))
    return out, gen


def test_c_math_functions_equal_shared_allowlist() -> None:
    # Exact equality, so a new shared function forces an explicit decision here.
    assert set(_C_MATH_FUNCTIONS) == set(LIBRARY_FUNCTIONS)


def test_library_max_lowers_to_fmax(sm_models: dict) -> None:
    values, gen = _effect_values(sm_models["sm14"], "SM14::MachineAssignCall")
    assert values == ["fmax(ctx->x, 0.0)"]
    assert gen.needs_math is True


def test_external_calc_def_call_is_rejected(sm_models: dict) -> None:
    with pytest.raises(UnsupportedConstructError):
        _effect_values(sm_models["sm15"], "SM15::Ramp")


def _payload_facts(model: syside.Model, qn: str) -> list:
    """Transition facts whose trigger binds a payload feature."""
    builder = RecordingBuilder()
    StateMachineDriver(model).run(qn, builder)
    return [
        t
        for t in builder.transitions
        if isinstance(t.trigger, SignalTrigger)
        and t.trigger.payload_feature is not None
    ]


def _payload_gen(
    trigger: SignalTrigger,
    payload_c_type: str | None = "sample_t",
    struct_field_types: dict | None = None,
    attribute_c_types: dict | None = None,
    structs_by_name: dict | None = None,
) -> CCodeGen:
    c_type = payload_c_type or "sample_t"
    return CCodeGen(
        attribute_names=frozenset({"current", "captured"}),
        real_attributes=frozenset({"current", "captured"}),
        payload_feature=trigger.payload_feature,
        payload_c_type=payload_c_type,
        attribute_c_types=attribute_c_types
        or {"current": "double", "captured": c_type},
        struct_field_types=struct_field_types or {c_type: {"value": "double"}},
        structs_by_name=structs_by_name,
    )


def test_payload_read_renders_f64_accessor(sm_models: dict) -> None:
    (t,) = _payload_facts(
        sm_models["sm11"], "SM11::MachineReadablePayloadGuard"
    )
    gen = _payload_gen(t.trigger)
    assert gen.render_expression(t.guard) == "sc_event_payload_f64(event) > 0.5"
    assert gen.payload_reads == {("value",)}


def test_payload_read_in_effect_assignment(sm_models: dict) -> None:
    (t,) = _payload_facts(
        sm_models["sm11"], "SM11::MachineReadablePayloadEffect"
    )
    gen = _payload_gen(t.trigger)
    (assign,) = actions.inline_actions(t.effect)
    assert (
        gen.render_action(assign)
        == "ctx->captured = sc_event_payload_f64(event);"
    )
    assert gen.payload_reads == {("value",)}


def test_two_segment_payload_chain_renders_f64_accessor(
    sm_models: dict,
) -> None:
    (t,) = _payload_facts(
        sm_models["sm11"], "SM11::MachineReadablePayloadChain"
    )
    gen = _payload_gen(t.trigger)
    assert gen.render_expression(t.guard) == "sc_event_payload_f64(event) > 0.5"
    assert gen.payload_reads == {("sample", "value")}


def test_three_segment_payload_chain_rejected(sm_models: dict) -> None:
    model = load_model(_DEEPCHAIN)
    (t,) = _payload_facts(model, "DEEPCHAIN::MachineDeepChain")
    gen = _payload_gen(t.trigger)
    with pytest.raises(UnsupportedConstructError):
        gen.render_expression(t.guard)


def test_whole_payload_capture_no_longer_raises(sm_models: dict) -> None:
    from sysmlc.backends.statix.program import CField, CStruct

    (t,) = _payload_facts(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
    )
    c_type = "sm11_machine_readable_payload_whole_measurement_t"
    sample_type = "sm11_machine_readable_payload_whole_sample_t"
    structs = {
        c_type: CStruct(
            name=c_type,
            fields=(
                CField("value", "double", ""),
                CField("sample", sample_type, ""),
            ),
        ),
        sample_type: CStruct(
            name=sample_type, fields=(CField("value", "double", ""),)
        ),
    }
    gen = _payload_gen(
        t.trigger,
        payload_c_type=c_type,
        struct_field_types={
            c_type: {"value": "double", "sample": sample_type},
            sample_type: {"value": "double"},
        },
        structs_by_name=structs,
    )
    (assign,) = actions.inline_actions(t.effect)
    rendered = gen.render_action(assign)
    assert "sc_event_payload_read" in rendered


def test_scalar_payload_to_non_real_target_stays_rejected(
    sm_models: dict,
) -> None:
    # The guard's real, correct purpose must survive the false-positive fix
    # below: a genuine scalar payload read assigned to a non-Real attribute
    # is still an error.
    (t,) = _payload_facts(
        sm_models["sm11"], "SM11::MachineReadablePayloadEffect"
    )
    gen = CCodeGen(
        attribute_names=frozenset({"current", "captured"}),
        real_attributes=frozenset(
            {"current"}
        ),  # captured deliberately NOT Real
        payload_feature=t.trigger.payload_feature,
    )
    (assign,) = actions.inline_actions(t.effect)
    with pytest.raises(UnsupportedConstructError):
        gen.render_action(assign)


def test_payload_read_without_binding_still_rejected(sm_models: dict) -> None:
    # Same expression, no payload_feature bound: the pre-B.2 rejection holds.
    (t,) = _payload_facts(
        sm_models["sm11"], "SM11::MachineReadablePayloadGuard"
    )
    gen = CCodeGen(
        attribute_names=frozenset({"current"}),
        real_attributes=frozenset({"current"}),
    )
    with pytest.raises(UnsupportedConstructError):
        gen.render_expression(t.guard)


def _enum_resolver_for(
    generated: frozenset[str],
) -> Callable[[syside.EnumerationUsage], tuple[str, str, bool]]:
    def resolver(
        literal: syside.EnumerationUsage,
    ) -> tuple[str, str, bool]:
        assert literal.name is not None
        c_type = "relcolor_t"
        return c_type, f"RELCOLOR_{literal.name.upper()}", c_type in generated

    return resolver


def test_relational_against_generated_enum_literal_is_rejected() -> None:
    model = load_model(_ENUMREJECT)
    gen = CCodeGen(
        attribute_names=frozenset({"c"}),
        attribute_c_types={"c": "relcolor_t"},
        generated_enum_types=frozenset({"relcolor_t"}),
        enum_resolver=_enum_resolver_for(frozenset({"relcolor_t"})),
    )
    with pytest.raises(UnsupportedConstructError):
        _guards(model, "ENUMREJECT::MachineRelationalLiteral", gen)


def test_relational_between_two_generated_enum_attributes_is_rejected() -> None:
    # Neither operand is itself a literal reference (referent is
    # AttributeUsage for both c1 and c2) -- only the type-aware check
    # (attribute_c_types + generated_enum_types) catches this.
    model = load_model(_ENUMREJECT)
    gen = CCodeGen(
        attribute_names=frozenset({"c1", "c2"}),
        attribute_c_types={"c1": "relcolor_t", "c2": "relcolor_t"},
        generated_enum_types=frozenset({"relcolor_t"}),
    )
    with pytest.raises(UnsupportedConstructError):
        _guards(model, "ENUMREJECT::MachineRelationalAttributes", gen)


def test_relational_between_native_scalar_attributes_still_works() -> None:
    # Same shape as the two attributes above (MachineRelationalAttributes'
    # `c1 < c2` guard), but with a recorded C type that is NOT in
    # generated_enum_types (the native-projection case, e.g. GradePoints):
    # the comparison must render normally, not raise. This asserts the
    # check is keyed on type, not on which attributes happen to be
    # compared.
    model = load_model(_ENUMREJECT)
    gen = CCodeGen(
        attribute_names=frozenset({"c1", "c2"}),
        attribute_c_types={"c1": "double", "c2": "double"},
        generated_enum_types=frozenset({"relcolor_t"}),
    )
    guards = _guards(model, "ENUMREJECT::MachineRelationalAttributes", gen)
    assert guards == ["ctx->c1 < ctx->c2"]


def test_relational_between_two_enum_valued_composite_fields_is_rejected() -> (
    None
):
    # b1.shade < b2.shade: both operands are FeatureChainExpressions, not
    # bare FeatureReferenceExpressions -- exercises _generated_enum_c_type's
    # chain-walking branch (struct_field_types), distinct from the
    # bare-attribute-reference branch the two tests above exercise.
    model = load_model(_ENUMREJECT)
    gen = CCodeGen(
        attribute_names=frozenset({"b1", "b2"}),
        attribute_c_types={"b1": "box_t", "b2": "box_t"},
        struct_field_types={"box_t": {"shade": "relcolor_t"}},
        generated_enum_types=frozenset({"relcolor_t"}),
    )
    with pytest.raises(UnsupportedConstructError):
        _guards(model, "ENUMREJECT::MachineRelationalCompositeFields", gen)


def test_whole_payload_assignment_type_mismatch_rejected(
    sm_models: dict,
) -> None:
    # captured declared as a plain Real (not the Measurement struct type)
    # must be rejected with a clear statix-level diagnostic, not silently
    # emit an incompatible C compound-literal assignment.
    (t,) = _payload_facts(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
    )
    gen = CCodeGen(
        attribute_names=frozenset({"current", "captured"}),
        real_attributes=frozenset({"current", "captured"}),
        payload_feature=t.trigger.payload_feature,
        payload_c_type="sm11_machine_readable_payload_whole_measurement_t",
        struct_field_types={
            "sm11_machine_readable_payload_whole_measurement_t": {
                "value": "double",
                "sample": "sm11_machine_readable_payload_whole_sample_t",
            },
        },
        attribute_c_types={
            "current": "double",
            "captured": "double",
        },  # WRONG on purpose
    )
    (assign,) = actions.inline_actions(t.effect)
    with pytest.raises(CCodeGenError, match="cannot assign the whole payload"):
        gen.render_action(assign)
