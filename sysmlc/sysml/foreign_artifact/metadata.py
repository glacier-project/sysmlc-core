"""Evaluate foreign metadata without losing the declaring document origin."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml import metadata

FOREIGN_ARTIFACT_METADTA_QN = "ForeignArtifactBinding::ForeignArtifact"


def foreign_artifact_definition(
    model: syside.Model,
) -> syside.MetadataDefinition | None:
    """Resolve the bundled metadata definition, if present."""
    try:
        return metadata.resolve_metadata_definition(
            model, FOREIGN_ARTIFACT_METADTA_QN
        )
    except ValueError:
        return None


def _evaluate_field(
    usage: syside.MetadataUsage, name: str, model: syside.Model
) -> object:
    """Evaluate one metadata feature and surface compilation failures."""
    for feature in usage.owned_members.collect():
        if not isinstance(feature, syside.Feature) or feature.name != name:
            continue
        expression = feature.feature_value_expression
        if expression is None:
            continue
        value, report = syside.Compiler().evaluate(
            expression, stdlib=syside.Stdlib(model.index)
        )
        if report.fatal or any(
            diagnostic.severity == syside.DiagnosticSeverity.Error
            for diagnostic in report.diagnostics
        ):
            raise UnsupportedConstructError(
                f"cannot evaluate @ForeignArtifact {name}: {report.diagnostics}",
                node=usage,
            )
        return value
    return None


def _declarations(
    model: syside.Model, target_lang: str
) -> list[tuple[syside.MetadataUsage, tuple[str, ...]]]:
    """Evaluate and validate matching declarations in model order."""
    definition = foreign_artifact_definition(model)
    if definition is None:
        return []
    found: list[tuple[syside.MetadataUsage, tuple[str, ...]]] = []
    for _, usage in metadata.elements_with_metadata(
        model, syside.Element, definition
    ):
        lang = _evaluate_field(usage, "lang", model)
        if not isinstance(lang, str) or not lang.strip():
            raise UnsupportedConstructError(
                "@ForeignArtifact lang must evaluate to a nonempty string",
                node=usage,
            )
        if lang.strip().lower() != target_lang.strip().lower():
            continue
        raw = _evaluate_field(usage, "files", model)
        paths = [raw] if isinstance(raw, str) else raw
        if (
            (not isinstance(paths, list) and not isinstance(paths, tuple))
            or not paths
            or any(
                not isinstance(path, str) or not path.strip() for path in paths
            )
        ):
            raise UnsupportedConstructError(
                "@ForeignArtifact files must evaluate to a nonempty string or string sequence",
                node=usage,
            )
        found.append((usage, tuple(str(path) for path in paths)))
    return found


def get_foreign_artifact_filepath_from_metadata(
    model: syside.Model, target_lang: str = "python"
) -> tuple[str, ...] | None:
    """Return evaluated paths from all matching declarations."""
    paths = tuple(
        path
        for _, values in _declarations(model, target_lang)
        for path in values
    )
    return paths or None


def metadata_file_paths(
    model: syside.Model, target_lang: str, model_dir: Path
) -> tuple[Path, ...]:
    """Resolve each file relative to its declaring SysML document."""
    paths: list[Path] = []
    for usage, values in _declarations(model, target_lang):
        origin = model_dir
        if usage.document is not None:
            url = urlsplit(str(usage.document.url))
            if url.scheme == "file":
                if url.netloc not in ("", "localhost"):
                    raise UnsupportedConstructError(
                        f"unsupported foreign metadata document URL {usage.document.url}",
                        node=usage,
                    )
                origin = Path(unquote(url.path)).parent
        for raw in values:
            path = Path(raw)
            paths.append(
                (path if path.is_absolute() else origin / path).resolve()
            )
    return tuple(dict.fromkeys(paths))
