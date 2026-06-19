import logging
from pathlib import Path

import syside

logger = logging.getLogger(__name__)

_LIB_DIR = Path(__file__).resolve().parent / "lib"


def _bundled_library_files() -> list[Path]:
    """Absolute paths of the .sysml libraries shipped with sysmlc."""
    return sorted(_LIB_DIR.glob("*.sysml"))


def load_model(model_dir: Path | str) -> syside.Model:
    """Load a SysML model directory with syside.

    Args:
        model_dir: Directory containing SysML files.

    Returns:
        The loaded syside model.

    Raises:
        ValueError: If syside reports diagnostics.
    """
    logger.info("Loading SysML model from %s", model_dir)
    sysml_files = syside.collect_files_recursively(str(model_dir))
    sysml_files = _bundled_library_files() + list(sysml_files)
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
