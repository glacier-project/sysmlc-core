from pathlib import Path

import pytest
import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions, bindings
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import AttributeValue, CompositeValue
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import feature_value_relationship, resolve
from sysmlc.values import configure_model
from tests.test_recording import RecordingBuilder

FIXTURE = Path(__file__).parent / "fixtures" / "bindings"


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(FIXTURE)


def _run(model: syside.Model, name: str) -> RecordingBuilder:
    builder = RecordingBuilder()
    StateMachineDriver(model).run(f"Bindings::{name}", builder)
    return builder


def _values(model: syside.Model, builder: RecordingBuilder) -> dict:
    compiler = syside.Compiler()
    stdlib = syside.Stdlib(model.index)

    def evaluate(value: AttributeValue) -> object:
        if isinstance(value, CompositeValue):
            return {name: evaluate(field) for name, field in value.fields}
        if isinstance(value, syside.Expression):
            result, report = compiler.evaluate(value, stdlib=stdlib)
            assert not report.fatal, report.diagnostics
            return result
        return value

    return {
        binding.name: evaluate(binding.value) for binding in builder.attributes
    }


def _assigned(builder: RecordingBuilder) -> set[str]:
    slots = [
        slot for state in builder.states for slot in state.executable_actions()
    ]
    slots += [transition.effect for transition in builder.transitions]
    return {
        str(slot.referent.qualified_name)
        for slot in slots
        if isinstance(slot, syside.AssignmentActionUsage)
        and slot.referent is not None
    }


def test_literal_constants_are_admitted(model: syside.Model) -> None:
    builder = _run(model, "Constants")
    values = _values(model, builder)
    mode = values.pop("mode")
    assert isinstance(mode, syside.EnumerationUsage)
    assert str(mode.qualified_name) == "Bindings::Mode::busy"
    assert values == {
        "flag": True,
        "count": 3,
        "ratio": 2.5,
        "label": "on",
        "negative": -4,
        "positive": 4,
        "doubleNegative": 4,
        # Valued literals, including one valued by another literal.
        "light": "g",
        "grade": -1.0,
        "rank": 4.0,
        "timeout": 120.0,
        "offset": -5.0,
        "limit": 7,
        "pt": {"x": 0.5},
        "gain": {"value": 1.0},
        "a": 1,
        "derivedOnce": 2,
        "tuned": 2,
        "bare": None,
    }


def test_initial_values_stay_assignable(model: syside.Model) -> None:
    builder = _run(model, "Constants")
    assert _assigned(builder) == {
        "Bindings::Constants::a",
        "Bindings::Constants::tuned",
        "Bindings::Constants::bare",
        "Bindings::Constants::derivedOnce",
    }
    # `:=` keeps its one-shot expression; it is not folded into a constant.
    (derived,) = [b for b in builder.attributes if b.name == "derivedOnce"]
    assert isinstance(derived.value, syside.OperatorExpression)


@pytest.mark.parametrize(
    ("machine", "feature", "kind"),
    [
        ("DynamicExpression", "DynamicExpression::b", "'='"),
        ("DynamicReference", "DynamicReference::b", "'='"),
        ("DynamicCall", "DynamicCall::b", "'='"),
        ("DynamicNot", "DynamicNot::b", "'='"),
        ("DynamicDefault", "DynamicDefault::b", "'default ='"),
        ("DynamicQuantity", "DynamicQuantity::delay", "'='"),
        ("DynamicField", "Scaled::twice", "'='"),
        ("DynamicNested", "DynamicNested::idle::local", "'='"),
        # Enumeration membership alone is not constancy.
        ("DynamicEnumeration", "DynamicEnumeration::k", "'='"),
        ("CyclicEnumeration", "CyclicEnumeration::k", "'='"),
        ("CallEnumeration", "CallEnumeration::k", "'='"),
    ],
)
def test_non_constant_binding_is_rejected(
    model: syside.Model, machine: str, feature: str, kind: str
) -> None:
    with pytest.raises(
        UnsupportedConstructError, match="not a literal constant"
    ) as error:
        _run(model, machine)
    node = error.value.node
    assert node is not None
    assert str(node.qualified_name) == f"Bindings::{feature}"
    assert f"bound with {kind}" in error.value.message


