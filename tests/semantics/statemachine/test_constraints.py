from pathlib import Path

import syside
from sysmlc_models.sm_examples import SM_EXAMPLES_BY_DIR

from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.sysml.loading import load_model
from tests.test_recording import RecordingBuilder

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_driver_pushes_asserted_constraints(
    contract_model: syside.Model,
) -> None:
    builder = RecordingBuilder()
    StateMachineDriver(contract_model).run("Contracts::Machine", builder)
    assert [c.name for c in builder.constraints] == [
        "levelPositive",
        "thresholdPositive",
    ]
    assert all(c.scope == "" for c in builder.constraints)
    assert all(c.expression is not None for c in builder.constraints)


def test_scoped_constraint_carries_state_path() -> None:
    model = load_model(FIXTURES_DIR / "scoped-constraint")
    builder = RecordingBuilder()
    StateMachineDriver(model).run("ScopedConstraint::Machine", builder)
    (fact,) = builder.constraints
    assert fact.name == "levelPositive"
    assert fact.scope == "idle"


def test_negated_constraint_carries_flag() -> None:
    example = SM_EXAMPLES_BY_DIR["sm17-assert-constraints"]
    model = load_model(example.model_dir)
    builder = RecordingBuilder()
    StateMachineDriver(model).run("SM17::MachineNegated", builder)
    (fact,) = builder.constraints
    assert fact.name == "tooHigh"
    assert fact.is_negated


def test_constraint_hook_is_optional(contract_model: syside.Model) -> None:
    # A builder without `bind_constraint` must keep working on a model that
    # declares asserted constraints.
    class _NoHook:
        def bind_attribute(self, binding: object) -> None:
            pass

        def add_state(self, state: object) -> None:
            pass

        def add_transition(self, transition: object) -> None:
            pass

        def result(self) -> object:
            return "ok"

    result = StateMachineDriver(contract_model).run(
        "Contracts::Machine", _NoHook()
    )
    assert result == "ok"
