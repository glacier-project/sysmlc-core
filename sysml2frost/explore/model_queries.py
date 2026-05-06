from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

import syside
import syside.helpers

type QualifiedName = str | Sequence[str]

logger = logging.getLogger(__name__)


class SysideModelQueries:
    """Encapsulate model navigation queries over a loaded SysIDE model."""

    def __init__(self, model: syside.Model):
        """Initialize model queries.

        Args:
            model: Loaded SysIDE model.
        """
        self._model = model

    def resolve_element_by_qn[TElement: syside.Element](
        self,
        node_kind: type[TElement],
        qualified_name: QualifiedName,
    ) -> TElement:
        """Resolve a model element by kind and qualified name.

        Args:
            node_kind: SysIDE element class to search.
            qualified_name: Qualified name of the target element.

        Returns:
            Matching model element of the requested kind.

        Raises:
            ValueError: If no matching element exists.
        """
        normalized_qn = normalize_qualified_name(qualified_name)
        logger.info(
            "Resolving %s %s",
            node_kind.__name__,
            "::".join(normalized_qn),
        )
        for element in self._model.elements(
            node_kind,
            include_subtypes=True,
        ):
            if element.matches_qualified_name(normalized_qn):
                return element

        logger.error(
            "%s %s not found",
            node_kind.__name__,
            "::".join(normalized_qn),
        )
        raise ValueError(
            f"{node_kind.__name__} {'::'.join(normalized_qn)!r} not found"
        )

    def resolve_part_definition(
        self, qualified_name: QualifiedName
    ) -> syside.PartDefinition:
        """Resolve a part definition by qualified name.

        Args:
            qualified_name: Qualified name of the target definition.

        Returns:
            Matching part definition.

        Raises:
            ValueError: If the part definition is not found.
        """
        return self.resolve_element_by_qn(
            syside.PartDefinition,
            qualified_name,
        )

    def resolve_metadata_definition(
        self,
        qualified_name: QualifiedName,
    ) -> syside.MetadataDefinition:
        """Resolve a metadata definition by qualified name.

        Args:
            qualified_name: Qualified name of the metadata definition.

        Returns:
            Matching metadata definition.
        """
        return self.resolve_element_by_qn(
            syside.MetadataDefinition,
            qualified_name,
        )

    def find_applied_metadata(
        self,
        element: syside.Element,
        metadata_definition: syside.MetadataDefinition,
    ) -> syside.MetadataUsage | None:
        """Find a specific metadata application on an element.

        Args:
            element: Element whose metadata applications are inspected.
            metadata_definition: Metadata definition to look for.

        Returns:
            The matching ``MetadataUsage`` if present, otherwise ``None``.
        """
        for metadata in element.metadata.collect():
            if not isinstance(metadata, syside.MetadataUsage):
                continue
            if metadata.metadata_definition == metadata_definition:
                return metadata
        return None

    def iter_elements_with_metadata[TElement: syside.Element](
        self,
        node_kind: type[TElement],
        metadata_definition: syside.MetadataDefinition,
    ) -> list[tuple[TElement, syside.MetadataUsage]]:
        """Return all model elements annotated with a metadata definition.

        Args:
            node_kind: SysIDE element class to scan.
            metadata_definition: Metadata definition the elements must carry.

        Returns:
            List of ``(element, metadata_usage)`` pairs for every element of
            ``node_kind`` that has ``metadata_definition`` applied.
        """
        matches: list[tuple[TElement, syside.MetadataUsage]] = []
        for element in self._model.elements(node_kind):
            metadata = self.find_applied_metadata(element, metadata_definition)
            if metadata is not None:
                matches.append((element, metadata))
        return matches


def normalize_qualified_name(qualified_name: QualifiedName) -> tuple[str, ...]:
    """Normalize a qualified name to SysIDE's segment-based representation.

    Args:
        qualified_name: Qualified name as a ``"::"``-joined string or as a
            sequence of segments.

    Returns:
        Tuple of non-empty segments suitable for SysIDE matching APIs.
    """
    if isinstance(qualified_name, str):
        return tuple(
            segment for segment in qualified_name.split("::") if segment
        )
    return tuple(qualified_name)


def qualified_name_to_string(
    qualified_name: QualifiedName | Iterable[str] | None,
) -> str | None:
    """Normalize qualified name objects to plain strings.

    Args:
        qualified_name: Qualified name as a string, an iterable of segments,
            or ``None``.

    Returns:
        The qualified name as a ``"::"``-joined string, or ``None`` if the
        input was ``None``.
    """
    if qualified_name is None:
        return None
    if isinstance(qualified_name, str):
        return qualified_name
    return syside.helpers.qualified_name_to_str(qualified_name)