def test_evaluable_binding_is_still_rejected(model: syside.Model) -> None:
    # syside evaluates `b = a + 1` from a's initial value; that is not
    # evidence that b stays constant once a changes.
    machine = resolve(
        model, syside.StateDefinition, "Bindings::DynamicExpression"
    )
    (b,) = [a for a in machine.owned_attributes.collect() if a.name == "b"]
    assert b.feature_value_expression is not None
    value, report = syside.Compiler().evaluate(
        b.feature_value_expression, stdlib=syside.Stdlib(model.index)
    )
    assert not report.fatal
    assert value == 2
    with pytest.raises(UnsupportedConstructError, match="'b'"):
        _run(model, "DynamicExpression")


def test_initial_value_hint_needs_a_variable_feature(
    model: syside.Model,
) -> None:
    # An attribute definition's field cannot be initialized with `:=`.
    with pytest.raises(UnsupportedConstructError, match="'twice'") as error:
        _run(model, "DynamicField")
    assert "':='" not in error.value.message
    with pytest.raises(UnsupportedConstructError, match="'b'") as error:
        _run(model, "DynamicExpression")
    assert "Declare an initial value with ':='" in error.value.message


def test_bound_structured_attribute_is_rejected(model: syside.Model) -> None:
    with pytest.raises(UnsupportedConstructError, match="structured") as error:
        _run(model, "DynamicStructured")
    node = error.value.node
    assert node is not None
    assert str(node.qualified_name) == "Bindings::DynamicStructured::pt"


def test_inherited_binding_is_rejected(model: syside.Model) -> None:
    # `:>> k` has no value of its own: FixedBase's binding applies to it.
    with pytest.raises(
        UnsupportedConstructError, match="inherits a value bound"
    ) as error:
        _run(model, "InheritedBinding")
    assert "Bindings::FixedBase::k" in error.value.message


@pytest.mark.parametrize(
    ("machine", "container", "feature", "kind"),
    [
        ("InheritedFixed", "InheritedFixed", "FixedBase::k", "'='"),
        (
            "InheritedDefault",
            "InheritedDefault",
            "DefaultBase::j",
            "'default ='",
        ),
        # A hidden dynamic binding: `b = a + 1` inherited from DynamicBase.
        ("InheritedDynamic", "InheritedDynamic", "DynamicBase::b", "'='"),
        (
            "InheritedBySubstate",
            "InheritedBySubstate::idle",
            "FixedBase::k",
            "'='",
        ),
    ],
)
def test_inherited_bound_attribute_is_rejected(
    model: syside.Model, machine: str, container: str, feature: str, kind: str
) -> None:
    # Inherited attributes are not materialized: their bindings would be
    # dropped silently, so they are diagnosed instead.
    with pytest.raises(
        UnsupportedConstructError, match="inherited state attributes"
    ) as error:
        _run(model, machine)
    assert error.value.message.startswith(
        f"'Bindings::{container}' inherits attribute 'Bindings::{feature}', "
        f"which is bound with {kind}"
    )
    node = error.value.node
    assert node is not None
    assert str(node.qualified_name) == f"Bindings::{feature}"


def test_overridden_default_is_assignable(model: syside.Model) -> None:
    # The redefinition's own `:=` replaces DefaultBase's `default` value.
    builder = _run(model, "OverriddenDefault")
    assert _values(model, builder) == {"j": 5}
    assert _assigned(builder) == {"Bindings::OverriddenDefault::j"}


def test_redefined_default_is_a_constant(model: syside.Model) -> None:
    builder = _run(model, "RedefinedDefault")
    assert _values(model, builder) == {"j": 7}


@pytest.mark.parametrize(
    ("machine", "where", "target", "kind"),
    [
        ("WriteEntry", "`entry` action of state 'idle'", "WriteEntry", "'='"),
        (
            "WriteEntryBlock",
            "`entry` action of state 'idle'",
            "WriteEntryBlock",
            "'='",
        ),
        ("WriteDo", "`do` action of state 'idle'", "WriteDo", "'='"),
        ("WriteExit", "`exit` action of state 'idle'", "WriteExit", "'='"),
        ("WriteEffect", "transition from 'idle'", "WriteEffect", "'='"),
        (
            "WriteEffectBlock",
            "transition from 'idle'",
            "WriteEffectBlock",
            "'='",
        ),
        (
            "WriteDefault",
            "`entry` action of state 'idle'",
            "WriteDefault",
            "'default ='",
        ),
        (
            "WriteNested",
            "`entry` action of state 'outer::inner'",
            "WriteNested::outer",
            "'='",
        ),
    ],
)
def test_assignment_to_bound_feature_is_rejected(
    model: syside.Model, machine: str, where: str, target: str, kind: str
) -> None:
    with pytest.raises(UnsupportedConstructError, match="assigns") as error:
        _run(model, machine)
    message = error.value.message
    assert where in message
    assert f"'Bindings::{target}::k', which is bound with {kind}" in message
    node = error.value.node
    assert node is not None
    assert str(node.qualified_name) == f"Bindings::{target}::k"


