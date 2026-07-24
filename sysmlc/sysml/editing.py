"""In-place model editing through syside's low-level API.

Overrides are applied in place on the loaded model: existing initializer
literals are mutated (or the literal node is replaced when its kind must
change), missing initializers and per-usage composite fields are created as
owned ``FeatureValue`` relationships and usage-local attributes (the type's
defaults are never touched), and quantity overrides written in SysML syntax
(``"90 [s]"``) are converted into the model's declared unit within the same
unit KIND. After editing, the user documents are re-run through syside's
sema+validation pipeline and any diagnostic fails the build.

Only ``default`` and ``:=`` initializers are overridable; a plain ``=``
binding is fixed by the model and refused — the same rule the language
applies to redefinitions.
"""

from __future__ import annotations

import syside

from sysmlc.errors import ValuesError
from sysmlc.semantics.statemachine.attributes import (
    is_scalar_quantity,
    nested_attributes,
)
from sysmlc.semantics.statemachine.triggers import evaluate_to_number
from sysmlc.sysml.quantities import (
    LITERAL_NODE_TYPES,
    QuantityProbe,
    quantity_parts,
)

type ValueScalar = bool | int | float | str
# A leaf scalar, or a nested mapping overriding a composite's fields.
type ValueNode = ValueScalar | dict[str, "ValueNode"]

_OVERRIDABLE_HINT = "only `default` and `:=` initial values can be overridden"


def value_rel(attr: syside.AttributeUsage) -> syside.FeatureValue | None:
    """Return the ``FeatureValue`` owned by *attr*, or ``None``."""
    for rel in attr.owned_relationships.collect():
        if isinstance(rel, syside.FeatureValue):
            return rel
    return None


def check_overridable(rel: syside.FeatureValue | None, name: str) -> None:
    """Raise :exc:`ValuesError` if *rel* is a fixed ``=`` binding."""
    if rel is not None and not (rel.is_default or rel.is_initial):
        raise ValuesError(
            f"{name!r} is bound with '=' (fixed by the model); "
            f"{_OVERRIDABLE_HINT}"
        )


def literal_class(value: ValueScalar) -> type[syside.Element]:
    """Return the syside literal class matching *value*'s Python type."""
    if isinstance(value, bool):  # bool before int: bool is an int
        return syside.LiteralBoolean
    if isinstance(value, int):
        return syside.LiteralInteger
    if isinstance(value, float):
        return syside.LiteralRational
    return syside.LiteralString


def set_literal_value(lit: syside.Element, value: ValueScalar) -> None:
    """Assign *value* to the literal node it is paired with.

    Callers guarantee the pairing: the node was chosen (or created) via
    ``literal_class(value)``, or *value* was previously read back from the
    same node. The per-kind narrowing makes that invariant visible to the
    type checker, since each literal class accepts only its own value type.
    """
    if isinstance(lit, syside.LiteralBoolean):
        assert isinstance(value, bool)
        lit.value = value
    elif isinstance(lit, syside.LiteralInteger):
        assert isinstance(value, int)
        lit.value = value
    elif isinstance(lit, syside.LiteralRational):
        assert isinstance(value, float)
        lit.value = value
    else:
        assert isinstance(lit, syside.LiteralString)
        assert isinstance(value, str)
        lit.value = value


def set_value(
    attr: syside.AttributeUsage, name: str, value: ValueScalar
) -> None:
    """Mutate the attribute's literal initializer, creating it if absent.

    Parsed structure cannot be replaced through the editing API (only
    mutated or extended), so an override that would change the literal's
    KIND is refused with a model-side hint.
    """
    rel = value_rel(attr)
    check_overridable(rel, name)
    if rel is None:
        # No initializer: create one. Typing errors (a string into a
        # `Real`) are left for revalidation — syside checks conformance.
        _new_rel, lit = attr.children.append(
            syside.FeatureValue, literal_class(value)
        )
        set_literal_value(lit, value)
        return
    existing = rel.value
    if (
        isinstance(existing, syside.LiteralRational)
        and isinstance(value, int | float)
        and not isinstance(value, bool)
    ):
        existing.value = float(value)  # keep the declared rational kind
        return
    if isinstance(existing, literal_class(value)):
        set_literal_value(existing, value)
        return
    if isinstance(existing, syside.LiteralInteger) and isinstance(value, float):
        raise ValuesError(
            f"override for {name!r} is fractional but the model declares "
            "an integer literal; declare the initial value as a rational "
            "(e.g. `2.0`) to allow it"
        )
    raise ValuesError(
        f"override for {name!r} does not match the kind of the model's "
        "literal initializer; change the model's declared value kind"
    )


def apply_attribute(
    model: syside.Model,
    attr: syside.AttributeUsage,
    name: str,
    value: ValueNode,
    probe: QuantityProbe,
) -> None:
    """Dispatch an override to the correct editing helper."""
    if isinstance(value, dict):
        apply_composite(model, attr, name, value, probe)
        return
    if is_scalar_quantity(attr):
        apply_quantity(model, attr, name, value, probe)
        return
    if nested_attributes(attr):
        raise ValuesError(
            f"attribute {name!r} is a composite; override its fields with "
            "a nested mapping"
        )
    set_value(attr, name, value)


