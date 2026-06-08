from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping  # noqa: TC003
from typing import Any, ClassVar, TextIO

PACKAGE_LOGGER_NAME = "sysmlc"
DEFAULT_LOG_LEVEL = "WARNING"
_HANDLER_MARKER = "_sysmlc_handler"

_package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
_package_logger.addHandler(logging.NullHandler())


class PackageFormatter(logging.Formatter):
    """Formatter with optional ANSI colors for terminal output."""

    fmt = "%(levelname)s - %(name)s - %(message)s"
    reset_color = "\x1b[0m"
    colors: ClassVar[dict[int, str]] = {
        logging.DEBUG: "\x1b[38;21m",
        logging.INFO: "\x1b[38;5;39m",
        logging.WARNING: "\x1b[38;5;226m",
        logging.ERROR: "\x1b[38;5;196m",
        logging.CRITICAL: "\x1b[31;1m",
    }

    def __init__(self, use_color: bool = False) -> None:
        """Initialize the formatter.

        Args:
            use_color: Whether ANSI colors should be used.
        """
        super().__init__(self.fmt)
        self._formatters = (
            {
                level: logging.Formatter(color + self.fmt + self.reset_color)
                for level, color in self.colors.items()
            }
            if use_color
            else {}
        )

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record.

        Args:
            record: Log record to render.

        Returns:
            The formatted log message, optionally wrapped in ANSI colors.
        """
        formatter = self._formatters.get(record.levelno)
        if formatter is not None:
            return formatter.format(record)
        return super().format(record)


def configure_logging(
    level: int | str | None = None,
    config: Mapping[str, Any] | None = None,
    *,
    stream: TextIO | None = None,
    use_color: bool | None = None,
) -> logging.Logger:
    """Configure the package logger.

    Explicit level wins over config, which wins over environment, which wins
    over the package default.

    Args:
        level: Explicit logging level override.
        config: Optional configuration mapping with ``logging_level``.
        stream: Optional output stream for the package handler.
        use_color: Optional color override. If omitted, colors are enabled only
            when the selected stream is a TTY.

    Returns:
        The configured package logger.

    Raises:
        ValueError: If the requested logging level is invalid.
    """
    resolved_level = _resolve_log_level(level=level, config=config)
    selected_stream = stream or sys.stderr
    selected_use_color = (
        selected_stream.isatty() if use_color is None else use_color
    )

    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    logger.setLevel(resolved_level)
    logger.propagate = False

    handler = _get_package_handler(logger)
    if handler is None:
        handler = logging.StreamHandler(selected_stream)
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)

    handler.setLevel(logging.NOTSET)
    handler.setFormatter(PackageFormatter(use_color=selected_use_color))
    return logger


def setup_logging(
    level: int | str | None = None,
    config: Mapping[str, Any] | None = None,
    *,
    stream: TextIO | None = None,
    use_color: bool | None = None,
) -> logging.Logger:
    """Backward-compatible alias for :func:`configure_logging`.

    Args:
        level: Explicit logging level override.
        config: Optional configuration mapping with ``logging_level``.
        stream: Optional output stream for the package handler.
        use_color: Optional color override; auto-detected from ``stream``
            when omitted.

    Returns:
        The configured package logger.
    """
    return configure_logging(
        level=level,
        config=config,
        stream=stream,
        use_color=use_color,
    )


def _resolve_log_level(
    *,
    level: int | str | None,
    config: Mapping[str, Any] | None,
) -> int:
    configured_level = level
    if configured_level is None and config is not None:
        configured_level = config.get("logging_level")
    if configured_level is None:
        configured_level = os.getenv("SYSMLC_LOG_LEVEL", DEFAULT_LOG_LEVEL)

    if isinstance(configured_level, int):
        return configured_level

    if isinstance(configured_level, str):
        normalized_level = configured_level.strip().upper()
        level_mapping = logging.getLevelNamesMapping()
        if normalized_level in level_mapping:
            return level_mapping[normalized_level]

    raise ValueError(f"Invalid logging level: {configured_level!r}")


def _get_package_handler(logger: logging.Logger) -> logging.Handler | None:
    for handler in logger.handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            return handler
    return None
