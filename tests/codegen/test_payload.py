from __future__ import annotations

import sys
from pathlib import Path

import pytest
import syside

from sysmlc.codegen.python import (
    PayloadField,
    PythonCodeGen,
    payload_fields,
    payload_signature,
)
from sysmlc.codegen.structured import (
    DataclassRegistry,
    GeneratedPythonModule,
    register_dataclass,
)
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine.facts import AttributeValue, CompositeValue
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import resolve

FIXTURE = Path(__file__).parents[1] / "fixtures" / "payload-construction"

# Field values each constructor must produce, derived from the KerML
# constructor rules rather than from the implementation: an argument binds
# the field its result feature redefines; an omitted field keeps the
# effective default of the constructed type, including an inherited one or
# the one a redefinition gives. Each value is (value, given as argument).
EXPECTED: dict[str, dict[str, tuple[int, bool]]] = {
    "positional": {"x": (7, True), "y": (42, True)},
    "defaults": {"x": (7, False), "y": (9, False)},
    "named": {"x": (7, False), "y": (42, True)},
    "inheritedDefaults": {"x": (7, False), "y": (9, False)},
    "inheritedNamed": {"x": (42, True), "y": (9, False)},
    "redefined": {"x": (7, False), "y": (11, False)},
    "redefinedNamed": {"x": (7, False), "y": (3, True)},
    "redefinedNoValue": {"x": (7, False), "y": (9, False)},
    "libraryDefaults": {"x": (7, False), "y": (9, False)},
    "libraryNamed": {"x": (7, False), "y": (42, True)},
    "libraryInherited": {"x": (42, True), "y": (9, False)},
    "solidAware": {"w": (2, False)},
    "diamond": {"v": (3, False)},
}


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(FIXTURE)


@pytest.fixture(scope="module")
def stdlib(model: syside.Model) -> syside.Stdlib:
    return syside.Stdlib(model.index)


def _send(model: syside.Model, transition: str) -> syside.SendActionUsage:
    sender = resolve(
        model, syside.StateDefinition, "PayloadConstruction::Sender"
    )
    for candidate in sender.owned_transitions.collect():
        if candidate.name == transition:
            action = candidate.effect_action
            assert isinstance(action, syside.SendActionUsage)
            return action
    raise AssertionError(f"no transition {transition!r}")


def _evaluate(expr: AttributeValue, stdlib: syside.Stdlib) -> object:
    assert isinstance(expr, syside.Expression)
    value, report = syside.Compiler().evaluate(expr, stdlib=stdlib)
    assert not report.diagnostics
    return value


def _render(value: AttributeValue, codegen: PythonCodeGen) -> str:
    # An unspecified value renders as the generated dataclasses' None.
    if value is None:
        return "None"
    if isinstance(value, CompositeValue):
        fields = ", ".join(
            f"{name}={_render(field, codegen)}" for name, field in value.fields
        )
        return f"{value.type_name}({fields})"
    assert isinstance(value, syside.Expression)
    return codegen.render_expression(value)


def _by_name(fields: list[PayloadField]) -> dict[str, PayloadField]:
    names = [field.name for field in fields]
    assert len(names) == len(set(names)), names
    return {field.name: field for field in fields}


@pytest.mark.parametrize("transition", list(EXPECTED))
def test_payload_fields_bind_arguments_and_type_values(
    model: syside.Model, stdlib: syside.Stdlib, transition: str
) -> None:
    fields = _by_name(payload_fields(_send(model, transition)))

    assert {
        name: (_evaluate(field.value, stdlib), field.explicit)
        for name, field in fields.items()
    } == EXPECTED[transition]


