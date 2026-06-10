from __future__ import annotations

from typing import TYPE_CHECKING

import syside

from sysmlc.sysml.queries import iter_elements, resolve

if TYPE_CHECKING:
    from sysmlc.sysml.names import QualifiedName


def resolve_part_definition(
    model: syside.Model, qualified_name: QualifiedName
) -> syside.PartDefinition:
    """Resolve a part definition by qualified name."""
    return resolve(model, syside.PartDefinition, qualified_name)


def resolve_metadata_definition(
    model: syside.Model, qualified_name: QualifiedName
) -> syside.MetadataDefinition:
    """Resolve a metadata definition by qualified name."""
    return resolve(model, syside.MetadataDefinition, qualified_name)


def find_applied_metadata(
    element: syside.Element,
    metadata_definition: syside.MetadataDefinition,
) -> syside.MetadataUsage | None:
    """Find a specific metadata application on an element."""
    for metadata in element.metadata.collect():
        if not isinstance(metadata, syside.MetadataUsage):
            continue
        if metadata.metadata_definition == metadata_definition:
            return metadata
    return None


def elements_with_metadata[TElement: syside.Element](
    model: syside.Model,
    kind: type[TElement],
    metadata_definition: syside.MetadataDefinition,
) -> list[tuple[TElement, syside.MetadataUsage]]:
    """Return all model elements annotated with a metadata definition."""
    matches: list[tuple[TElement, syside.MetadataUsage]] = []
    for element in iter_elements(model, kind):
        metadata = find_applied_metadata(element, metadata_definition)
        if metadata is not None:
            matches.append((element, metadata))
    return matches
