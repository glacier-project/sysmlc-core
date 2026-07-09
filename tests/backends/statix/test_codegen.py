from pathlib import Path

import pytest
import syside

from sysmlc.backends.statix.codegen import _C_MATH_FUNCTIONS, CCodeGen
from sysmlc.codegen.python import LIBRARY_FUNCTIONS
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import SignalTrigger
from sysmlc.sysml.loading import load_model

_DEEPCHAIN = Path(__file__).resolve().parent / "fixtures" / "deepchain"


class _FactSink:
    """Minimal TargetBuilder that just records transition facts."""

    def __init__(self, out: list) -> None:
        self.transitions = out

    def bind_attribute(self, b: object) -> None: ...

    def add_state(self, s: object) -> None: ...

    def add_transition(self, t: object) -> None:
        self.transitions.append(t)

    def result(self) -> object:
        return None


def _guards(model: syside.Model, qn: str) -> list[str]:
    """Return rendered guards for every guarded transition of a state def."""
    gen = CCodeGen()
    facts: list = []
    StateMachineDriver(model).run(qn, _FactSink(facts))
    return [
        gen.render_expression(t.guard) for t in facts if t.guard is not None
    ]


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
    facts: list = []
    StateMachineDriver(model).run(qn, _FactSink(facts))
    out: list[str] = []
    for t in facts:
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
    facts: list = []
    StateMachineDriver(model).run(qn, _FactSink(facts))
    return [
        t
        for t in facts
        if isinstance(t.trigger, SignalTrigger)
        and t.trigger.payload_feature is not None
    ]


def _payload_gen(trigger: SignalTrigger) -> CCodeGen:
    return CCodeGen(
        attribute_names=frozenset({"current", "captured"}),
        real_attributes=frozenset({"current", "captured"}),
        payload_feature=trigger.payload_feature,
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


def test_whole_payload_reference_rejected(sm_models: dict) -> None:
    (t,) = _payload_facts(
        sm_models["sm11"], "SM11::MachineReadablePayloadWhole"
    )
    gen = _payload_gen(t.trigger)
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