@pytest.mark.parametrize(
    "transition",
    [
        pytest.param(
            name,
            marks=pytest.mark.xfail(
                strict=True,
                reason="syside's scoped evaluator returns the redefining "
                "feature itself instead of the default it inherits from "
                "the redefined feature",
            ),
        )
        if name == "redefinedNoValue"
        else name
        for name in EXPECTED
    ],
)
def test_payload_fields_agree_with_scoped_evaluation(
    model: syside.Model, stdlib: syside.Stdlib, transition: str
) -> None:
    # Syside's scoped evaluator applies redefinitions within the evaluated
    # constructor value; it is a second oracle for constant constructors.
    send = _send(model, transition)
    payload = send.payload_argument
    assert payload is not None
    compiler = syside.Compiler()
    constructed, report = compiler.evaluate(payload, stdlib=stdlib)
    assert isinstance(constructed, syside.Type), report.diagnostics

    for field in payload_fields(send):
        scoped, _ = compiler.evaluate_feature(
            field.feature, constructed, stdlib=stdlib
        )
        assert scoped == _evaluate(field.value, stdlib), field.name


@pytest.mark.parametrize(
    ("transition", "names"),
    [
        ("defaults", ["x", "y"]),
        ("libraryDefaults", ["x", "y"]),
        ("solidAware", ["w"]),
    ],
)
def test_payload_fields_exclude_only_built_in_item_characteristics(
    model: syside.Model, transition: str, names: list[str]
) -> None:
    # Fields declared in a library package are application data; the
    # implicit Items::Item::isSolid is not, even where it is redefined.
    fields = payload_fields(_send(model, transition))

    assert [field.name for field in fields] == names


def test_explicit_arguments_keep_constructor_member_order(
    model: syside.Model,
) -> None:
    # Emitting entries in sequence must evaluate the arguments in the
    # constructor's member order, as before, not in the type's field order.
    send = _send(model, "reversed")

    assert [name for name, _ in payload_signature(send)[1]] == ["y", "x"]
    assert [(field.name, field.explicit) for field in payload_fields(send)] == [
        ("y", True),
        ("x", True),
    ]
    assert [
        (field.name, field.explicit)
        for field in payload_fields(_send(model, "named"))
    ] == [("y", True), ("x", False)]


def test_redefined_field_replaces_the_inherited_field_once(
    model: syside.Model,
) -> None:
    fields = payload_fields(_send(model, "redefined"))
    redefined = resolve(
        model, syside.AttributeUsage, "PayloadConstruction::Redefined::y"
    )

    assert [field.name for field in fields].count("y") == 1
    assert _by_name(fields)["y"].feature == redefined


def test_runtime_argument_remains_an_expression(model: syside.Model) -> None:
    fields = _by_name(payload_fields(_send(model, "runtime")))
    codegen = PythonCodeGen()

    assert fields["y"].explicit
    assert isinstance(fields["y"].value, syside.OperatorExpression)
    assert _render(fields["y"].value, codegen) == "counter + 1"
    assert _render(fields["x"].value, codegen) == "7"


def test_unvalued_field_is_unspecified(model: syside.Model) -> None:
    (field,) = payload_fields(_send(model, "unvalued"))

    assert (field.name, field.value, field.explicit) == ("n", None, False)


def test_omitted_structured_field_is_built_from_its_definition(
    model: syside.Model, stdlib: syside.Stdlib
) -> None:
    fields = _by_name(payload_fields(_send(model, "nestedOmitted")))
    sample = fields["sample"].value

    assert not fields["sample"].explicit
    assert isinstance(sample, CompositeValue)
    assert sample.definition == resolve(
        model, syside.AttributeDefinition, "PayloadConstruction::Sample"
    )
    level, spare = sample.fields
    assert (level[0], _evaluate(level[1], stdlib)) == ("level", 3)
    assert spare == ("spare", None)
    assert _evaluate(fields["value"].value, stdlib) == 1


def test_omitted_structured_field_applies_its_usage_redefinitions(
    model: syside.Model, stdlib: syside.Stdlib
) -> None:
    (field,) = payload_fields(_send(model, "usageOverride"))
    point = field.value

    assert isinstance(point, CompositeValue)
    assert point.definition == resolve(
        model, syside.AttributeDefinition, "PayloadConstruction::Point"
    )
    assert {name: _evaluate(value, stdlib) for name, value in point.fields} == {
        "x": 5,
        "y": 2,
    }


