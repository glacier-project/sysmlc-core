"""Load, select, and apply attribute initial-value overrides.

The values file is YAML whose nesting mirrors SysML qualified names —
``Pkg: {Def: {attr: value}}`` — so no ``::`` syntax appears in the file.

Overrides are applied **in place** on the loaded model through syside's
low-level editing API; see :mod:`sysmlc.sysml.editing` for the full
description of editing rules and constraints.

If :func:`configure_model` raises, the model may be partially edited;
reload it before further use.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import syside
import yaml

from sysmlc.errors import ValuesError as ValuesError
from sysmlc.sysml.editing import (
    ValueNode as ValueNode,
)
from sysmlc.sysml.editing import (
    ValueScalar as ValueScalar,
)
from sysmlc.sysml.editing import (
    apply_attribute,
    revalidate,
)
from sysmlc.sysml.quantities import QuantityProbe
from sysmlc.sysml.queries import is_scalar_quantity, resolve

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


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
    probe_strings = [
        (name, value)
        for name, value in values.items()
        if isinstance(value, str)
        and (attr := attributes.get(name)) is not None
        and is_scalar_quantity(attr)
    ]
    probe = QuantityProbe(element_qn, probe_strings)
    for name, value in values.items():
        attr = attributes.get(name)
        if attr is None:
            raise ValuesError(
                f"override {name!r} does not match an attribute of "
                f"{element_qn!r}"
            )
        apply_attribute(model, attr, name, value, probe)
    revalidate(model)
    return model
