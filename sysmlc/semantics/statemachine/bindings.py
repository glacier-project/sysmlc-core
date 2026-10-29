"""Admission of bound (``=``) feature values in the compiled subset.

A bound feature value asserts that a feature equals its expression's result
at every snapshot; an initial value (``:=``) only provides the starting
value. The compiled subset materializes each value once, at initialization,
and maintains no equality at run time, so it admits only a narrow subset of
bound values that cannot change: literal constants. Writing a bound
feature, writing through a bound value, or replacing a structured value
with one that may change a field fixed with ``=`` is rejected instead of
silently breaking the equality. This is a supported-subset policy: SysML
itself does not forbid every assignment consistent with a binding.

A ``default =`` value binds the feature whenever the default applies, so it
follows the same rule; ``default :=`` is an initial value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions, states
from sysmlc.sysml.queries import feature_value, feature_value_relationship

if TYPE_CHECKING:
    from collections.abc import Iterator

_SIGNS: Final[frozenset[syside.Operator]] = frozenset(
    {syside.Operator.Minus, syside.Operator.Plus}
)


def effective_value_relationship(
    feature: syside.Feature,
) -> syside.FeatureValue | None:
    """Return the ``FeatureValue`` that applies to ``feature``, if any.

    The feature's own value comes first, including one created through the
    low-level editing API; otherwise the nearest value inherited through a
    redefinition applies.
    """
    owned = feature_value_relationship(feature)
    if owned is not None:
        return owned
    for membership in feature.inherited_memberships.collect():
        if isinstance(membership, syside.FeatureValue):
            return membership
    return None


def is_constant(expr: syside.Expression) -> bool:
    """Whether ``expr`` is a literal constant admitted as a bound value.

    Admits Boolean, Integer, Rational and String literals, unary numeric
    signs, literal quantities whose unit is a standard-library unit, and
    enumeration literals that are symbolic or whose own value is itself
    admitted. References to other features and calls are outside the
    admitted constant subset, even when syside can evaluate them from
    initial values.
    """
    return _is_constant(expr, set())


def require_supported_value(
    attr: syside.AttributeUsage | syside.ItemUsage,
    *,
    structured: bool = False,
) -> None:
    """Reject a bound value of ``attr`` outside the admitted constant subset.

    Unvalued attributes and initial (``:=``) values are always accepted.

    Args:
        attr: The attribute or item whose value is about to be bound.
        structured: Whether ``attr`` is materialized from its fields, so its
            own value expression is never rendered.

    Raises:
        UnsupportedConstructError: If a bound value applies to ``attr`` and
            it is inherited through a redefinition, binds a structured
            attribute, or is not a literal constant.
    """
    relationship = effective_value_relationship(attr)
    if relationship is None or relationship.is_initial:
        return
    kind = _kind(relationship)
    if feature_value_relationship(attr) is None:
        source = relationship.feature_with_value
        raise UnsupportedConstructError(
            f"attribute {attr.name!r} inherits a value bound with {kind} "
            f"from {_qualified(source)!r}; values inherited through a "
            "redefinition are not supported.",
            node=attr,
        )
    if structured:
        raise UnsupportedConstructError(
            f"structured attribute {attr.name!r} is bound with {kind}; only "
            "its fields' values are supported.",
            node=attr,
        )
    value = relationship.value
    if value is None or not is_constant(value):
        raise UnsupportedConstructError(
            f"attribute {attr.name!r} is bound with {kind} to an expression "
            "that is not a literal constant; a bound value is an equality "
            "that is not maintained at run time, so only Boolean, Integer, "
            "Rational and String literals, unary numeric signs, literal "
            "quantities and enumeration literals that are symbolic or have "
            f"such a value are supported.{_initial_hint(attr)}",
            node=attr,
        )


def require_no_inherited_bindings(
    container: syside.StateDefinition | syside.StateUsage,
) -> None:
    """Reject a bound value on an attribute a state container inherits.

    Only the attributes and items a state container declares itself are
    materialized, so an inherited, not redeclared, attribute would carry
    no value at all; a bound value on it is rejected rather than silently
    dropped. Unvalued and initial (``:=``) inherited attributes are not
    checked here.

    Args:
        container: A state definition or state usage; it and every
            substate below it are checked.

    Raises:
        UnsupportedConstructError: If an inherited attribute or item of
            ``container`` or of one of its substates has a bound value.
    """
    # Library types never specialize model types, so a container whose
    # direct generals are all library types inherits no model attribute.
    inherited = (
        container.features.collect()
        if any(
            specialization.general is not None
            and not specialization.general.is_library_element
            for specialization in container.owned_specializations.collect()
        )
        else []
    )
    for feature in inherited:
        if (
            not isinstance(feature, syside.AttributeUsage | syside.ItemUsage)
            or feature.is_library_element
            or feature.owning_type == container
        ):
            continue
        relationship = effective_value_relationship(feature)
        if relationship is not None and not relationship.is_initial:
            raise UnsupportedConstructError(
                f"{_qualified(container)!r} inherits attribute "
                f"{_qualified(feature)!r}, which is bound with "
                f"{_kind(relationship)}; inherited state attributes are not "
                "materialized, so their bound values are not supported.",
                node=feature,
            )
    for substate in states.substates(container):
        require_no_inherited_bindings(substate)


def require_assignable_actions(
    slot: syside.ActionUsage | None, where: str
) -> None:
    """Reject assignments in an action slot that write a bound feature.

    Args:
        slot: An ``entry``, ``do`` or ``exit`` action or a transition
            effect, in shorthand or block form, or None.
        where: Describes the slot in diagnostics, e.g. ``the `entry`
            action of state 'idle'``.

    Raises:
        UnsupportedConstructError: If an assignment in ``slot`` is rejected
            by ``require_assignable``, or if ``slot`` cannot be inspected as
            an inline action body.
    """
    for action in actions.inline_actions(slot):
        if isinstance(action, syside.AssignmentActionUsage):
            require_assignable(action, where)


def require_assignable(
    assign: syside.AssignmentActionUsage, where: str
) -> None:
    """Reject an assignment that writes, or writes through, a bound value.

    The target is identified by its resolved feature, never by name. An
    unresolved target is left to the code generator, which reports it.
    A bound occurrence reference on the target's chain still designates
    the same occurrence when one of its members changes, so only the
    assigned member and bound value prefixes are checked.

    Replacing a whole structured value must also keep every field fixed
    with ``=``. A field the target usage fixes itself, parsed or created
    through configuration, is not known to be kept by any replacement
    value, which is rejected. For a field its definitions fix, a value of a
    conforming definition read from a feature keeps it, and so does a
    ``new`` constructor of a definition that owns every such field
    directly, because syside rejects a constructor argument that overrides
    a fixed field; admitting a constructor here does not mean a backend
    can emit it. A constructor does not materialize the fixed fields of
    nested structured values, and any other value, such as a calculation
    result, may change them; both are rejected. A ``default`` field is not
    protected, because an explicitly given value replaces it. Only
    assignments in the model are checked; code outside the model, such as
    an external function, is not.

    Args:
        assign: The ``assign <target> := <expr>`` action to check.
        where: Describes the enclosing action slot in diagnostics.

    Raises:
        UnsupportedConstructError: If a bound value applies to the target
            feature or to a value feature on the target's chain, or if the
            assigned value may change a field fixed by the target usage or
            its definitions.
    """
    target = assign.referent
    if target is None:
        return
    relationship = effective_value_relationship(target)
    if relationship is not None and not relationship.is_initial:
        raise UnsupportedConstructError(
            f"{where} assigns {_qualified(target)!r}, which is bound with "
            f"{_kind(relationship)}; a bound value is a fixed equality, not "
            "a stored value, so assigning it is not supported."
            f"{_initial_hint(target)}",
            node=target,
        )
    for prefix in _chain_features(assign.target_argument):
        if _is_occurrence(prefix):
            continue
        relationship = effective_value_relationship(prefix)
        if relationship is not None and not relationship.is_initial:
            raise UnsupportedConstructError(
                f"{where} assigns {_qualified(target)!r} through "
                f"{_qualified(prefix)!r}, which is bound with "
                f"{_kind(relationship)}; writing through a bound value is "
                "not supported.",
                node=prefix,
            )
    local = next(_usage_fixed_fields(target), None)
    if local is not None:
        raise UnsupportedConstructError(
            f"{where} replaces the whole value of {_qualified(target)!r}, "
            f"which fixes its own field {local.name!r} with '='; no "
            "replacement value is known to keep a field fixed by the usage.",
            node=local,
        )
    definitions = _model_definitions(target)
    leaves = list(_fixed_fields(definitions, set()))
    if not leaves:
        return
    value = assign.value_expression
    sources: list[syside.Type] = [] if value is None else _value_types(value)
    if not all(
        any(source.specializes(definition) for source in sources)
        for definition in definitions
    ):
        raise UnsupportedConstructError(
            f"{where} replaces the whole value of {_qualified(target)!r}, "
            f"whose field {_qualified(leaves[0])!r} is bound with '='; only "
            "a value of the same definition, read from a feature or built "
            "with `new`, is known to keep that field.",
            node=leaves[0],
        )
    if isinstance(value, syside.ConstructorExpression):
        owned = sources[0].owned_features.collect()
        nested = next((leaf for leaf in leaves if leaf not in owned), None)
        if nested is not None:
            raise UnsupportedConstructError(
                f"{where} replaces the whole value of {_qualified(target)!r} "
                f"with a `new` {_qualified(sources[0])!r}, which does not "
                f"own the field {_qualified(nested)!r} bound with '='; a "
                "constructed value does not materialize the fixed fields of "
                "nested structured values.",
                node=nested,
            )


def _model_definitions(feature: syside.Feature) -> list[syside.Type]:
    """Return a feature's model-declared, non-enumeration definitions."""
    return [
        definition
        for definition in feature.types.collect()
        if isinstance(definition, syside.Definition)
        and not isinstance(definition, syside.EnumerationDefinition)
        and not definition.is_library_element
    ]


