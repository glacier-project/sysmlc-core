from __future__ import annotations

import logging
from typing import TYPE_CHECKING, overload

import syside

if TYPE_CHECKING:
    from collections.abc import Sequence

from sysmlc.sysml.names import QualifiedName, normalize_qualified_name

logger = logging.getLogger(__name__)


def resolve[TElement: syside.Element](
    model: syside.Model,
    kind: type[TElement],
    qualified_name: QualifiedName,
) -> TElement:
    """Resolve a model element by kind and qualified name (MODEL-scoped)."""
    normalized = normalize_qualified_name(qualified_name)
    logger.info("Resolving %s %s", kind.__name__, "::".join(normalized))
    for element in model.elements(
        kind,
        include_subtypes=True,
        considered_document_kinds=syside.DocumentKind.MODEL,
    ):
        if element.matches_qualified_name(normalized):
            return element
    raise ValueError(f"{kind.__name__} {'::'.join(normalized)!r} not found")


@overload
def iter_elements(
    model: syside.Model,
    kind: None = ...,
    *,
    include_subtypes: bool = ...,
    considered_document_kinds: syside.DocumentKind = ...,
) -> Sequence[syside.Element]: ...


@overload
def iter_elements[TElement: syside.Element](
    model: syside.Model,
    kind: type[TElement],
    *,
    include_subtypes: bool = ...,
    considered_document_kinds: syside.DocumentKind = ...,
) -> Sequence[TElement]: ...


def iter_elements(
    model: syside.Model,
    kind: type[syside.Element] | None = None,
    *,
    include_subtypes: bool = True,
    considered_document_kinds: syside.DocumentKind = syside.DocumentKind.MODEL,
) -> Sequence[syside.Element]:
    """Return model elements of ``kind``, sorted for stable iteration."""
    if kind is None:
        kind = syside.Element
    return sorted(
        model.elements(
            kind,
            include_subtypes=include_subtypes,
            considered_document_kinds=considered_document_kinds,
        ),
        key=_element_sort_key,
    )


def state_definitions(model: syside.Model) -> Sequence[syside.StateDefinition]:
    """Return every state definition in the model, deterministically sorted."""
    return iter_elements(model, syside.StateDefinition)


def feature_value(attr: syside.AttributeUsage) -> syside.Expression | None:
    """Return the attribute's own value expression, if any.

    Reads the owned ``FeatureValue`` relationship first: syside's
    ``feature_value_expression`` accessor is blind to values created
    through the low-level editing API (in-memory configuration), while
    the relationship is authoritative for parsed and created values
    alike.
    """
    for rel in attr.owned_relationships.collect():
        if isinstance(rel, syside.FeatureValue):
            return rel.value
    return attr.feature_value_expression


def _element_sort_key(element: syside.Element) -> tuple[str, str, str]:
    qualified_name = element.qualified_name
    path = element.path
    name = element.name
    return (
        "" if qualified_name is None else str(qualified_name),
        str(path),
        "" if name is None else str(name),
    )
