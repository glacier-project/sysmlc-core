from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING, override

from sysmlc.backends.base import Backend, OutputOptions
from sysmlc.backends.statix.builder import build_statix, build_statix_project
from sysmlc.backends.statix.program import CProgram, CProject
from sysmlc.backends.statix.serialize import emit_project_files, to_c_preview
from sysmlc.errors import SerializationError
from sysmlc.sysml.queries import state_definitions

if TYPE_CHECKING:
    from pathlib import Path

    import syside


class StatixBackend(Backend):
    """Static-memory, Power-of-10 C backend for flat SysML state machines."""

    def __init__(self) -> None:
        super().__init__(
            name="statix",
            description=(
                "Generate static-memory, Power-of-10 C statechart projects "
                "from flat SysML state definitions."
            ),
            formats=(("c", "static-memory C statechart project"),),
        )

    @override
    def build(self, model: syside.Model, element_qn: str) -> object:
        """Build the flat C statechart program for the state definition."""
        return build_statix(model, element_qn)

    def build_model(self, model: syside.Model) -> CProject:
        """Build every state definition in ``model`` into one C project."""
        qns = tuple(
            str(state_def.qualified_name)
            for state_def in state_definitions(model)
        )
        if not qns:
            raise SerializationError("the model contains no state definition")
        return build_statix_project(model, qns)

    @override
    def serialize(self, artifact: object, fmt: str) -> str:
        """Serialize the built program to concatenated C (``c`` format)."""
        if not isinstance(artifact, (CProgram, CProject)):
            raise SerializationError("expected a CProgram or CProject artifact")
        if fmt == "c":
            return to_c_preview(artifact)
        raise SerializationError(f"unsupported format: {fmt!r}")

    @override
    def write(self, artifact: object, options: OutputOptions) -> list[Path]:
        """Write the generated project plus the bundled runtime kernel.

        Produces a self-contained C project under ``options.output_dir``: the
        generated ``.h``/``.c`` files, a ``CMakeLists.txt``, and a copy of the
        runtime ``include/`` and ``src/`` trees.
        """
        if isinstance(artifact, CProgram):
            project = CProject(programs=(artifact,))
        elif isinstance(artifact, CProject):
            project = artifact
        else:
            raise SerializationError("expected a CProgram or CProject artifact")
        out = options.output_dir
        out.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for name, content in emit_project_files(project).items():
            path = out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            written.append(path)
        written += self._copy_runtime(out)
        return written

    def _copy_runtime(self, out: Path) -> list[Path]:
        """Copy the bundled runtime kernel into the output project."""
        runtime = resources.files("sysmlc.backends.statix") / "runtime"
        copied: list[Path] = []
        dest_sub = "include/sc"
        (out / dest_sub).mkdir(parents=True, exist_ok=True)
        src_dir = runtime / "include" / "sc"
        for entry in src_dir.iterdir():
            if entry.name.endswith(".h"):
                dest = out / dest_sub / entry.name
                dest.write_text(entry.read_text())
                copied.append(dest)
        return copied

    @override
    def summary(self, artifact: object) -> str:
        """Return a one-line description of the built program."""
        if isinstance(artifact, CProject):
            return f"C project: {len(artifact.programs)} statecharts"
        if not isinstance(artifact, CProgram):
            return self.name
        return (
            f"C statechart {artifact.name!r}: {len(artifact.states)} states, "
            f"{len(artifact.transitions)} transitions, "
            f"{len(artifact.events)} events"
        )