def apply_composite(
    model: syside.Model,
    attr: syside.AttributeUsage,
    name: str,
    value: dict[str, ValueNode],
    probe: QuantityProbe,
) -> None:
    """Apply a mapping override to a composite attribute's fields."""
    fields = {
        field.name: field for field in nested_attributes(attr) if field.name
    }
    if not fields:
        raise ValuesError(
            f"attribute {name!r} is not a composite; give it a scalar"
        )
    local_names = {
        member.name
        for member in attr.owned_members.collect()
        if isinstance(member, syside.AttributeUsage) and member.name
    }
    for field_name, field_value in value.items():
        field = fields.get(field_name)
        if field is None:
            raise ValuesError(
                f"override {name}.{field_name} does not match a field of "
                f"attribute {name!r}"
            )
        label = f"{name}.{field_name}"
        if field_name in local_names:
            apply_attribute(model, field, label, field_value, probe)
            continue
        # The field lives on the attribute def: create a usage-LOCAL
        # value so the type's default stays untouched for other usages.
        check_overridable(value_rel(field), label)
        if isinstance(field_value, dict):
            raise ValuesError(
                f"override {label} nests deeper than the usage declares; "
                "declare the nested structure on the usage in the model"
            )
        if is_scalar_quantity(field):
            raise ValuesError(
                f"quantity field {label} has no usage-local initializer; "
                "declare one in the model to make it configurable"
            )
        _membership, local = attr.children.append(
            syside.OwningMembership, syside.AttributeUsage
        )
        local.declared_name = field_name
        set_value(local, label, field_value)


def apply_quantity(
    model: syside.Model,
    attr: syside.AttributeUsage,
    name: str,
    value: ValueScalar,
    probe: QuantityProbe,
) -> None:
    """Apply a scalar or SysML-string override to a quantity attribute."""
    rel = value_rel(attr)
    if rel is None or rel.value is None:
        raise ValuesError(
            f"quantity attribute {name!r} has no usage-local initializer "
            "to override; declare one in the model"
        )
    check_overridable(rel, name)
    expr = rel.value
    _magnitude, model_unit, model_kind = quantity_parts(
        expr, f"the initializer of {name!r}"
    )
    assert isinstance(expr, syside.OperatorExpression)  # shape-checked
    if isinstance(value, bool):
        raise ValuesError(
            f"override for quantity attribute {name!r} must be a number "
            "(model units) or a SysML quantity string like '90 [s]'"
        )
    if isinstance(value, int | float):
        # Magnitude in the model's declared unit.
        set_magnitude(expr, value, name)
        return
    user = probe.quantity(name)
    if user.kind_qn != model_kind:
        raise ValuesError(
            f"the override for {name!r} has unit kind {user.kind_qn}, but "
            f"the model declares {model_kind}; use a unit of the same kind"
        )
    if user.unit_qn == model_unit:
        set_magnitude(expr, user.magnitude, name)
        return
    if "temperature" in model_kind.lower():
        raise ValuesError(
            f"cannot convert the override for {name!r}: temperature units "
            "are affine (a ratio conversion would be wrong); use "
            f"{model_unit} directly"
        )
    scale = _unit_scale(model, expr, name)
    set_magnitude(expr, user.si / scale, name)


def _unit_scale(
    model: syside.Model, expr: syside.OperatorExpression, name: str
) -> float:
    """The SI value of ``1 [model unit]`` (linear units only)."""
    magnitude, _unit = expr.operands.collect()
    assert isinstance(magnitude, LITERAL_NODE_TYPES)
    original = magnitude.value
    set_literal_value(magnitude, type(original)(1))
    try:
        scale = evaluate_to_number(
            expr, syside.Compiler(), syside.Stdlib(model.index)
        )
    finally:
        set_literal_value(magnitude, original)
    if not scale:
        raise ValuesError(
            f"cannot determine the unit scale of {name!r}'s initializer"
        )
    return float(scale)


def set_magnitude(
    expr: syside.OperatorExpression, value: float | int, name: str
) -> None:
    """Set the magnitude literal of a quantity expression.

    Parsed literal nodes can only be mutated, not replaced, so a
    fractional magnitude cannot land in a model-declared integer.
    """
    magnitude, _unit = expr.operands.collect()
    if isinstance(magnitude, syside.LiteralRational):
        magnitude.value = float(value)
        return
    if isinstance(magnitude, syside.LiteralInteger):
        if float(value).is_integer():
            magnitude.value = int(value)
            return
        raise ValuesError(
            f"the override for {name!r} works out to the fractional "
            f"magnitude {float(value)!r}, but the model declares an "
            "integer; declare the default with a rational magnitude "
            "(e.g. `2.0 [min]`) or override in the declared unit"
        )
    raise ValuesError(
        f"the magnitude of {name!r}'s initializer is not a literal; "
        "declare it as one to make it configurable"
    )


def revalidate(model: syside.Model) -> None:
    """Re-run sema + validation on the edited user documents.

    Keeps the parse (``BuildState.Parsed``) so in-memory AST edits
    survive, and surfaces any diagnostic as a configuration error —
    syside checks value-type conformance for us.
    """
    documents = list(model.user_docs)
    for mutex in documents:
        with mutex.lock() as document:
            # Explicit per-document reset (sema_reset has no whole-index
            # form); BuildState.Parsed keeps the parse so AST edits survive.
            syside.sema_reset(document)
            document.build_state = syside.BuildState.Parsed
    pipeline = syside.make_pipeline(
        syside.PipelineOptions(static_index=model.index, lib=model.lib)
    )
    options = syside.ScheduleOptions(
        syside.ValidationTiming.OnType, force_revalidation=True
    )
    result = syside.Executor().run(pipeline.schedule(documents, options))
    errors = [
        diagnostic
        for results in result.diagnostics
        for stage in (results.parser, results.sema, results.validation)
        for diagnostic in stage
        if "error" in str(diagnostic.severity).lower()
    ]
    if errors:
        details = "; ".join(str(error) for error in errors[:5])
        raise ValuesError(f"the configured model is not valid SysML: {details}")
