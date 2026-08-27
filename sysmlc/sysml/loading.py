import logging
from importlib.metadata import entry_points
from pathlib import Path

import syside

logger = logging.getLogger(__name__)

_LIB_DIR = Path(__file__).resolve().parent / "lib"

# Installed packages ship additional .sysml libraries by registering a
# zero-argument callable under this entry-point group; the callable
# returns the absolute paths of its library files.
LIBRARY_ENTRY_POINT_GROUP = "sysmlc.libraries"


def _bundled_library_files() -> list[Path]:
    """Absolute paths of the .sysml libraries shipped with sysmlc."""
    return sorted(_LIB_DIR.glob("*.sysml"))


def provider_library_files() -> list[Path]:
    """Absolute paths of every installed provider's library files.

    Providers are ordered by entry-point name, so the combined list is
    deterministic regardless of installation order. A provider that
    fails to load or raises when called is skipped with a logged
    warning, so a single broken plugin cannot take every model load
    down. An exact duplicate path (the same file reached through two
    providers) is dropped, keeping the first occurrence; distinct files
    with clashing package names are not a discovery concern and surface
    as ordinary syside diagnostics.

    Returns:
        The providers' ``.sysml`` paths, providers ordered by
        entry-point name, exact duplicates dropped.
    """
    files: list[Path] = []
    seen: set[Path] = set()
    points = sorted(
        entry_points(group=LIBRARY_ENTRY_POINT_GROUP),
        key=lambda point: point.name,
    )
    for point in points:
        # a broken provider must not break model loading
        try:
            provider = point.load()
            provided = [Path(path) for path in provider()]
        except Exception as error:
            logger.warning(
                "Failed to load SysML library provider %r: %s",
                point.name,
                error,
            )
            continue
        for path in provided:
            if path in seen:
                continue
            seen.add(path)
            files.append(path)
    return files


def load_model(model_dir: Path | str) -> syside.Model:
    """Load a SysML model directory with syside.

    Every load also carries the bundled sysmlc library and the
    libraries of every installed ``sysmlc.libraries`` provider, so
    models may import provider packages without declaring where the
    files live.

    Args:
        model_dir: Directory containing SysML files.

    Returns:
        The loaded syside model.

    Raises:
        ValueError: If syside reports diagnostics.
    """
    logger.info("Loading SysML model from %s", model_dir)
    sysml_files = syside.collect_files_recursively(str(model_dir))
    sysml_files = (
        _bundled_library_files() + provider_library_files() + list(sysml_files)
    )
    logger.debug("Collected %d SysML files", len(sysml_files))
    model, diagnostics = syside.try_load_model(paths=sysml_files)

    warnings = list(diagnostics.warnings)
    if warnings:
        logger.warning(
            "syside reported %d warnings while loading the model",
            len(warnings),
        )

    if diagnostics.contains_errors():
        errors = list(diagnostics.errors)
        logger.error(
            "syside reported %d errors while loading the model", len(errors)
        )
        raise ValueError(
            "syside diagnostics reported problems:\n"
            f"{_format_diagnostic_messages(errors)}"
        )

    logger.info("Loaded SysML model successfully")
    return model


def _format_diagnostic_messages(
    diagnostics: list[syside.DiagnosticMessage],
) -> str:
    """Format diagnostic messages for exception reporting.

    Args:
        diagnostics: Diagnostic messages to format.

    Returns:
        A newline-delimited string of diagnostics.
    """
    return "\n".join(str(diagnostic) for diagnostic in diagnostics)