def test_distinct_fields_sharing_a_name_are_rejected(
    model: syside.Model,
) -> None:
    both = resolve(model, syside.ItemDefinition, "PayloadConstruction::Both")

    with pytest.raises(UnsupportedConstructError, match="two distinct fields"):
        payload_fields(_send(model, "sharedName"))
    with pytest.raises(UnsupportedConstructError, match="two distinct fields"):
        register_dataclass(both, DataclassRegistry(), lambda _: "None")


def test_argument_binding_a_non_attribute_feature_is_rejected(
    model: syside.Model,
) -> None:
    send = _send(model, "referenceArgument")

    with pytest.raises(ValueError, match="'who' does not bind"):
        payload_signature(send)
    with pytest.raises(ValueError, match="'who' does not bind"):
        payload_fields(send)


def test_omitted_recursive_structured_field_is_rejected(
    model: syside.Model,
) -> None:
    with pytest.raises(UnsupportedConstructError, match="recursive"):
        payload_fields(_send(model, "recursiveOmitted"))


def test_marker_payload_has_no_fields(model: syside.Model) -> None:
    assert payload_fields(_send(model, "marker")) == []
    assert payload_signature(_send(model, "marker")) == ("Marker", [])


def test_omitted_non_constant_type_value_is_rejected(
    model: syside.Model,
) -> None:
    with pytest.raises(
        UnsupportedConstructError,
        match="omits field 'PayloadConstruction::Derived::b'",
    ):
        payload_fields(_send(model, "derivedOmitted"))


def test_given_argument_replaces_a_non_constant_type_value(
    model: syside.Model, stdlib: syside.Stdlib
) -> None:
    fields = _by_name(payload_fields(_send(model, "derivedGiven")))

    assert (_evaluate(fields["b"].value, stdlib), fields["b"].explicit) == (
        5,
        True,
    )
    assert (_evaluate(fields["a"].value, stdlib), fields["a"].explicit) == (
        1,
        False,
    )


@pytest.mark.parametrize(
    ("transition", "expected"),
    [
        ("positional", ("Data", [("x", 7), ("y", 42)])),
        ("named", ("Data", [("y", 42)])),
        ("defaults", ("Data", [])),
        ("inheritedNamed", ("Child", [("x", 42)])),
        ("redefinedNamed", ("Redefined", [("y", 3)])),
    ],
)
def test_payload_signature_lists_arguments_by_bound_field(
    model: syside.Model,
    stdlib: syside.Stdlib,
    transition: str,
    expected: tuple[str, list[tuple[str, int]]],
) -> None:
    name, pairs = payload_signature(_send(model, transition))

    assert (
        name,
        [(field, _evaluate(argument, stdlib)) for field, argument in pairs],
    ) == expected


@pytest.mark.parametrize(
    ("definition", "fields"),
    [
        ("Child", ["    x: int = 7", "    y: int = 9"]),
        ("Redefined", ["    y: int = 11", "    x: int = 7"]),
        ("RedefinedNoValue", ["    y: int = 9", "    x: int = 7"]),
        ("Unvalued", ["    n: int = None"]),
        ("LibraryChild", ["    x: int = 7", "    y: int = 9"]),
        ("SolidAware", ["    w: int = 2"]),
        ("Diamond", ["    v: int = 3"]),
    ],
)
def test_dataclass_has_effective_fields_and_defaults(
    model: syside.Model, definition: str, fields: list[str]
) -> None:
    registry = DataclassRegistry()

    register_dataclass(
        resolve(
            model, syside.ItemDefinition, f"PayloadConstruction::{definition}"
        ),
        registry,
        PythonCodeGen().render_expression,
    )

    assert registry.class_blocks() == [
        "@dataclass",
        f"class {definition}:",
        *fields,
    ]


