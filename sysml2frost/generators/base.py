from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Generator(ABC):
    """Abstract base class for artifact generators."""

    def __init__(self, output_dir: Path | str | None = None):
        """Initialize the generator with an optional output directory."""
        self._output_dir = None if output_dir is None else Path(output_dir)

    def _validate_output_folder(self) -> Path:
        """Validate and create the configured output directory.

        Returns:
            The configured output directory, created if it did not exist.

        Raises:
            ValueError: If no ``output_dir`` was configured, or if the
                configured path exists but is not a directory.
        """
        if self._output_dir is None:
            raise ValueError(
                "output_dir is required when writing generated artifacts"
            )
        if self._output_dir.exists() and not self._output_dir.is_dir():
            raise ValueError(
                f"output_dir {self._output_dir} exists but is not a directory"
            )
        self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir

    @abstractmethod
    def generate(self) -> None:
        """Generate target artifacts."""
