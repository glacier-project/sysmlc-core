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
from sysmlc.sysml.queries import (
    definitions_of,
    feature_value,
    is_scalar_quantity,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_DIRECTIONS: Final[dict[syside.FeatureDirectionKind, AttributeDirection]] = {
    syside.FeatureDirectionKind.In: AttributeDirection.IN,
    syside.FeatureDirectionKind.Out: AttributeDirection.OUT,
    syside.FeatureDirectionKind.Inout: AttributeDirection.INOUT,
}


def direction_of(
    attr: syside.AttributeUsage | syside.ItemUsage,
) -> AttributeDirection:
    """Classify the attribute's declared direction (NONE if undirected)."""
    if attr.direction is None:
        return AttributeDirection.NONE
    return _DIRECTIONS[attr.direction]


def nested_attributes(
    attr: syside.AttributeUsage | syside.ItemUsage,
) -> list[syside.AttributeUsage]:
    """Return the attributes of ``attr``'s structured definition.

    An attribute is structured when its type resolves to an
    ``AttributeDefinition`` or ``ItemDefinition`` that owns attributes; it is
    scalar when its type resolves to a primitive ``DataType``.

    A usage-local attribute of the same name (a ``:>>`` redefinition giving
    THIS usage its own value) replaces the definition's field, so per-usage
    redefinitions win over the type's defaults.
    """
    nested: list[syside.AttributeUsage] = []
    for definition in definitions_of(attr):
        if isinstance(definition, syside.Definition):
            nested.extend(definition.owned_attributes.collect())
    if not nested:
        return nested
    # owned_members (not owned_features): the latter is sema-derived and
    # blind to members created through the low-level editing API.
    local = {
        member.name: member
        for member in attr.owned_members.collect()
        if isinstance(member, syside.AttributeUsage) and member.name
    }
    return [
        local.get(field.name, field) if field.name else field
        for field in nested
    ]


def scope_attributes(
    container: syside.StateDefinition | syside.StateUsage,
) -> list[syside.AttributeUsage | syside.ItemUsage]:
    """Return the attributes and items directly declared in a state container.

    A ``StateDefinition`` exposes them as ``owned_attributes``/``owned_items``;
    a ``StateUsage`` exposes them as ``nested_attributes``/``nested_items``.
    Items are included alongside attributes because a context declaration
    whose type is an ``ItemDefinition`` (e.g. a whole-payload capture buffer)
    must use ``item``, not ``attribute`` -- SysML reserves ``attribute`` for
    values, not occurrences.
    """
    if isinstance(container, syside.StateDefinition):
        return [
            *container.owned_attributes.collect(),
            *container.owned_items.collect(),
        ]
    return [
        *container.nested_attributes.collect(),
        *container.nested_items.collect(),
    ]


def iter_scope_attributes(
    container: syside.StateDefinition | syside.StateUsage,
) -> Iterator[
    tuple[
        syside.StateDefinition | syside.StateUsage,
        syside.AttributeUsage | syside.ItemUsage,
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
    attr: syside.AttributeUsage | syside.ItemUsage,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
) -> AttributeValue:
    """Build an attribute's neutral runtime value.

    - a **scalar** attribute -> its initializer ``Expression`` node (or None);
    - a **scalar quantity** (``DurationValue`` and the like) -> its value in SI
      base units as a ``float`` (or None when it has no value);
    - a **composite** attribute -> a ``CompositeValue`` built recursively.
    - an **item** (an occurrence, not a value) -> always ``None``; items carry
      no KerML default-value semantics, unlike attributes, so a bare
      ``item captured : Measurement;`` is a write-only placeholder rather
      than something to default-materialize. The caller (``_field``) turns a
      ``None`` composite-typed binding into a zero-initialized struct field.

    Raises:
        UnsupportedConstructError: If a scalar-quantity value does not evaluate
            to a number, or a composite field has no value to bind.
    """
    if isinstance(attr, syside.ItemUsage):
        return feature_value(attr)
    nested = nested_attributes(attr)
    if not nested:
        return feature_value(attr)
    if is_scalar_quantity(attr):
        expr = feature_value(attr)
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
    definition = next(
        (
            d
            for d in attr.attribute_definitions.collect()
            if isinstance(d, syside.Definition) and d.owned_attributes.collect()
        ),
        None,
    )
    if definition is None:
        raise UnsupportedConstructError(
            "composite attribute has fields but no structured definition "
            "could be resolved",
            node=attr,
        )
    assert definition.name is not None
    return CompositeValue(tuple(fields), definition.name, definition)
