import syside

from sysmlc.backends.statix.codegen import CCodeGen
from sysmlc.semantics.statemachine.driver import StateMachineDriver


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
