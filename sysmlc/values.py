"""Load, select, and apply attribute initial-value overrides.

The values file is YAML whose nesting mirrors SysML qualified names —
``Pkg: {Def: {attr: value}}`` — so no ``::`` syntax appears in the file.

Overrides are applied by **editing the model sources at runtime**: each
override becomes a byte-span text edit (replacing an initializer
expression, or inserting a usage-local redefinition such as
``attribute pt : Point { attribute :>> x = 0.7; }``), the patched sources
are written to a temporary directory, and the model is reloaded from
there. Reloading re-validates the configured model with the language's own
rules — e.g. a ``=`` binding is fixed and cannot be redefined, while a
``default`` can.

Quantity overrides use SysML syntax (``"90 [s]"``); the text is inserted
verbatim after a unit-kind sanity check (a length cannot override a
duration), so no unit conversion ever happens — the configured model
simply declares the new quantity.
"""

from __future__ import annotations

import atexit
import json
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import syside
import yaml

from sysmlc.errors import SysmlcError
from sysmlc.semantics.statemachine.attributes import (
    is_scalar_quantity,
    nested_attributes,
)
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import iter_elements, resolve

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

type ValueScalar = bool | int | float | str
# A leaf scalar, or a nested mapping overriding a composite's fields.
type ValueNode = ValueScalar | dict[str, "ValueNode"]


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
    model_path: Path,
    element_qn: str,
    values: dict[str, ValueNode],
) -> syside.Model:
    """Apply value overrides by editing the model sources and reloading.

    Args:
        model: The originally loaded model (used to locate attributes and
            initializer spans).
        model_path: The file or directory the model was loaded from.
        element_qn: Qualified name of the state definition whose
            attributes the overrides target.
        values: Overrides from :func:`select_values`.

    Returns:
        A model reloaded from the patched sources. The temporary directory
        holding them is cleaned up at interpreter exit.

    Raises:
        ValuesError: For unknown attribute names, structure mismatches,
            unit-kind mismatches, or when the configured model fails to
            reload (e.g. overriding a fixed ``=`` binding).
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
    edits: list[_Edit] = []
    for name, value in values.items():
        attr = attributes.get(name)
        if attr is None:
            raise ValuesError(
                f"override {name!r} does not match an attribute of "
                f"{element_qn!r}"
            )
        edits += _attribute_edits(attr, name, value, probe)
    return _reload_patched(model_path, edits)


@dataclass(frozen=True)
class _Edit:
    """One byte-span replacement in a source file."""

    path: Path
    start: int
    end: int
    text: str


def _document_path(element: syside.Element) -> Path:
    url = str(element.document.url)
    return Path(url.removeprefix("file://").removeprefix("file:"))


def _span(element: syside.Element) -> tuple[int, int]:
    cst = element.cst_node
    assert cst is not None  # parsed elements always carry their syntax
    return cst.start_byte, cst.end_byte


def _is_usage_local(inner: syside.Element, usage: syside.Element) -> bool:
    """Whether ``inner``'s source text lies inside ``usage``'s declaration."""
    if _document_path(inner) != _document_path(usage):
        return False
    inner_start, inner_end = _span(inner)
    usage_start, usage_end = _span(usage)
    return usage_start <= inner_start and inner_end <= usage_end


def _attribute_edits(
    attr: syside.AttributeUsage,
    name: str,
    value: ValueNode,
    probe: _QuantityProbe,
) -> list[_Edit]:
    if isinstance(value, dict):
        return _composite_edits(attr, name, value, probe)
    if is_scalar_quantity(attr):
        return [_quantity_edit(attr, name, value, probe)]
    if nested_attributes(attr):
        raise ValuesError(
            f"attribute {name!r} is a composite; override its fields with "
            "a nested mapping"
        )
    text = _sysml_scalar(value)
    expr = attr.feature_value_expression
    if expr is not None and _is_usage_local(expr, attr):
        start, end = _span(expr)
        return [_Edit(_document_path(expr), start, end, text)]
    # No usage-local initializer: insert one before the closing ';'.
    keyword = (
        "default" if attr.direction is syside.FeatureDirectionKind.In else ":="
    )
    return [_insert_into_declaration(attr, f" {keyword} {text}")]


def _composite_edits(
    attr: syside.AttributeUsage,
    name: str,
    value: dict[str, ValueNode],
    probe: _QuantityProbe,
) -> list[_Edit]:
    fields = {
        field.name: field for field in nested_attributes(attr) if field.name
    }
    if not fields:
        raise ValuesError(
            f"attribute {name!r} is not a composite; give it a scalar"
        )
    edits: list[_Edit] = []
    redefinitions: list[str] = []
    for field_name, field_value in value.items():
        field = fields.get(field_name)
        if field is None:
            raise ValuesError(
                f"override {name}.{field_name} does not match a field of "
                f"attribute {name!r}"
            )
        if _is_usage_local(field, attr):
            edits += _attribute_edits(field, field_name, field_value, probe)
        else:
            # Field declared on the attribute def: redefine it on THIS
            # usage so the type's default stays untouched for other usages.
            redefinitions.append(_redefinition_text(field_name, field_value))
    if redefinitions:
        edits.append(_insert_body(attr, " ".join(redefinitions)))
    return edits


def _redefinition_text(name: str, value: ValueNode) -> str:
    if isinstance(value, dict):
        inner = " ".join(_redefinition_text(n, v) for n, v in value.items())
        return f"attribute :>> {name} {{ {inner} }}"
    return f"attribute :>> {name} = {_sysml_scalar(value)};"


def _insert_into_declaration(attr: syside.AttributeUsage, text: str) -> _Edit:
    """Insert ``text`` just before the declaration's closing ``;``."""
    path = _document_path(attr)
    start, end = _span(attr)
    tail = path.read_bytes()[start:end]
    if not tail.rstrip().endswith(b";"):
        raise ValuesError(
            f"cannot insert an initializer into attribute "
            f"{attr.name!r}: unsupported declaration shape"
        )
    semi = start + tail.rindex(b";")
    return _Edit(path, semi, semi, text)


