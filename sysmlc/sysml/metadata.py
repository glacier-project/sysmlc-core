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
    """Find a specific metadata application on an element.

    Returns the first application if there is more than one; callers that
    must see every application an element carries (a ``@ForeignArtifact``
    applied once per language, say) want
    :func:`find_all_applied_metadata` instead.
    """
    for metadata in element.metadata.collect():
        if not isinstance(metadata, syside.MetadataUsage):
            continue
        if metadata.metadata_definition == metadata_definition:
            return metadata
    return None


def find_all_applied_metadata(
    element: syside.Element,
    metadata_definition: syside.MetadataDefinition,
) -> list[syside.MetadataUsage]:
    """Find every application of a metadata definition on an element."""
    return [
        metadata
        for metadata in element.metadata.collect()
        if isinstance(metadata, syside.MetadataUsage)
        and metadata.metadata_definition == metadata_definition
    ]


def elements_with_metadata[TElement: syside.Element](
    model: syside.Model,
    kind: type[TElement],
    metadata_definition: syside.MetadataDefinition,
) -> list[tuple[TElement, syside.MetadataUsage]]:
    """Return one (element, usage) pair per metadata application found.

    An element with several applications of ``metadata_definition`` (e.g.
    ``@ForeignArtifact`` applied once per language) yields one pair per
    application, not one pair for the element.
    """
    matches: list[tuple[TElement, syside.MetadataUsage]] = []
    for element in iter_elements(model, kind):
        for metadata in find_all_applied_metadata(element, metadata_definition):
            matches.append((element, metadata))
    return matches