def test_target_identity_is_not_its_name(model: syside.Model) -> None:
    # `equipment.k` shares the bound attribute's simple name only.
    builder = _run(model, "WriteSameName")
    assert _assigned(builder) == {"Bindings::Equipment::k"}


def test_bound_member_target_is_rejected(model: syside.Model) -> None:
    with pytest.raises(
        UnsupportedConstructError,
        match="'Bindings::Equipment::locked', which is bound",
    ):
        _run(model, "WriteBoundMember")


def test_mutable_member_through_bound_reference_is_admitted(
    model: syside.Model,
) -> None:
    # `equipment = spare` binds which occurrence is designated, not the
    # values of its members.
    builder = _run(model, "WriteThroughBoundReference")
    assert _assigned(builder) == {"Bindings::Equipment::free"}


def test_fixed_member_through_bound_reference_is_rejected(
    model: syside.Model,
) -> None:
    with pytest.raises(
        UnsupportedConstructError,
        match="assigns 'Bindings::Equipment::locked', which is bound with '='",
    ) as error:
        _run(model, "WriteFixedThroughBoundReference")
    node = error.value.node
    assert node is not None
    assert str(node.qualified_name) == "Bindings::Equipment::locked"


@pytest.mark.parametrize(
    ("machine", "target"),
    [
        ("ReplaceFromCall", "ReplaceFromCall::pt"),
        ("ReplaceNestedFromCall", "ReplaceNestedFromCall::h"),
        ("ReplaceChainedFromCall", "Envelope::point"),
        ("ReplaceFromOtherType", "ReplaceFromOtherType::pt"),
    ],
)
def test_replacement_that_may_change_a_fixed_field_is_rejected(
    model: syside.Model, machine: str, target: str
) -> None:
    with pytest.raises(
        UnsupportedConstructError, match="replaces the whole value"
    ) as error:
        _run(model, machine)
    assert f"'Bindings::{target}'" in error.value.message
    node = error.value.node
    assert node is not None
    assert str(node.qualified_name) == "Bindings::Point::x"


@pytest.mark.parametrize(
    ("machine", "assigned"),
    [
        (
            "ReplaceFromReference",
            {
                "Bindings::ReplaceFromReference::pt",
                "Bindings::Envelope::point",
            },
        ),
        # A constructed Point owns, and so keeps, its fixed `x`.
        ("ReplaceFromConstructor", {"Bindings::ReplaceFromConstructor::pt"}),
        # An explicitly given value replaces a `default` field, also one
        # the usage declares itself.
        ("ReplaceDefaultField", {"Bindings::ReplaceDefaultField::gain"}),
        (
            "ReplaceLocalDefaultField",
            {"Bindings::ReplaceLocalDefaultField::gain"},
        ),
        # Enumeration literals are values, not fields of the enumeration.
        ("ReplaceEnumeration", {"Bindings::ReplaceEnumeration::light"}),
    ],
)
def test_replacement_that_keeps_fixed_fields_is_admitted(
    model: syside.Model, machine: str, assigned: set[str]
) -> None:
    builder = _run(model, machine)
    slots = [
        action
        for state in builder.states
        for action in actions.inline_actions(state.entry_action)
    ]
    assert {
        str(slot.referent.qualified_name)
        for slot in slots
        if isinstance(slot, syside.AssignmentActionUsage)
        and slot.referent is not None
    } == assigned


@pytest.mark.parametrize(
    ("machine", "target", "field"),
    [
        (
            "ReplaceLocalFixedField",
            "ReplaceLocalFixedField::gain",
            "ReplaceLocalFixedField::gain::value",
        ),
        (
            "ReplaceNestedLocalFixedField",
            "ReplaceNestedLocalFixedField::rig",
            "ReplaceNestedLocalFixedField::rig::gain::value",
        ),
    ],
)
def test_replacement_of_a_usage_fixed_field_is_rejected(
    model: syside.Model, machine: str, target: str, field: str
) -> None:
    # `spare` conforms to the type, whose own field is only a default: the
    # usage's fixed 7.0 would become 1.0.
    with pytest.raises(
        UnsupportedConstructError,
        match=f"'Bindings::{target}', which fixes its own field 'value'",
    ) as error:
        _run(model, machine)
    node = error.value.node
    assert node is not None
    assert str(node.qualified_name) == f"Bindings::{field}"


