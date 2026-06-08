"""Command-line interface for ``sysmlc``."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from importlib.metadata import version
from typing import TYPE_CHECKING, Any

from .errors import SerializationError, SysmlcError

if TYPE_CHECKING:
    import syside

__all__ = ["main"]

logger = logging.getLogger("sysmlc.cli")
__version__ = version("sysmlc")

class CliError(SysmlcError):
    """A user-facing error, reported as a message without a traceback."""


_BACKENDS: dict[str, Backend] = {}

def _register(backend: Backend) -> None:
    _BACKENDS[backend.name] = backend

class Backend(ABC):
    """Abstract base class for a sysmlc backend that builds target artifacts.

    Each backend has a unique ``name`` and a human-friendly ``target``
    description. backends may optionally declare supported output ``formats``
    for serialization. The ``build`` method must be implemented to produce the
    target artifact for a given state definition. The ``serialize`` and ``run``
    methods may be overridden to support outputting the artifact in different
    formats or executing it, but by default they raise a ``CliError`` indicating
    the backend does not support those operations.
    """
    name: str
    description: str
    _options: dict[str, tuple[str, Any]]
    _formats: tuple[tuple[str, str], ...]

    def __init__(
            self,
            name: str, description: str,
            options: dict[str, tuple[str, Any]] | None = None,
            formats: tuple[tuple[str, str], ...] | None = None) -> None:
        self.name = name
        self.description = description
        self._options = options or {}
        self._formats = formats or ()

    @abstractmethod
    def build(self, model: syside.Model, element_qn: str) -> object:
        """Build the artifacts for the ``element_qn`` in the given model.

        Args:
            model: The loaded SysML model containing the state definition.
            element_qn: The qualified name of the state definition to build.

        Returns:
            An artifact object representing the built target, whose type is
            specific to the backend.
        """

    def options(self) -> list[str]:
        """Return the list of supported option strings for this backend."""
        return [opt for opt, _ in self._options]

    def default_options(self) -> dict[str, str]:
        """Return a dict of default option values for this backend."""
        return {opt: default for opt, (desc, default) in self._options.items()}

    def option_help(self) -> str:
        """Return a help string describing the supported options."""
        help_texts = [
            f"- {opt}: {desc} (default: {default})"
            for opt, (desc, default) in self._options.items()]
        return "\n".join(help_texts) if help_texts else "- no supported options"

    def formats(self) -> list[str]:
        """Return the list of supported format strings for this backend."""
        return [fmt for fmt, _ in self._formats]

    def default_format(self) -> str | None:
        """Return the default format string for this backend."""
        return self._formats[0][0] if self._formats else None

    def _format_help(self) -> str:
        """Return a help string describing the supported formats."""
        formats = [f"- {fmt}: {desc}" for fmt, desc in self._formats]
        return "\n".join(formats) if formats else "- no supported formats"

    def serialize(self, artifact: object, fmt: str) -> str:
        """Serialize a built artifact to text in the requested format."""
        raise SerializationError(
            f"backend {self.name!r} cannot serialize to {fmt!r}")

    def summary(self, artifact: object) -> str:
        """Return a one-line description of a built artifact."""
        return self.name

    def help(self) -> str:
        """Return a help string describing this backend's capabilities."""
        return (
            f"backend {self.name!r}: {self.description}\n"
            f"  options:\n{self.option_help()}\n"
            f"  formats:\n{self._format_help()}"
        )