def _insert_body(attr: syside.AttributeUsage, body: str) -> _Edit:
    """Turn ``attribute pt : Point;`` into ``… { <body> }`` (or extend)."""
    path = _document_path(attr)
    start, end = _span(attr)
    source = path.read_bytes()[start:end]
    stripped = source.rstrip()
    if stripped.endswith(b";"):
        semi = start + source.rindex(b";")
        return _Edit(path, semi, semi + 1, f" {{ {body} }}")
    if stripped.endswith(b"}"):
        brace = start + source.rindex(b"}")
        return _Edit(path, brace, brace, f" {body} ")
    raise ValuesError(
        f"cannot insert redefinitions into attribute {attr.name!r}: "
        "unsupported declaration shape"
    )


def _sysml_scalar(value: ValueScalar) -> str:
    """Render an override scalar as SysML literal text."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    return repr(value)


# -- quantities ------------------------------------------------------------

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
    for the kind check.
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
        self._exprs: dict[str, syside.Expression] | None = None

    def expression(self, name: str) -> syside.Expression:
        if self._exprs is None:
            self._exprs = self._parse()
        return self._exprs[name]

    def _parse(self) -> dict[str, syside.Expression]:
        names = [name for name, _ in self._strings]
        declarations = "\n".join(
            f"    attribute __v{i} = {text};"
            for i, (_, text) in enumerate(self._strings)
        )
        snippet = _PROBE_TEMPLATE.format(declarations=declarations)
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
        out: dict[str, syside.Expression] = {}
        for i, name in enumerate(names):
            expr = parsed[f"__v{i}"].feature_value_expression
            assert expr is not None
            out[name] = expr
        return out


def _unit_kind(expr: syside.Expression, what: str) -> str:
    """The unit kind (``ISQBase::DurationUnit``) of a quantity expression."""
    if (
        not isinstance(expr, syside.OperatorExpression)
        or expr.operator is not syside.Operator.Quantity
    ):
        raise ValuesError(
            f"{what} is not a measurement expression of the form "
            "'<number> [<unit>]'"
        )
    _magnitude, unit = expr.operands.collect()
    referent = getattr(unit, "referent", None)
    types = referent.types.collect() if referent is not None else []
    if not types:
        raise ValuesError(f"{what} has no resolvable measurement unit")
    return str(types[0].qualified_name)


def _quantity_edit(
    attr: syside.AttributeUsage,
    name: str,
    value: ValueScalar,
    probe: _QuantityProbe,
) -> _Edit:
    expr = attr.feature_value_expression
    if expr is None or not _is_usage_local(expr, attr):
        raise ValuesError(
            f"quantity attribute {name!r} has no usage-local initializer "
            "to override; declare one in the model"
        )
    if isinstance(value, bool):
        raise ValuesError(
            f"override for quantity attribute {name!r} must be a number "
            "(model units) or a SysML quantity string like '90 [s]'"
        )
    if isinstance(value, int | float):
        # Magnitude in the model's declared unit: replace just the literal.
        _unit_kind(expr, f"the initializer of {name!r}")  # shape check
        assert isinstance(expr, syside.OperatorExpression)
        magnitude, _unit = expr.operands.collect()
        start, end = _span(magnitude)
        return _Edit(_document_path(expr), start, end, repr(value))
    user_expr = probe.expression(name)
    user_kind = _unit_kind(user_expr, f"the override for {name!r}")
    model_kind = _unit_kind(expr, f"the initializer of {name!r}")
    if user_kind != model_kind:
        raise ValuesError(
            f"the override for {name!r} has unit kind {user_kind}, but the "
            f"model declares {model_kind}; use a unit of the same kind"
        )
    start, end = _span(expr)
    return _Edit(_document_path(expr), start, end, value)


# -- patch and reload ------------------------------------------------------


def _model_files(model_path: Path) -> Iterator[Path]:
    for file in syside.collect_files_recursively(str(model_path)):
        yield Path(file)


def _reload_patched(model_path: Path, edits: list[_Edit]) -> syside.Model:
    by_file: dict[Path, list[_Edit]] = {}
    for edit in edits:
        by_file.setdefault(edit.path.resolve(), []).append(edit)
    workdir = Path(tempfile.mkdtemp(prefix="sysmlc-configured-"))
    atexit.register(shutil.rmtree, workdir, ignore_errors=True)
    base = model_path if model_path.is_dir() else model_path.parent
    for file in _model_files(model_path):
        resolved = file.resolve()
        relative = (
            resolved.relative_to(base.resolve())
            if resolved.is_relative_to(base.resolve())
            else Path(file.name)
        )
        target = workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        content = file.read_bytes()
        for edit in sorted(
            by_file.get(resolved, []), key=lambda e: e.start, reverse=True
        ):
            content = (
                content[: edit.start] + edit.text.encode() + content[edit.end :]
            )
        target.write_bytes(content)
    logger.info("Configured model written to %s", workdir)
    try:
        return load_model(workdir)
    except ValueError as error:
        raise ValuesError(
            "the configured model is not valid SysML — the overrides may "
            f"violate the model's rules: {error}"
        ) from error