def _fixed_fields(
    definitions: list[syside.Type], seen: set[syside.Type]
) -> Iterator[syside.Feature]:
    """Yield the fields, at any depth, fixed by ``=`` in ``definitions``."""
    for definition in definitions:
        if definition in seen:
            continue
        seen.add(definition)
        for field in definition.features.collect():
            if (
                not isinstance(field, syside.AttributeUsage)
                or field.is_library_element
            ):
                continue
            if _is_fixed(effective_value_relationship(field)):
                yield field
            else:
                yield from _fixed_fields(_model_definitions(field), seen)


def _usage_fixed_fields(feature: syside.Feature) -> Iterator[syside.Feature]:
    """Yield the fields, at any depth, a usage itself fixes with ``=``.

    Reads ``owned_members``, as ``attributes.nested_attributes`` does, so a
    field created through the low-level editing API is included.
    """
    for member in feature.owned_members.collect():
        if not isinstance(member, syside.AttributeUsage):
            continue
        if _is_fixed(feature_value_relationship(member)):
            yield member
        else:
            yield from _usage_fixed_fields(member)


def _is_fixed(relationship: syside.FeatureValue | None) -> bool:
    """Whether ``relationship`` is a plain ``=`` binding."""
    return (
        relationship is not None
        and not relationship.is_initial
        and not relationship.is_default
    )


