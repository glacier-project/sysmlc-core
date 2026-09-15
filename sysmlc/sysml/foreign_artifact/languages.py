"""Language adapters used by the foreign artifact abstraction."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Protocol

from sysmlc.errors import UnsupportedConstructError


class ForeignArtifactLanguage(Protocol):
    """Define the language operations needed by a foreign artifact."""

    @property
    def name(self) -> str:
        """Return the canonical language name."""

    @property
    def extension(self) -> str:
        """Return the generated artifact extension."""

    @property
    def comment(self) -> str:
        """Return the source comment prefix."""

    def validate(self, source: str) -> None:
        """Validate source code for this language."""

    def function_names(self, source: str) -> frozenset[str]:
        """Return callable names exposed by this artifact."""


@dataclass(frozen=True)
class PythonLanguage:
    """Handle Python foreign artifacts."""

    name: str = "python"
    extension: str = "py"
    comment: str = "#"

    def validate(self, source: str) -> None:
        """Validate Python source code."""
        ast.parse(source)

    def function_names(self, source: str) -> frozenset[str]:
        """Return top-level synchronous Python function names."""
        tree = ast.parse(source)
        return frozenset(
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        )


@dataclass(frozen=True)
class CLanguage:
    """Handle C foreign artifacts."""

    name: str = "c"
    extension: str = "c"
    comment: str = "//"
    _function_pattern: re.Pattern[str] = re.compile(
        r"(?m)^\s*(?:[A-Za-z_]\w*\s+)+([A-Za-z_]\w*)\s*"
        r"\([^;{}]*\)\s*\{"
    )

    def validate(self, source: str) -> None:
        """Accept C source as opaque text."""

    def function_names(self, source: str) -> frozenset[str]:
        """Return names of C function definitions."""
        return frozenset(
            match.group(1) for match in self._function_pattern.finditer(source)
        )


@dataclass(frozen=True)
class CHeaderLanguage:
    """Handle C header foreign artifacts.

    A header is a companion file (declarations, macros, types), never a
    match target for a calc-def call: it exposes no function names, even
    when it happens to contain an inline definition. A backend that wants
    a calc def backed by a ``.c``/``.h`` pair declares both, one as
    ``"c"`` and one as ``"c_h"``, and tells them apart by ``lang`` to
    place each correctly (e.g. a compiled source vs. an include-path-only
    header) -- see ``sysmlc_statix`` for the backend that actually needs
    the distinction.
    """

    name: str = "c_h"
    extension: str = "h"
    comment: str = "//"

    def validate(self, source: str) -> None:
        """Accept C header source as opaque text."""

    def function_names(self, source: str) -> frozenset[str]:
        """A header backs no calc-def match; always empty."""
        return frozenset()


_LANGUAGES: dict[str, ForeignArtifactLanguage] = {
    "python": PythonLanguage(),
    "c": CLanguage(),
    "c_h": CHeaderLanguage(),
}

SUPPORTED_LANG = tuple(_LANGUAGES)


def get_language(lang: str) -> ForeignArtifactLanguage:
    """Return the adapter registered for a language."""
    normalized = lang.strip().lower()
    try:
        return _LANGUAGES[normalized]
    except KeyError as error:
        raise UnsupportedConstructError(
            f"{lang} is not a supported foreign artifact language."
        ) from error


def register_language(language: ForeignArtifactLanguage) -> None:
    """Register or replace a foreign artifact language adapter."""
    _LANGUAGES[language.name.strip().lower()] = language
