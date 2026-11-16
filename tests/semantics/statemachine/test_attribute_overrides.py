from pathlib import Path

import pytest
import syside

from sysmlc.errors import UnsupportedConstructError, ValuesError
from sysmlc.semantics.statemachine import attributes
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import AttributeValue, CompositeValue
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import is_attribute_feature, resolve
from sysmlc.values import configure_model
from tests.test_recording import RecordingBuilder

FIXTURE = Path(__file__).parent / "fixtures" / "attribute-overrides"


def _values(model: syside.Model) -> dict[tuple[str, str], dict[str, object]]:
    builder = RecordingBuilder()
    StateMachineDriver(model).run("FieldOverrideProbe::Machine", builder)
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)

    def evaluate(value: AttributeValue) -> object:
        if isinstance(value, CompositeValue):
            return {name: evaluate(field) for name, field in value.fields}
        if isinstance(value, syside.Expression):
            result, report = compiler.evaluate(value, stdlib=stdlib)
            assert not report.fatal, report.diagnostics
            if isinstance(result, syside.EnumerationUsage):
                return str(result.qualified_name)
            return result
        return value

    result = {}
    for binding in builder.attributes:
        value = evaluate(binding.value)
        assert isinstance(value, dict)
        result[binding.scope, binding.name] = value
    return result


def test_shorthand_fields_preserve_schema_and_resolve_values() -> None:
    values = _values(load_model(FIXTURE))
    base = {
        "count": 1,
        "inner": {"count": 1},
        "delay": 60.0,
        "color": "FieldOverrideProbe::Color::cold",
    }
    assert values == {
        ("", "direct"): base | {"count": 2},
        ("", "nested"): base | {"inner": {"count": 3}},
        ("", "explicit"): base | {"count": 4},
        ("", "kinds"): base
        | {"delay": 120.0, "color": "FieldOverrideProbe::Color::warm"},
        ("", "unchanged"): base,
        ("", "inherited"): base,
        ("enclosing", "local"): base | {"inner": {"count": 3}},
    }
    assert list(values["", "direct"]) == list(base)


def test_configuration_updates_existing_shorthand_without_changing_type() -> (
    None
):
    model = load_model(FIXTURE)
    configure_model(
        model,
        "FieldOverrideProbe::Machine",
        {
            "direct": {"count": 7},
            "nested": {"inner": {"count": 8}},
            "kinds": {"delay": 3},
            "inherited": {"count": 9},
        },
    )
    values = _values(model)
    assert values["", "direct"]["count"] == 7
    assert values["", "nested"]["inner"] == {"count": 8}
    assert values["", "kinds"]["delay"] == 180.0
    assert values["", "inherited"]["count"] == 9
    assert values["", "unchanged"]["count"] == 1
    assert values["enclosing", "local"]["inner"] == {"count": 3}


def test_configuration_preserves_inherited_fixed_field() -> None:
    model = load_model(FIXTURE)
    with pytest.raises(ValuesError, match="fixed by the model"):
        configure_model(
            model, "FieldOverrideProbe::InheritedFixed", {"box": {"count": 7}}
        )


@pytest.mark.parametrize("machine", ["FixedDirect", "FixedNested"])
def test_shorthand_fixed_fields_prevent_whole_value_replacement(
    machine: str,
) -> None:
    model = load_model(FIXTURE)
    with pytest.raises(UnsupportedConstructError, match="fixes its own field"):
        StateMachineDriver(model).run(
            f"FieldOverrideProbe::{machine}", RecordingBuilder()
        )


def test_renamed_field_is_diagnosed_before_materialization() -> None:
    model = load_model(FIXTURE)
    state = resolve(
        model, syside.StateDefinition, "FieldOverrideProbe::Renamed"
    )
    (box,) = state.owned_attributes.collect()
    with pytest.raises(UnsupportedConstructError, match="renamed structured"):
        attributes.bind_value(
            box, syside.Compiler(), syside.Stdlib(model.index)
        )


def test_attribute_fields_are_identified_by_redefinition() -> None:
    model = load_model(FIXTURE)
    unrelated = resolve(
        model, syside.ReferenceUsage, "FieldOverrideProbe::Controls::unrelated"
    )
    payload = resolve(
        model, syside.ItemUsage, "FieldOverrideProbe::Controls::payload"
    )
    override = resolve(
        model,
        syside.ReferenceUsage,
        "FieldOverrideProbe::Machine::direct::count",
    )
    assert is_attribute_feature(override)
    assert not is_attribute_feature(unrelated)
    assert not is_attribute_feature(payload)