def _value_types(expr: syside.Expression) -> list[syside.Type]:
    """Return the types of a referenced or constructed value, else none."""
    if isinstance(expr, syside.ConstructorExpression):
        constructed = expr.instantiated_type
        return [] if constructed is None else [constructed]
    feature: syside.Feature | None = None
    if isinstance(expr, syside.FeatureChainExpression):
        tail = expr.target_feature
        if tail is not None:
            feature = (tail.chaining_features.collect() or [tail])[-1]
    elif isinstance(expr, syside.FeatureReferenceExpression):
        feature = expr.referent
    return [] if feature is None else feature.types.collect()


def _chain_features(expr: syside.Expression | None) -> list[syside.Feature]:
    """Return the resolved features a chained assignment target goes through."""
    if isinstance(expr, syside.FeatureChainExpression):
        operands = expr.operands.collect()
        features = _chain_features(operands[0]) if operands else []
        tail = expr.target_feature
        if tail is not None:
            features.extend(tail.chaining_features.collect() or [tail])
        return features
    if isinstance(expr, syside.FeatureReferenceExpression):
        referent = expr.referent
        return [] if referent is None else [referent]
    return []


def _is_occurrence(feature: syside.Feature) -> bool:
    """Whether ``feature`` is typed by an occurrence (item, part, ...)."""
    return any(
        isinstance(definition, syside.OccurrenceDefinition)
        for definition in feature.types.collect()
    )


