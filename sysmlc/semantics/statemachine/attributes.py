from __future__ import annotations

from typing import TYPE_CHECKING, Final

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import states, triggers
from sysmlc.semantics.statemachine.facts import (
    AttributeDirection,
    AttributeValue,
    CompositeValue,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


_DIRECTIONS: Final[dict[syside.FeatureDirectionKind, AttributeDirection]] = {
    syside.FeatureDirectionKind.In: AttributeDirection.IN,
    syside.FeatureDirectionKind.Out: AttributeDirection.OUT,
    syside.FeatureDirectionKind.Inout: AttributeDirection.INOUT,
}


def direction_of(attr: syside.AttributeUsage) -> AttributeDirection:
    """Classify the attribute's declared direction (NONE if undirected)."""
    if attr.direction is None:
        return AttributeDirection.NONE
    return _DIRECTIONS[attr.direction]


def nested_attributes(
    attr: syside.AttributeUsage,
) -> list[syside.AttributeUsage]:
    """Return the attributes of ``attr``'s structured definition.

    An attribute is structured when its type resolves to an
    ``AttributeDefinition`` that owns attributes; it is scalar when its type
    resolves to a primitive ``DataType``.
    """
    nested: list[syside.AttributeUsage] = []
    for definition in attr.attribute_definitions.collect():
        if isinstance(definition, syside.AttributeDefinition):
            nested.extend(definition.owned_attributes.collect())
    return nested


def is_scalar_quantity(attr: syside.AttributeUsage) -> bool:
    """Whether ``attr``'s type is a scalar quantity value.

    A scalar quantity value (like ``DurationValue``) is a subtype of
    ``Quantities::ScalarQuantityValue``: it carries a unit and reduces to one
    number once that unit is normalized to SI base units.
    """
    for definition in attr.attribute_definitions.collect():
        if isinstance(
            definition, syside.AttributeDefinition
        ) and definition.specializes(("Quantities", "ScalarQuantityValue")):
            return True
    return False


def scope_attributes(
    container: syside.StateDefinition | syside.StateUsage,
) -> list[syside.AttributeUsage]:
    """Return the attributes directly declared in a state container.

    A ``StateDefinition`` exposes them as ``owned_attributes``; a ``StateUsage``
    exposes them as ``nested_attributes``.
    """
    if isinstance(container, syside.StateDefinition):
        return container.owned_attributes.collect()
    return container.nested_attributes.collect()


def iter_scope_attributes(
    container: syside.StateDefinition | syside.StateUsage,
) -> Iterator[
    tuple[
        syside.StateDefinition | syside.StateUsage,
        syside.AttributeUsage,
    ]
]:
    """Yield every ``(scope, attribute)`` pair under ``container``.

    Walks ``container`` and every substate; each yielded ``scope`` is the state
    container that directly declares the attribute.
    """
    for attr in scope_attributes(container):
        yield container, attr
    for substate in states.substates(container):
        yield from iter_scope_attributes(substate)


def bind_value(
    attr: syside.AttributeUsage,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
) -> AttributeValue:
    """Build an attribute's neutral runtime value.

    - a **scalar** attribute -> its initializer ``Expression`` node (or None);
    - a **scalar quantity** (``DurationValue`` and the like) -> its value in SI
      base units as a ``float`` (or None when it has no value);
    - a **composite** attribute -> a ``CompositeValue`` built recursively.

    Raises:
        UnsupportedConstructError: If a scalar-quantity value does not evaluate
            to a number, or a composite field has no value to bind.
    """
    nested = nested_attributes(attr)
    if not nested:
        return attr.feature_value_expression
    if is_scalar_quantity(attr):
        expr = attr.feature_value_expression
        if expr is None:
            return None
        number = triggers.evaluate_to_number(expr, compiler, stdlib)
        if number is None:
            raise UnsupportedConstructError(
                "scalar-quantity attribute value does not evaluate to a number",
                node=attr,
            )
        return float(number)
    fields: list[tuple[str, AttributeValue]] = []
    for field in nested:
        assert field.name is not None
        value = bind_value(field, compiler, stdlib)
        if value is None:
            raise UnsupportedConstructError(
                f"composite attribute field {field.name!r} has no value to "
                "bind; give it a default.",
                node=attr,
            )
        fields.append((field.name, value))
    return CompositeValue(tuple(fields))
