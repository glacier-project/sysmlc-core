from __future__ import annotations

import logging

import syside

from sysml2frost.explore.traversal import iter_model_elements

logger = logging.getLogger(__name__)


class SysideVisitor:
    """Base visitor for traversing selected elements of a Syside model."""

    element_kind: type[syside.Element] = syside.Element
    include_subtypes: bool = True
    considered_document_kinds: syside.DocumentKind = syside.DocumentKind.MODEL

    def __init__(
        self,
        model: syside.Model,
        *,
        element_kind: type[syside.Element] | None = None,
        include_subtypes: bool | None = None,
        considered_document_kinds: syside.DocumentKind | None = None,
    ):
        """Initialize the visitor.

        Args:
            model: Loaded Syside model.
            element_kind: Optional Syside class to traverse.
            include_subtypes: Optional subtype traversal override.
            considered_document_kinds: Optional Syside document-kind filter.
        """
        self._model = model
        self._element_kind = element_kind or self.element_kind
        self._include_subtypes = (
            self.include_subtypes
            if include_subtypes is None
            else include_subtypes
        )
        self._considered_document_kinds = (
            self.considered_document_kinds
            if considered_document_kinds is None
            else considered_document_kinds
        )

    @property
    def model(self) -> syside.Model:
        """Return the visited Syside model."""
        return self._model

    def visit(self) -> None:
        """Traverse the model and dispatch each element to typed hooks."""
        self.start()
        for element in iter_model_elements(
            self._model,
            self._element_kind,
            include_subtypes=self._include_subtypes,
            considered_document_kinds=self._considered_document_kinds,
        ):
            logger.debug("Visiting %s", element)
            self._dispatch_element(element)
        self.end()

    def start(self) -> None:
        """Hook called before traversal starts."""

    def end(self) -> None:
        """Hook called after traversal ends."""

    def visit_element(self, element: syside.Element) -> None:
        """Hook called for every traversed element."""

    def visit_namespace(self, namespace: syside.Namespace) -> None:
        """Hook called for namespace elements."""

    def visit_package(self, package: syside.Package) -> None:
        """Hook called for package elements."""

    def visit_metadata_definition(
        self,
        metadata_definition: syside.MetadataDefinition,
    ) -> None:
        """Hook called for metadata definitions."""

    def visit_part_definition(
        self,
        part_definition: syside.PartDefinition,
    ) -> None:
        """Hook called for part definitions."""

    def visit_part_usage(self, part_usage: syside.PartUsage) -> None:
        """Hook called for part usages."""

    def visit_action_definition(
        self,
        action_definition: syside.ActionDefinition,
    ) -> None:
        """Hook called for action definitions."""

    def visit_action_usage(self, action_usage: syside.ActionUsage) -> None:
        """Hook called for action usages."""

    def visit_attribute_usage(
        self,
        attribute_usage: syside.AttributeUsage,
    ) -> None:
        """Hook called for attribute usages."""

    def visit_metadata_usage(
        self,
        metadata_usage: syside.MetadataUsage,
    ) -> None:
        """Hook called for metadata usages."""

    def _dispatch_element(self, element: syside.Element) -> None:
        self.visit_element(element)

        if isinstance(element, syside.MetadataDefinition):
            self.visit_metadata_definition(element)
        elif isinstance(element, syside.PartDefinition):
            self.visit_part_definition(element)
        elif isinstance(element, syside.PartUsage):
            self.visit_part_usage(element)
        elif isinstance(element, syside.ActionDefinition):
            self.visit_action_definition(element)
        elif isinstance(element, syside.ActionUsage):
            self.visit_action_usage(element)
        elif isinstance(element, syside.AttributeUsage):
            self.visit_attribute_usage(element)
        elif isinstance(element, syside.MetadataUsage):
            self.visit_metadata_usage(element)
        elif isinstance(element, syside.Package):
            self.visit_package(element)
        elif isinstance(element, syside.Namespace):
            self.visit_namespace(element)