def _is_constant(expr: syside.Expression, seen: set[syside.Feature]) -> bool:
    """Implement ``is_constant``; ``seen`` breaks enumeration value cycles."""
    if isinstance(expr, syside.LiteralBoolean | syside.LiteralString):
        return True
    if isinstance(expr, syside.FeatureReferenceExpression):
        return _is_constant_enumeration_literal(expr.referent, seen)
    return _is_numeric_constant(expr)


def _is_numeric_constant(expr: syside.Expression) -> bool:
    """Whether ``expr`` is a numeric literal, signed or with a library unit."""
    if isinstance(expr, syside.LiteralInteger | syside.LiteralRational):
        return True
    if not isinstance(expr, syside.OperatorExpression):
        return False
    operands = expr.operands.collect()
    if expr.operator in _SIGNS and len(operands) == 1:
        return _is_numeric_constant(operands[0])
    if expr.operator is syside.Operator.Quantity and len(operands) == 2:
        magnitude, unit = operands
        return (
            _is_numeric_constant(magnitude)
            and isinstance(unit, syside.FeatureReferenceExpression)
            and unit.referent is not None
            and unit.referent.is_library_element
        )
    return False


def _is_constant_enumeration_literal(
    feature: syside.Feature | None, seen: set[syside.Feature]
) -> bool:
    """Whether ``feature`` is an enumeration literal with a constant value.

    A symbolic literal is its own value. A valued literal stands for its
    value expression, which a backend may project in its place, so that
    expression must itself be admitted; a cycle of literal values is not.
    """
    if not isinstance(feature, syside.EnumerationUsage):
        return False
    owner = feature.owner
    if not (
        isinstance(owner, syside.EnumerationDefinition)
        and feature in owner.enumerated_values.collect()
    ):
        return False
    value = feature_value(feature)
    if value is None:
        return True
    if feature in seen:
        return False
    seen.add(feature)
    return _is_constant(value, seen)


def _initial_hint(feature: syside.Feature) -> str:
    """Suggest ``:=`` in diagnostics where a feature can be initialized."""
    if not feature.is_variable:
        return ""
    return " Declare an initial value with ':=' if the value may change."


def _kind(relationship: syside.FeatureValue) -> str:
    """Return the bound value's SysML notation for diagnostics."""
    return "'default ='" if relationship.is_default else "'='"


def _qualified(feature: syside.Element | None) -> str:
    """Return a feature's qualified name, or its name, for diagnostics."""
    if feature is None:
        return "<unresolved>"
    if feature.qualified_name is not None:
        return str(feature.qualified_name)
    return feature.name or "<anonymous>"
