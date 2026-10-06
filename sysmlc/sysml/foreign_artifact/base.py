"""Neutral foreign inputs and reusable model-source resolution policy."""

from __future__ import annotations

import keyword
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sysmlc.errors import SysmlcError
from sysmlc.sysml.foreign_artifact import c
from sysmlc.sysml.foreign_artifact.languages import (
    c_header_source,
    get_language,
)
from sysmlc.sysml.foreign_artifact.metadata import metadata_file_paths
from sysmlc.sysml.foreign_artifact.text_rep import extract_text_rep, write_file

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import syside


class ForeignArtifactError(SysmlcError):
    """A diagnostic for invalid foreign dependency input."""


@dataclass(frozen=True)
class ForeignArtifact:
    """One canonical file declaration; construction performs no source I/O."""

    path: Path
    lang: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", self.path.resolve())
        object.__setattr__(self, "lang", self.lang.strip().lower())

    @property
    def file_name(self) -> str:
        """Module stem used by consumers and generated imports."""
        return self.path.stem


@dataclass(frozen=True)
class ExternalDependency:
    """A neutral dependency declaration with canonical language and paths."""

    language: str
    files: tuple[Path, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "language", self.language.strip().lower())
        object.__setattr__(
            self, "files", tuple(dict.fromkeys(p.resolve() for p in self.files))
        )


def collect_foreign_dependencies(
    model_dir: Path,
    model: syside.Model,
    element_qn: str,
    languages: Sequence[str],
    *,
    overrides: Mapping[str, Sequence[Path]] | None = None,
) -> tuple[ExternalDependency, ...]:
    """Resolve neutral dependencies, applying per-language replacement first.

    Explicit files replace both metadata and representations in their language.
    Other languages remain additive. Repeated identical files are delivered once.

    Args:
        model_dir: Fallback origin for declarations without a file document.
        model: Loaded SysML model.
        element_qn: Selected element, or a whole-model output stem.
        languages: Languages consumed by the backend.
        overrides: Explicit files, grouped by language.

    Returns:
        Immutable declarations with absolute, existing file paths.

    Raises:
        ForeignArtifactError: If a file is missing or output names collide.
    """
    explicit = {
        lang.strip().lower(): tuple(paths)
        for lang, paths in (overrides or {}).items()
    }
    artifacts: list[ForeignArtifact] = []
    for lang in dict.fromkeys(value.strip().lower() for value in languages):
        get_language(lang)
        if explicit.get(lang):
            artifacts.extend(
                ForeignArtifact(path, lang) for path in explicit[lang]
            )
        else:
            artifacts.extend(parse_metadata(model_dir, model, lang))
            artifacts.extend(parse_text_rep(model, element_qn, lang))
    # A generated C companion is superseded by an explicit header input too.
    artifacts = [
        artifact
        for artifact in artifacts
        if not explicit.get(artifact.lang)
        or artifact.path in {p.resolve() for p in explicit[artifact.lang]}
    ]
    artifacts = validate_artifact_paths(artifacts)
    return tuple(
        ExternalDependency(
            lang, tuple(a.path for a in artifacts if a.lang == lang)
        )
        for lang in dict.fromkeys(a.lang for a in artifacts)
    )


def validate_artifact_paths(
    artifacts: Sequence[ForeignArtifact],
) -> list[ForeignArtifact]:
    """Deduplicate inputs and reject missing files or delivery-name collisions."""
    result = list(dict.fromkeys(artifacts))
    names: dict[str, Path] = {}
    for artifact in result:
        if not artifact.path.is_file():
            raise ForeignArtifactError(f"cannot read file {artifact.path}")
        name = artifact.path.name
        previous = names.setdefault(name, artifact.path)
        if previous != artifact.path:
            raise ForeignArtifactError(
                f"foreign files {previous} and {artifact.path} have the same "
                f"output filename {name!r}"
            )
    return result


