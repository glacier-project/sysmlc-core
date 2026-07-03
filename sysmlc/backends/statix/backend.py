from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING, override

from sysmlc.backends.base import Backend, OutputOptions
from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.program import CProgram
from sysmlc.backends.statix.serialize import emit_files, to_c_preview
from sysmlc.errors import SerializationError

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

    @override
    def serialize(self, artifact: object, fmt: str) -> str:
        """Serialize the built program to concatenated C (``c`` format)."""
        if not isinstance(artifact, CProgram):
            raise SerializationError("expected a CProgram artifact")
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
        if not isinstance(artifact, CProgram):
            raise SerializationError("expected a CProgram artifact")
        out = options.output_dir
        out.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for name, content in emit_files(artifact).items():
            path = out / name
            path.write_text(content)
            written.append(path)
        written += self._copy_runtime(out)
        return written

    def _copy_runtime(self, out: Path) -> list[Path]:
        """Copy the bundled runtime kernel into the output project."""
        runtime = resources.files("sysmlc.backends.statix") / "runtime"
        copied: list[Path] = []
        for sub in ("include/sc", "src"):
            (out / sub).mkdir(parents=True, exist_ok=True)
            src_dir = runtime / sub
            for entry in src_dir.iterdir():
                if entry.name.endswith((".h", ".c")):
                    dest = out / sub / entry.name
                    dest.write_text(entry.read_text())
                    copied.append(dest)
        return copied

    @override
    def summary(self, artifact: object) -> str:
        """Return a one-line description of the built program."""
        if not isinstance(artifact, CProgram):
            return self.name
        return (
            f"C statechart {artifact.name!r}: {len(artifact.states)} states, "
            f"{len(artifact.transitions)} transitions, "
            f"{len(artifact.events)} events"
        )