def test_constructor_of_a_nested_fixed_field_is_rejected(
    model: syside.Model,
) -> None:
    # `new Holder()` leaves its point unset: the fixed Point::x is lost.
    with pytest.raises(
        UnsupportedConstructError, match="does not materialize"
    ) as error:
        _run(model, "ReplaceNestedFromConstructor")
    assert (
        "with a `new` 'Bindings::Holder', which does not own the field "
        "'Bindings::Point::x'"
    ) in error.value.message
    node = error.value.node
    assert node is not None
    assert str(node.qualified_name) == "Bindings::Point::x"


def test_constructor_cannot_override_a_fixed_field(tmp_path: Path) -> None:
    # Replacement admits `new` values because syside already rejects a
    # constructor argument for a field fixed with `=`.
    (tmp_path / "ctor.sysml").write_text(
        """package Ctor {
            private import ScalarValues::*;
            attribute def Point { attribute x : Real = 0.5; }
            state def Machine {
                attribute pt : Point;
                entry; then idle;
                state idle { entry assign pt := new Point(0.9); }
            }
        }
        """
    )
    with pytest.raises(ValueError, match="feature-value-overriding"):
        load_model(tmp_path)


def test_constant_predicate_rejects_non_library_unit(
    tmp_path: Path,
) -> None:
    (tmp_path / "units.sysml").write_text(
        """package Units {
            private import ISQ::*;
            private import MeasurementReferences::*;
            attribute <px> pixel : LengthUnit;
            attribute width : LengthValue = 3 [px];
        }
        """
    )
    units = load_model(tmp_path)
    width = resolve(units, syside.AttributeUsage, "Units::width")
    expression = width.feature_value_expression
    assert expression is not None
    assert not bindings.is_constant(expression)


# -- configured (edited) values ---------------------------------------------


def test_configured_unvalued_attribute_stays_assignable() -> None:
    model = configure_model(
        load_model(FIXTURE), "Bindings::Constants", {"bare": 9}
    )
    machine = resolve(model, syside.StateDefinition, "Bindings::Constants")
    (bare,) = [
        a for a in machine.owned_attributes.collect() if a.name == "bare"
    ]
    relationship = feature_value_relationship(bare)
    assert relationship is not None
    assert relationship.is_initial
    builder = _run(model, "Constants")
    assert _values(model, builder)["bare"] == 9
    assert "Bindings::Constants::bare" in _assigned(builder)


def test_configured_bound_default_stays_bound() -> None:
    model = configure_model(
        load_model(FIXTURE), "Bindings::Constants", {"limit": 11}
    )
    assert _values(model, _run(model, "Constants"))["limit"] == 11
    model = configure_model(
        load_model(FIXTURE), "Bindings::WriteDefault", {"k": 3}
    )
    with pytest.raises(UnsupportedConstructError, match="'default ='"):
        _run(model, "WriteDefault")


def test_configured_initial_value_stays_initial() -> None:
    model = configure_model(
        load_model(FIXTURE), "Bindings::Constants", {"a": 4, "tuned": 8}
    )
    builder = _run(model, "Constants")
    values = _values(model, builder)
    assert (values["a"], values["tuned"]) == (4, 8)
    assert {
        "Bindings::Constants::a",
        "Bindings::Constants::tuned",
    } <= _assigned(builder)


def test_configured_field_is_a_bound_constant() -> None:
    # An attribute's field is not variable: the created usage-local value
    # stays a binding, and its literal is admitted as a constant.
    model = configure_model(
        load_model(FIXTURE), "Bindings::Constants", {"gain": {"value": 3.0}}
    )
    machine = resolve(model, syside.StateDefinition, "Bindings::Constants")
    (gain,) = [
        a for a in machine.owned_attributes.collect() if a.name == "gain"
    ]
    (local,) = [
        member
        for member in gain.owned_members.collect()
        if isinstance(member, syside.AttributeUsage)
    ]
    relationship = feature_value_relationship(local)
    assert relationship is not None
    assert not relationship.is_initial
    assert _values(model, _run(model, "Constants"))["gain"] == {"value": 3.0}


def test_configured_field_protects_against_replacement() -> None:
    # Unconfigured, `gain := nextGain(gain)` replaces only a default field;
    # the configured usage-local value is fixed, so it is rejected.
    model = configure_model(
        load_model(FIXTURE),
        "Bindings::ReplaceDefaultField",
        {"gain": {"value": 3.0}},
    )
    with pytest.raises(
        UnsupportedConstructError,
        match="'Bindings::ReplaceDefaultField::gain', which fixes its own "
        "field 'value'",
    ):
        _run(model, "ReplaceDefaultField")
