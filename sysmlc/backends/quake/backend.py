from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

from sismic.io import export_to_plantuml, export_to_yaml
from sismic.model import Statechart

from sysmlc.backends.base import Backend, OutputOptions
from sysmlc.errors import SerializationError

from .builder import StatechartBuilder

if TYPE_CHECKING:
    from pathlib import Path

    import syside


class QuakeBackend(Backend):
    """Sismic-statechart backend for SysML state definitions."""

    _EXTENSIONS: ClassVar[dict[str, str]] = {"yaml": "yaml", "plantuml": "puml"}

    def __init__(self) -> None:
        super().__init__(
            name="quake",
            description=(
                "Generate Sismic statecharts from SysML state definitions."
            ),
            formats=(
                ("yaml", "YAML-serialized Sismic statechart"),
                ("plantuml", "PlantUML statechart diagram"),
            ),
        )

    @override
    def build(self, model: syside.Model, element_qn: str) -> object:
        """Build the Sismic statechart for the given state definition."""
        return StatechartBuilder(model, element_qn).build()

    @override
    def serialize(self, artifact: object, fmt: str) -> str:
        """Serialize the Sismic statechart to the requested format."""
        if not isinstance(artifact, Statechart):
            raise SerializationError("expected a sismic Statechart artifact")
        if fmt == "yaml":
            return str(export_to_yaml(artifact))
        if fmt == "plantuml":
            return str(export_to_plantuml(artifact))
        raise SerializationError(f"unsupported format: {fmt!r}")

    @override
    def write(self, artifact: object, options: OutputOptions) -> list[Path]:
        """Write the statechart as one flat file per requested format.

        Each format becomes ``<basename>.<ext>`` (``.yaml`` / ``.puml``) in
        ``options.output_dir``; the basename defaults to the statechart's own
        name and the formats default to every format the backend supports.
        """
        if not isinstance(artifact, Statechart):
            raise SerializationError("expected a sismic Statechart artifact")
        formats = options.formats or tuple(self.formats())
        basename = options.basename or artifact.name
        options.output_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for fmt in formats:
            text = self.serialize(artifact, fmt)
            path = options.output_dir / f"{basename}.{self._EXTENSIONS[fmt]}"
            path.write_text(text)
            written.append(path)
        return written

    @override
    def summary(self, artifact: object) -> str:
        """Return a one-line description of the built statechart."""
        if not isinstance(artifact, Statechart):
            return self.name
        states = len(artifact.states)
        transitions = len(artifact.transitions)
        return (
            f"statechart {artifact.name!r}: "
            f"{states} states, {transitions} transitions"
        )
