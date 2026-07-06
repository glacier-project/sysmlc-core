from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING, ClassVar, override

from sismic.model import Statechart

from sysmlc.backends.base import Backend, OutputOptions
from sysmlc.backends.quake import runner
from sysmlc.backends.quake.builder import build_statechart
from sysmlc.backends.quake.parts import QuakePartSystem, build_part_system
from sysmlc.backends.quake.serialize import to_plantuml, to_yaml
from sysmlc.errors import SerializationError, UnsupportedConstructError

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
    def build(
        self,
        model: syside.Model,
        element_qn: str,
        *,
        external: tuple[str, frozenset[str]] | None = None,
    ) -> object:
        """Build the Sismic statechart for the given state definition."""
        return build_statechart(model, element_qn, external=external)

    def build_part(
        self,
        model: syside.Model,
        usage_qn: str,
        *,
        target_options: tuple[tuple[str, str], ...] = (),
        external: tuple[str, frozenset[str]] | None = None,
    ) -> QuakePartSystem:
        """Build a connected part system for coordinated execution."""
        if target_options:
            raise UnsupportedConstructError(
                "quake part systems do not support LF target options"
            )
        return build_part_system(model, usage_qn, external=external)

    def run_state_def(
        self,
        model: syside.Model,
        state_def_qn: str,
        *,
        max_steps: int = 1000,
        until: float | None = None,
        external: tuple[str, frozenset[str]] | None = None,
    ) -> runner.RunReport:
        """Execute a state definition to quiescence."""
        return runner.run_state_def(
            model,
            state_def_qn,
            max_steps=max_steps,
            until=until,
            external=external,
        )

    def run_part_system(
        self,
        model: syside.Model,
        usage_qn: str,
        *,
        max_steps: int = 1000,
        until: float | None = None,
        external: tuple[str, frozenset[str]] | None = None,
    ) -> runner.RunReport:
        """Execute a connected part system to quiescence."""
        return runner.run_part_system(
            model,
            usage_qn,
            max_steps=max_steps,
            until=until,
            external=external,
        )

    @override
    def serialize(self, artifact: object, fmt: str) -> str:
        """Serialize the Sismic statechart to the requested format."""
        if not isinstance(artifact, Statechart):
            raise SerializationError("expected a sismic Statechart artifact")
        if fmt == "yaml":
            return to_yaml(artifact)
        if fmt == "plantuml":
            return to_plantuml(artifact)
        raise SerializationError(f"unsupported format: {fmt!r}")

    @override
    def write(self, artifact: object, options: OutputOptions) -> list[Path]:
        """Write a quake artifact to disk.

        Single statecharts are written as one flat file per requested format.
        Part systems are written as ``<basename>/routing.json`` plus one
        statechart file per part instance and requested format.
        """
        if isinstance(artifact, QuakePartSystem):
            return self._write_part_system(artifact, options)
        if not isinstance(artifact, Statechart):
            raise SerializationError(
                "expected a sismic Statechart or QuakePartSystem artifact"
            )
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

    def _write_part_system(
        self, artifact: QuakePartSystem, options: OutputOptions
    ) -> list[Path]:
        """Write one statechart file per instance plus a routing manifest."""
        formats = options.formats or tuple(self.formats())
        basename = options.basename or artifact.name
        system_dir = options.output_dir / basename
        system_dir.mkdir(parents=True, exist_ok=True)
        manifest = system_dir / "routing.json"
        manifest.write_text(
            json.dumps(_part_system_manifest(artifact), indent=2) + "\n"
        )
        written = [manifest]
        for node in artifact.graph.parts:
            statechart = artifact.statecharts[node.usage_name]
            for fmt in formats:
                path = system_dir / f"{node.usage_name}.{self._EXTENSIONS[fmt]}"
                path.write_text(self.serialize(statechart, fmt))
                written.append(path)
        return written

    @override
    def summary(self, artifact: object) -> str:
        """Return a one-line description of the built statechart."""
        if isinstance(artifact, QuakePartSystem):
            return (
                f"part system {artifact.name!r}: "
                f"{len(artifact.graph.parts)} parts, "
                f"{len(artifact.routes)} routes"
            )
        if not isinstance(artifact, Statechart):
            return self.name
        states = len(artifact.states)
        transitions = len(artifact.transitions)
        return (
            f"statechart {artifact.name!r}: "
            f"{states} states, {transitions} transitions"
        )


def _part_system_manifest(artifact: QuakePartSystem) -> dict[str, object]:
    """Return the JSON-serializable routing manifest."""
    return {
        "name": artifact.name,
        "instances": [
            {
                "name": node.usage_name,
                "definition": node.definition_name,
                "behavior": node.behaviors[0][1],
            }
            for node in artifact.graph.parts
        ],
        "routes": [asdict(route) for route in artifact.routes],
    }