def resolve_foreign_artifact(
    model_dir: Path,
    model: syside.Model,
    element_qn: str,
    lang: str = "python",
    *,
    overrides: Sequence[Path] = (),
) -> list[ForeignArtifact]:
    """Resolve one language using the shared replacement policy."""
    return [
        ForeignArtifact(path, dependency.language)
        for dependency in collect_foreign_dependencies(
            model_dir, model, element_qn, (lang,), overrides={lang: overrides}
        )
        for path in dependency.files
    ]


def parse_metadata(
    model_dir: Path, model: syside.Model, lang: str
) -> list[ForeignArtifact]:
    """Collect declarations, preserving each declaring document's directory."""
    return [
        ForeignArtifact(path, lang)
        for path in metadata_file_paths(model, lang, model_dir)
    ]


def parse_text_rep(
    model: syside.Model, element_qn: str, lang: str
) -> list[ForeignArtifact]:
    """Materialize representations with a C companion preserving type context."""
    lang = lang.strip().lower()
    text_rep = extract_text_rep(model, element_qn, lang)
    if not text_rep:
        return []
    file_name, source_lines = text_rep
    header = None
    if lang == "c":
        source = "\n".join(source_lines)
        try:
            header = c_header_source(source)
            source_lines = tuple(
                c.with_function_declarations(source).splitlines()
            )
        except SyntaxError as error:
            raise ForeignArtifactError(
                f"C representations for {element_qn!r}: {error}"
            ) from error
    out_dir = Path(tempfile.mkdtemp(prefix="sysmlc-reps-"))
    file_path = write_file(source_lines, out_dir, file_name, lang)
    artifacts = [ForeignArtifact(file_path, lang)]
    if header is not None:
        guard = re.sub(r"[^0-9A-Za-z]", "_", file_name).upper() + "_H"
        header_path = write_file(
            [f"#ifndef {guard}", f"#define {guard}", header, "#endif"],
            out_dir,
            file_name,
            "c_h",
        )
        artifacts.append(ForeignArtifact(header_path, "c_h"))
    return artifacts


def parse_raw_file(file_path: Path, lang: str) -> ForeignArtifact:
    """Declare a file without interpreting its language."""
    return ForeignArtifact(file_path, lang)


def parse_artifact(
    file_path: Path, lang: str = "python"
) -> tuple[str, frozenset[str]]:
    """Interpret source explicitly; called by consumers requiring symbols."""
    return file_path.stem, get_functions_names(file_path, lang)


def get_functions_names(
    module_path: Path, lang: str = "python"
) -> frozenset[str]:
    """Read and interpret a source file through its language helper."""
    try:
        return get_language(lang).function_names(module_path.read_text())
    except (OSError, SyntaxError) as error:
        raise ForeignArtifactError(
            f"file {module_path} is not valid: {error}"
        ) from error


def interpret_artifacts(
    artifacts: Sequence[ForeignArtifact],
    lang: str,
    *,
    unique_symbols: bool = True,
) -> dict[ForeignArtifact, frozenset[str]]:
    """Build a consumer's symbol map and reject ambiguous bindings."""
    lang = lang.strip().lower()
    selected = validate_artifact_paths([a for a in artifacts if a.lang == lang])
    symbols: dict[str, Path] = {}
    modules: dict[str, Path] = {}
    result: dict[ForeignArtifact, frozenset[str]] = {}
    for artifact in selected:
        if lang == "python" and (
            not artifact.file_name.isidentifier()
            or keyword.iskeyword(artifact.file_name)
        ):
            raise ForeignArtifactError(
                f"invalid Python module name {artifact.file_name!r}"
            )
        if lang == "python":
            previous_module = modules.setdefault(
                artifact.file_name, artifact.path
            )
            if previous_module != artifact.path:
                raise ForeignArtifactError(
                    f"duplicate Python module name {artifact.file_name!r}: "
                    f"{previous_module} and {artifact.path}"
                )
        names = get_functions_names(artifact.path, lang)
        if unique_symbols:
            for name in sorted(names):
                previous = symbols.setdefault(name, artifact.path)
                if previous != artifact.path:
                    raise ForeignArtifactError(
                        f"ambiguous {lang} function {name!r}: {previous} and {artifact.path}"
                    )
        result[artifact] = names
    return result
