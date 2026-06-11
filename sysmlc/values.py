"""Load, select, and apply attribute initial-value overrides.

The values file is YAML whose nesting mirrors SysML qualified names —
``Pkg: {Def: {attr: value}}`` — so no ``::`` syntax appears in the file.

Overrides are applied **in place** on the loaded model through syside's
low-level editing API: existing initializer literals are mutated (or the
literal node is replaced when its kind must change), missing initializers
and per-usage composite fields are created as owned ``FeatureValue``
relationships and usage-local attributes (the type's defaults are never
touched), and quantity overrides written in SysML syntax (``"90 [s]"``)
are converted into the model's declared unit within the same unit KIND —
a length can never override a duration, and affine temperature units are
refused (their ratio conversion would be wrong). After editing, the user
documents are re-run through syside's sema+validation pipeline and any
diagnostic fails the build.

Only ``default`` and ``:=`` initializers are overridable; a plain ``=``
binding is fixed by the model and refused — the same rule the language
applies to redefinitions.

If :func:`configure_model` raises, the model may be partially edited;
reload it before further use.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import syside
import yaml

from sysmlc.errors import SysmlcError
from sysmlc.semantics.statemachine.attributes import (
    is_scalar_quantity,
    nested_attributes,
)
from sysmlc.semantics.statemachine.triggers import evaluate_to_number
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import iter_elements, resolve

logger = logging.getLogger(__name__)

type ValueScalar = bool | int | float | str
# A leaf scalar, or a nested mapping overriding a composite's fields.
type ValueNode = ValueScalar | dict[str, "ValueNode"]

_OVERRIDABLE_HINT = "only `default` and `:=` initial values can be overridden"


class ValuesError(SysmlcError):
    """Raised for an unreadable, ill-formed, or inapplicable values file."""


def load_values(path: Path) -> dict[str, object]:
    """Load a values file into its nested-mapping form.

    Args:
        path: The YAML file to read.

    Returns:
        The nested mapping (an empty file yields ``{}``).

    Raises:
        ValuesError: If the file cannot be parsed or its top level is not
            a mapping.
    """
    try:
        loaded = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise ValuesError(
            f"cannot parse values file {path}: {error}"
        ) from error
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValuesError(
            f"values file {path} must hold a mapping at the top level"
        )
    return loaded


def select_values(
    tree: dict[str, object], element_qn: str
) -> dict[str, ValueNode]:
    """Return the overrides nested under ``element_qn``'s name path.

    Args:
        tree: A nested mapping from :func:`load_values`.
        element_qn: Qualified name of the element being built; its
            ``::`` segments are walked through the nesting.

    Returns:
        A ``{attribute name: scalar or nested mapping}`` view; empty when
        the file does not mention the element.

    Raises:
        ValuesError: If the element's entry is not a mapping.
    """
    node: object = tree
    for segment in element_qn.split("::"):
        if not isinstance(node, dict) or segment not in node:
            return {}
        node = node[segment]
    if not isinstance(node, dict):
        raise ValuesError(
            f"the entry for {element_qn!r} must map attribute names to values"
        )
    return _check_value_nodes(node, element_qn)


def _check_value_nodes(
    node: dict[object, object], where: str
) -> dict[str, ValueNode]:
    out: dict[str, ValueNode] = {}
    for name, value in node.items():
        if not isinstance(name, str):
            raise ValuesError(
                f"override key {name!r} under {where!r} must "
                "be an attribute name"
            )
        if isinstance(value, dict):
            out[name] = _check_value_nodes(value, f"{where}::{name}")
        elif isinstance(value, bool | int | float | str):
            out[name] = value
        else:
            raise ValuesError(
                f"override {name!r} under {where!r} must be a scalar or a "
                "mapping of composite fields"
            )
    return out


def configure_model(
    model: syside.Model,
    element_qn: str,
    values: dict[str, ValueNode],
) -> syside.Model:
    """Apply value overrides in place and revalidate the model.

    Args:
        model: The loaded model to configure (edited in place).
        element_qn: Qualified name of the state definition whose
            attributes the overrides target.
        values: Overrides from :func:`select_values`.

    Returns:
        The same model, edited and revalidated.

    Raises:
        ValuesError: For unknown attribute names, structure mismatches,
            fixed ``=`` bindings, unit-kind mismatches, or when the
            configured model fails validation.
    """
    if not values:
        return model
    state_def = resolve(model, syside.StateDefinition, element_qn)
    attributes = {
        member.name: member
        for member in state_def.owned_members.collect()
        if isinstance(member, syside.AttributeUsage) and member.name
    }
    probe = _QuantityProbe(element_qn, values, attributes)
    for name, value in values.items():
        attr = attributes.get(name)
        if attr is None:
            raise ValuesError(
                f"override {name!r} does not match an attribute of "
                f"{element_qn!r}"
            )
        _apply_attribute(model, attr, name, value, probe)
    _revalidate(model)
    return model


# -- in-place edits ----------------------------------------------------------


def _apply_attribute(
    model: syside.Model,
    attr: syside.AttributeUsage,
    name: str,
    value: ValueNode,
    probe: _QuantityProbe,
) -> None:
    if isinstance(value, dict):
        _apply_composite(model, attr, name, value, probe)
        return
    if is_scalar_quantity(attr):
        _apply_quantity(model, attr, name, value, probe)
        return
    if nested_attributes(attr):
        raise ValuesError(
            f"attribute {name!r} is a composite; override its fields with "
            "a nested mapping"
        )
    _set_value(attr, name, value)


def _value_rel(attr: syside.AttributeUsage) -> syside.FeatureValue | None:
    for rel in attr.owned_relationships.collect():
        if isinstance(rel, syside.FeatureValue):
            return rel
    return None


def _check_overridable(rel: syside.FeatureValue | None, name: str) -> None:
    if rel is not None and not (rel.is_default or rel.is_initial):
        raise ValuesError(
            f"{name!r} is bound with '=' (fixed by the model); "
            f"{_OVERRIDABLE_HINT}"
        )


_LITERALS = (
    syside.LiteralBoolean,
    syside.LiteralInteger,
    syside.LiteralRational,
    syside.LiteralString,
)


def _literal_class(value: ValueScalar) -> type[syside.Element]:
    if isinstance(value, bool):  # bool before int: bool is an int
        return syside.LiteralBoolean
    if isinstance(value, int):
        return syside.LiteralInteger
    if isinstance(value, float):
        return syside.LiteralRational
    return syside.LiteralString


def _set_value(
    attr: syside.AttributeUsage, name: str, value: ValueScalar
) -> None:
    """Mutate the attribute's literal initializer, creating it if absent.

    Parsed structure cannot be replaced through the editing API (only
    mutated or extended), so an override that would change the literal's
    KIND is refused with a model-side hint.
    """
    rel = _value_rel(attr)
    _check_overridable(rel, name)
    if rel is None:
        # No initializer: create one. Typing errors (a string into a
        # `Real`) are left for revalidation — syside checks conformance.
        _new_rel, literal = attr.children.append(
            syside.FeatureValue, _literal_class(value)
        )
        assert isinstance(literal, _LITERALS)
        literal.value = value
        return
    existing = rel.value
    if (
        isinstance(existing, syside.LiteralRational)
        and isinstance(value, int | float)
        and not isinstance(value, bool)
    ):
        existing.value = float(value)  # keep the declared rational kind
        return
    if isinstance(existing, _literal_class(value)) and isinstance(
        existing, _LITERALS
    ):
        existing.value = value
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


def _apply_composite(
    model: syside.Model,
    attr: syside.AttributeUsage,
    name: str,
    value: dict[str, ValueNode],
    probe: _QuantityProbe,
) -> None:
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
            _apply_attribute(model, field, label, field_value, probe)
            continue
        # The field lives on the attribute def: create a usage-LOCAL
        # value so the type's default stays untouched for other usages.
        _check_overridable(_value_rel(field), label)
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
        _set_value(local, label, field_value)


# -- quantities --------------------------------------------------------------


@dataclass(frozen=True)
class _Quantity:
    """A parsed SysML quantity override."""

    magnitude: float
    si: float
    unit_qn: str
    kind_qn: str


_PROBE_TEMPLATE = """package __SysmlcValuesProbe {{
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::*;
{declarations}
}}
"""


class _QuantityProbe:
    """Parse SysML quantity strings by compiling them as a tiny model.

    All quantity-string overrides are declared in one probe package
    (``attribute __v0 = 90 [s];``), loaded lazily once, giving full SysML
    parsing — unit aliases, scientific notation — plus the unit referent
    for the kind check and the SI value for conversion.
    """

    def __init__(
        self,
        element_qn: str,
        values: dict[str, ValueNode],
        attributes: dict[str, syside.AttributeUsage],
    ) -> None:
        self._element_qn = element_qn
        self._strings: list[tuple[str, str]] = [
            (name, value)
            for name, value in values.items()
            if isinstance(value, str)
            and (attr := attributes.get(name)) is not None
            and is_scalar_quantity(attr)
        ]
        self._parsed: dict[str, _Quantity] | None = None

    def quantity(self, name: str) -> _Quantity:
        if self._parsed is None:
            self._parsed = self._parse()
        return self._parsed[name]

    def _parse(self) -> dict[str, _Quantity]:
        names = [name for name, _ in self._strings]
        declarations = "\n".join(
            f"    attribute __v{i} = {text};"
            for i, (_, text) in enumerate(self._strings)
        )
        snippet = _PROBE_TEMPLATE.format(declarations=declarations)
        out: dict[str, _Quantity] = {}
        with tempfile.TemporaryDirectory() as workdir:
            probe_file = Path(workdir) / "values_probe.sysml"
            probe_file.write_text(snippet)
            try:
                probe_model = load_model(workdir)
            except ValueError as error:
                raise ValuesError(
                    f"a quantity override for {self._element_qn!r} is not "
                    f"valid SysML: {error}"
                ) from error
            parsed = {
                e.name: e
                for e in iter_elements(probe_model, syside.AttributeUsage)
                if e.name and e.name.startswith("__v")
            }
            compiler = syside.Compiler()
            stdlib = syside.Stdlib(probe_model.index)
            for index, name in enumerate(names):
                expr = parsed[f"__v{index}"].feature_value_expression
                assert expr is not None
                magnitude, unit_qn, kind_qn = _quantity_parts(
                    expr, f"the override for {name!r}"
                )
                si = evaluate_to_number(expr, compiler, stdlib)
                if si is None:
                    raise ValuesError(
                        f"the override for {name!r} does not evaluate to "
                        "a number"
                    )
                assert isinstance(magnitude, _LITERALS)
                out[name] = _Quantity(
                    magnitude=float(magnitude.value),
                    si=float(si),
                    unit_qn=unit_qn,
                    kind_qn=kind_qn,
                )
        return out


def _quantity_parts(
    expr: syside.Expression, what: str
) -> tuple[syside.Element, str, str]:
    """Split a quantity expression into (magnitude literal, unit, kind)."""
    if (
        not isinstance(expr, syside.OperatorExpression)
        or expr.operator is not syside.Operator.Quantity
    ):
        raise ValuesError(
            f"{what} is not a measurement expression of the form "
            "'<number> [<unit>]'"
        )
    magnitude, unit = expr.operands.collect()
    referent = getattr(unit, "referent", None)
    types = referent.types.collect() if referent is not None else []
    if referent is None or not types:
        raise ValuesError(f"{what} has no resolvable measurement unit")
    return (
        magnitude,
        str(referent.qualified_name),
        str(types[0].qualified_name),
    )


def _apply_quantity(
    model: syside.Model,
    attr: syside.AttributeUsage,
    name: str,
    value: ValueScalar,
    probe: _QuantityProbe,
) -> None:
    rel = _value_rel(attr)
    if rel is None or rel.value is None:
        raise ValuesError(
            f"quantity attribute {name!r} has no usage-local initializer "
            "to override; declare one in the model"
        )
    _check_overridable(rel, name)
    expr = rel.value
    _magnitude, model_unit, model_kind = _quantity_parts(
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
        _set_magnitude(expr, value, name)
        return
    user = probe.quantity(name)
    if user.kind_qn != model_kind:
        raise ValuesError(
            f"the override for {name!r} has unit kind {user.kind_qn}, but "
            f"the model declares {model_kind}; use a unit of the same kind"
        )
    if user.unit_qn == model_unit:
        _set_magnitude(expr, user.magnitude, name)
        return
    if "temperature" in model_kind.lower():
        raise ValuesError(
            f"cannot convert the override for {name!r}: temperature units "
            "are affine (a ratio conversion would be wrong); use "
            f"{model_unit} directly"
        )
    scale = _unit_scale(model, expr, name)
    _set_magnitude(expr, user.si / scale, name)


def _unit_scale(
    model: syside.Model, expr: syside.OperatorExpression, name: str
) -> float:
    """The SI value of ``1 [model unit]`` (linear units only)."""
    magnitude, _unit = expr.operands.collect()
    assert isinstance(magnitude, _LITERALS)
    original = magnitude.value
    magnitude.value = type(original)(1)
    try:
        scale = evaluate_to_number(
            expr, syside.Compiler(), syside.Stdlib(model.index)
        )
    finally:
        magnitude.value = original
    if not scale:
        raise ValuesError(
            f"cannot determine the unit scale of {name!r}'s initializer"
        )
    return float(scale)


def _set_magnitude(
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


# -- revalidation ------------------------------------------------------------


def _revalidate(model: syside.Model) -> None:
    """Re-run sema + validation on the edited user documents.

    Keeps the parse (``BuildState.Parsed``) so in-memory AST edits
    survive, and surfaces any diagnostic as a configuration error —
    syside checks value-type conformance for us.
    """
    documents = list(model.user_docs)
    for mutex in documents:
        with mutex.lock() as document:
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
