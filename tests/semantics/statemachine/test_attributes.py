import syside
from sysmlc_models.catalog import model_path

from sysmlc.semantics.statemachine import attributes
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import (
    AttributeDirection,
    CompositeValue,
)
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import resolve
from tests.backends.test_showcase import SHOWCASE_DIR
from tests.test_recording import RecordingBuilder

SM_DIR = model_path("sm-examples")


def _named_attr(
    model: syside.Model, qn: str, name: str
) -> syside.AttributeUsage | syside.ItemUsage:
    machine = resolve(model, syside.StateDefinition, qn)
    return next(
        a for a in attributes.scope_attributes(machine) if a.name == name
    )


def test_scalar_binds_to_expression_node() -> None:
    model = load_model(SM_DIR / "sm04-assignment")
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    counter = _named_attr(model, "SM04::MachineEntryIncrement", "counter")
    value = attributes.bind_value(counter, compiler, stdlib)
    assert isinstance(value, syside.Expression)


def test_composite_binds_to_composite_value() -> None:
    model = load_model(SM_DIR / "sm05-chained-references")
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    pt = _named_attr(model, "SM05::MachineChainGuard", "pt")
    value = attributes.bind_value(pt, compiler, stdlib)
    assert isinstance(value, CompositeValue)
    assert [name for name, _ in value.fields] == ["x"]


def test_composite_value_carries_type_name() -> None:
    model = load_model(SM_DIR / "sm05-chained-references")
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    pt = _named_attr(model, "SM05::MachineChainGuard", "pt")
    value = attributes.bind_value(pt, compiler, stdlib)
    assert isinstance(value, CompositeValue)
    assert value.type_name == "Point"
    assert value.definition.name == "Point"


def test_scalar_quantity_binds_to_si_float() -> None:
    model = load_model(SM_DIR / "sm13-time-trigger")
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)
    pick = _named_attr(model, "SM13::MachineAfterAttribute", "pickDuration")
    value = attributes.bind_value(pick, compiler, stdlib)
    assert value == 120.0


def test_iter_scope_attributes_yields_root_attribute() -> None:
    model = load_model(SM_DIR / "sm04-assignment")
    machine = resolve(
        model, syside.StateDefinition, "SM04::MachineEntryIncrement"
    )
    names = [attr.name for _, attr in attributes.iter_scope_attributes(machine)]
    assert names == ["counter"]


def test_attribute_direction_is_captured() -> None:
    builder = RecordingBuilder()
    model = load_model(SHOWCASE_DIR / "thermostat")
    StateMachineDriver(model).run("Thermostat::ThermostatBehavior", builder)
    directions = {b.name: b.direction for b in builder.attributes}
    assert directions["setpoint"] is AttributeDirection.IN
    assert directions["hysteresis"] is AttributeDirection.IN
    assert directions["temperature"] is AttributeDirection.INOUT
