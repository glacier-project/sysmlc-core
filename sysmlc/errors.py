from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import syside


class SysmlcError(Exception):
    """Base error for all sysmlc-specific exceptions."""

    pass


class ModelTraversalError(SysmlcError):
    """Raised when an error occurs during model traversal."""

    pass


class SerializationError(SysmlcError):
    """Raised when an error occurs during generated artifacts serialization."""

    pass

class CodeGenerationError(SysmlcError):
    """Raised when an error occurs during code generation.

    This error may optionally carry a reference to the AST/model node that
    triggered the problem. Its string form includes the node type and, when
    available, a resolved name or qualified name to aid debugging.
    """

    def __init__(
        self, message: str, node: syside.Element | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.node = node

    def __str__(self) -> str:
        if self.node is None:
            return self.message
        node = self.node

        node_type = type(node).__name__
        node_repr = (
            node.qualified_name or node.name or node.textual_representations
        )

        return f"{self.message} (node {node_type} {node_repr})"


class UnsupportedConstructError(CodeGenerationError):
    """Raised when the generator encounters a construct it doesn't support."""
