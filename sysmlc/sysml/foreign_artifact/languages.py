"""Language adapters used by the foreign artifact abstraction."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Final, Protocol

from sysmlc.errors import UnsupportedConstructError

_C_FUNCTION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?m)^\s*(?:[A-Za-z_]\w*\s+)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
)
_C_DECLARATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?m)^\s*(?:[A-Za-z_]\w*\s+)+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*;"
)


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

    def validate(self, source: str) -> None:
        """Accept C source as opaque text."""

    def function_names(self, source: str) -> frozenset[str]:
        """Return names of C function definitions."""
        return frozenset(
            match.group(1) for match in _C_FUNCTION_PATTERN.finditer(source)
        )


def c_function_declarations(source: str) -> tuple[str, ...]:
    """Return one prototype declaration per top-level C function definition.

    Each line is the function's own signature with the body dropped and a
    ``;`` in its place, in source order. Used to synthesize a companion
    header for C extracted from a ``TextualRepresentation`` body, where
    there is no user-authored file to carry one (see
    ``sysmlc.sysml.foreign_artifact.text_rep``).
    """
    declarations: list[str] = []
    for match in _C_FUNCTION_PATTERN.finditer(source):
        signature = match.group(0)
        signature = signature[: signature.rindex("{")].rstrip()
        declarations.append(f"{signature};")
    return tuple(declarations)


@dataclass(frozen=True)
class CHeaderLanguage:
    """Handle C header foreign artifacts.

    A header is a companion file (declarations, macros, types): it never
    *defines* a callable, so it is never itself the match target that
    backs a calc-def call -- a backend must check a ``"c"`` artifact for
    that. ``function_names`` here means "names this header *declares*",
    used instead to check that a backed calc def has a companion
    declaration available at all (a backend wanting a calc def backed by
    a ``.c``/``.h`` pair declares both, one as ``"c"`` and one as
    ``"c_h"``, and tells them apart by ``lang`` -- see ``sysmlc_statix``,
    the backend that actually needs the distinction).
    """

    name: str = "c_h"
    extension: str = "h"
    comment: str = "//"

    def validate(self, source: str) -> None:
        """Accept C header source as opaque text."""

    def function_names(self, source: str) -> frozenset[str]:
        """Return names of C function prototypes declared in this header."""
        return frozenset(
            match.group(1) for match in _C_DECLARATION_PATTERN.finditer(source)
        )


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