def test_non_literal_default_makes_a_required_keyword_field(
    model: syside.Model,
) -> None:
    # A backend may render an enumeration literal as a reference to a
    # generated class, which is not a literal the module can embed.
    def render(expr: syside.Expression) -> str:
        if isinstance(expr, syside.FeatureReferenceExpression):
            return "Mode.busy"
        return PythonCodeGen().render_expression(expr)

    registry = DataclassRegistry()
    register_dataclass(
        resolve(model, syside.ItemDefinition, "PayloadConstruction::Status"),
        registry,
        render,
    )

    assert registry.class_blocks() == [
        "@dataclass(kw_only=True)",
        "class Status:",
        "    m: object",
    ]
    name = "sysmlc_test_payload_required_types"
    module = GeneratedPythonModule.from_registry(name, registry)
    assert module is not None
    try:
        status = module.install().Status
        with pytest.raises(TypeError, match="'m'"):
            status()
        assert status(m="busy").m == "busy"
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize(
    ("transition", "counter", "expected"),
    [
        ("named", 0, {"x": 7, "y": 42}),
        ("defaults", 0, {"x": 7, "y": 9}),
        ("runtime", 5, {"x": 7, "y": 6}),
        ("reversed", 5, {"x": 7, "y": 6}),
    ],
)
def test_constructed_payload_executes_with_expected_values(
    model: syside.Model,
    transition: str,
    counter: int,
    expected: dict[str, int],
) -> None:
    # Render the construction as a backend would, with every valued field
    # passed by keyword, and execute it against the generated dataclass.
    send = _send(model, transition)
    codegen = PythonCodeGen()
    registry = DataclassRegistry()
    data = resolve(model, syside.ItemDefinition, "PayloadConstruction::Data")
    register_dataclass(data, registry, codegen.render_expression)
    arguments = ", ".join(
        f"{field.name}={_render(field.value, codegen)}"
        for field in payload_fields(send)
    )
    name = f"sysmlc_test_payload_{transition}_types"
    module = GeneratedPythonModule.from_registry(name, registry)
    assert module is not None
    try:
        namespace = {"Data": module.install().Data, "counter": counter}
        value = eval(f"Data({arguments})", namespace)
    finally:
        sys.modules.pop(name, None)

    assert vars(value) == expected


def test_constructed_nested_payload_executes_with_type_values(
    model: syside.Model,
) -> None:
    codegen = PythonCodeGen()
    registry = DataclassRegistry()
    measurement = resolve(
        model, syside.ItemDefinition, "PayloadConstruction::Measurement"
    )
    register_dataclass(measurement, registry, codegen.render_expression)
    arguments = ", ".join(
        f"{field.name}={_render(field.value, codegen)}"
        for field in payload_fields(_send(model, "nestedOmitted"))
    )
    name = "sysmlc_test_payload_nested_types"
    module = GeneratedPythonModule.from_registry(name, registry)
    assert module is not None
    try:
        value = eval(f"Measurement({arguments})", vars(module.install()))
    finally:
        sys.modules.pop(name, None)

    assert value.value == 1
    assert (value.sample.level, value.sample.spare) == (3, None)


def test_constructed_usage_override_executes_with_overridden_value(
    model: syside.Model,
) -> None:
    codegen = PythonCodeGen()
    registry = DataclassRegistry()
    located = resolve(
        model, syside.ItemDefinition, "PayloadConstruction::Located"
    )
    register_dataclass(located, registry, codegen.render_expression)
    arguments = ", ".join(
        f"{field.name}={_render(field.value, codegen)}"
        for field in payload_fields(_send(model, "usageOverride"))
    )
    name = "sysmlc_test_payload_usage_types"
    module = GeneratedPythonModule.from_registry(name, registry)
    assert module is not None
    try:
        value = eval(f"Located({arguments})", vars(module.install()))
    finally:
        sys.modules.pop(name, None)

    assert (value.p.x, value.p.y) == (5, 2)


@pytest.mark.parametrize("transition", ["explicitItem", "explicitItemChild"])
def test_explicit_item_base_keeps_only_application_fields(
    model: syside.Model, stdlib: syside.Stdlib, transition: str
) -> None:
    fields = payload_fields(_send(model, transition))

    assert [
        (field.name, _evaluate(field.value, stdlib)) for field in fields
    ] == [("x", 7)]
