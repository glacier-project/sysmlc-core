from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Protocol

from sysmlc.errors import (
    BackendError,
    SerializationError,
    UnsupportedOperationError,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import syside

    from sysmlc.sysml.foreign_artifact.base import ForeignArtifact

logger = logging.getLogger(__name__)

BACKEND_ENTRY_POINT_GROUP = "sysmlc.backends"


class RunReport(Protocol):
    """The result of executing a model to quiescence.

    Backends return their own report type from the run operations; the CLI
    only relies on this structural contract.
    """

    @property
    def hit_step_cap(self) -> bool:
        """Whether the run stopped at the ``--max-steps`` safety cap."""
        ...

    def render(self) -> str:
        """Return a human-readable summary of the run."""
        ...


@dataclass(frozen=True)
class OutputOptions:
    """Where and in what formats a backend should write its artifact.

    These are the backend-agnostic output concerns the CLI owns. Backend-
    specific knobs do not belong here.

    Attributes:
        output_dir: Directory the backend writes its files into.
        formats: Selected output formats; empty means the backend's full set.
        basename: Base filename without extension; ``None`` lets the backend
            name the files itself.
    """

    output_dir: Path
    formats: tuple[str, ...] = ()
    basename: str | None = None


class Backend(ABC):
    """Abstract base class for a sysmlc backend that builds target artifacts.

    Each backend has a unique ``name`` and a human-friendly ``description``.
    Backends may optionally declare supported output ``formats`` for
    serialization. The ``build`` method must be implemented to produce the
    target artifact for a given state definition. The ``serialize`` and
    ``summary`` methods may be overridden to support outputting the artifact in
    different formats or describing it. By default ``serialize`` raises a
    ``SerializationError`` indicating the backend does not support that format.
    """

    name: str
    description: str
    _formats: tuple[tuple[str, str], ...]

    def __init__(
        self,
        name: str,
        description: str,
        formats: tuple[tuple[str, str], ...] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self._formats = formats or ()

    @abstractmethod
    def build(self, model: syside.Model, element_qn: str) -> object:
        """Build the artifact for the ``element_qn`` in the given model.

        Args:
            model: The loaded SysML model containing the state definition.
            element_qn: The qualified name of the state definition to build.

        Returns:
            An artifact object representing the built target, whose type is
            specific to the backend.
        """

    def build_kinds(self) -> frozenset[str]:
        """Return the optional build kinds this backend supports.

        Beyond the always-available single state-definition build
        (:meth:`build`), a backend supports a build kind by overriding the
        matching operation: ``"model"`` (:meth:`build_model`), ``"part"``
        (:meth:`build_part`), or ``"rig"`` (:meth:`build_composition`).
        Support is derived from those overrides, so it cannot drift from the
        implementation.
        """
        cls = type(self)
        kinds: set[str] = set()
        if cls.build_model is not Backend.build_model:
            kinds.add("model")
        if cls.build_part is not Backend.build_part:
            kinds.add("part")
        if cls.build_composition is not Backend.build_composition:
            kinds.add("rig")
        return frozenset(kinds)

    def run_kinds(self) -> frozenset[str]:
        """Return the run kinds this backend supports.

        A backend supports a run kind by overriding the matching operation:
        ``"statedef"`` (:meth:`run_state_def`) or ``"part"``
        (:meth:`run_part_system`). Support is derived from those overrides.
        """
        cls = type(self)
        kinds: set[str] = set()
        if cls.run_state_def is not Backend.run_state_def:
            kinds.add("statedef")
        if cls.run_part_system is not Backend.run_part_system:
            kinds.add("part")
        return frozenset(kinds)

    def build_model(self, model: syside.Model) -> object:
        """Build one artifact from the whole model (no single element)."""
        raise UnsupportedOperationError(
            f"backend {self.name!r} does not build a whole model"
        )

    def build_part(
        self,
        model: syside.Model,
        usage_qn: str,
        *,
        target_options: tuple[tuple[str, str], ...] = (),
        externals: list[ForeignArtifact] | None = None,
    ) -> object:
        """Build an artifact for a top-level part usage."""
        raise UnsupportedOperationError(
            f"backend {self.name!r} does not build part systems"
        )

    def build_composition(
        self,
        model: syside.Model,
        element_qn: str,
        *,
        external: list[ForeignArtifact] | None = None,
    ) -> object:
        """Build an artifact for a two-exhibit rig composition."""
        raise UnsupportedOperationError(
            f"backend {self.name!r} does not build compositions"
        )

    def run_state_def(
        self,
        model: syside.Model,
        element_qn: str,
        *,
        max_steps: int = 1000,
        until: float | None = None,
        external: list[ForeignArtifact] | None = None,
        load_external: Callable[[], None] | None = None,
    ) -> RunReport:
        """Execute a single state definition to quiescence.

        Args:
            model: The loaded SysML model.
            element_qn: Qualified name of the state definition to execute.
            max_steps: Safety cap on runtime macro steps.
            until: Optional simulated-time upper bound.
            external: Python module name and functions backing external calls.
            load_external: Callback that imports that module. Backends with
                generated Python runtime dependencies call it after preparing
                those dependencies and before starting execution.

        Returns:
            The backend-specific run report.
        """
        raise UnsupportedOperationError(
            f"backend {self.name!r} cannot run a state definition"
        )

    def run_part_system(
        self,
        model: syside.Model,
        element_qn: str,
        *,
        max_steps: int = 1000,
        until: float | None = None,
        external: list[ForeignArtifact] | None = None,
        load_external: Callable[[], None] | None = None,
    ) -> RunReport:
        """Execute a top-level part usage to quiescence.

        Args:
            model: The loaded SysML model.
            element_qn: Qualified name of the part usage to execute.
            max_steps: Safety cap on runtime macro steps.
            until: Optional simulated-time upper bound.
            external: Python module name and functions backing external calls.
            load_external: Callback that imports that module. Backends with
                generated Python runtime dependencies call it after preparing
                those dependencies and before starting execution.

        Returns:
            The backend-specific run report.
        """
        raise UnsupportedOperationError(
            f"backend {self.name!r} cannot run a part system"
        )

    def formats(self) -> list[str]:
        """Return the list of supported format strings for this backend."""
        return [fmt for fmt, _ in self._formats]

    def default_format(self) -> str | None:
        """Return the default format string for this backend."""
        return self._formats[0][0] if self._formats else None

    def format_help(self) -> str:
        """Return a help string describing the supported formats."""
        template = "- {fmt}{default}: {desc}"
        help_texts = []
        for fmt, desc in self._formats:
            default = " (default)" if fmt == self.default_format() else ""
            help_texts.append(
                template.format(fmt=fmt, default=default, desc=desc)
            )

        return "\n".join(help_texts) if help_texts else "- no supported formats"

    def help(self) -> str:
        """Return a help string describing this backend."""
        return (
            f"{self.name}: {self.description}\n\n"
            f"Supported formats:\n{self.format_help()}"
        )

    def consumes_python_support(self) -> bool:
        """Whether the backend consumes a ``--python`` file and model reps.

        A backend that emits Python (statechart guards, reactor reactions)
        backs external calc-def calls with a Python support file and
        materializes the model's Python textual representations. When False,
        the CLI omits the ``--python`` flag for this backend.
        """
        return False

    def defers_python_support_loading(self) -> bool:
        """Whether the backend controls when Python support is imported.

        Backends that generate Python modules needed by the support file
        return True, then invoke the ``load_external`` callback accepted by
        their run operation after those generated modules are ready. The
        default preserves eager CLI loading for existing backends.
        """
        return False

    def accepts_target_options(self) -> bool:
        """Whether the backend accepts the ``--timeout``/``--fast`` flags.

        These populate target-header options (a run timeout and fast mode)
        for the generated program. When False, the CLI omits both flags for
        this backend.
        """
        return False

    def serialize(self, artifact: object, fmt: str) -> str:
        """Serialize a built artifact to text in the requested format."""
        raise SerializationError(
            f"backend {self.name!r} cannot serialize to {fmt!r}"
        )

    @abstractmethod
    def write(self, artifact: object, options: OutputOptions) -> list[Path]:
        """Write the artifact's files into ``options.output_dir``.

        The backend owns its output shape (a single file or a directory
        tree) and the filename and extension for each format. The CLI does
        not assume any particular layout.

        Args:
            artifact: The artifact returned by :meth:`build`.
            options: Where to write, which formats, and the base filename.

        Returns:
            The paths actually written, for the caller to report.
        """

    @abstractmethod
    def summary(self, artifact: object) -> str:
        """Return a one-line description of a built artifact."""


def discover_backends() -> dict[str, Backend]:
    """Discover installed backends via ``sysmlc.backends`` entry points.

    Each entry point must name a no-argument :class:`Backend` subclass. A
    backend that fails to load is skipped with a logged warning, so a single
    broken plugin cannot take down the whole CLI. Two backends claiming the
    same ``name`` cannot be resolved unambiguously, so a collision is refused
    rather than letting one silently shadow the other.

    Returns:
        Backend instances keyed by ``Backend.name``.

    Raises:
        BackendError: If two entry points yield backends with the same name.
    """
    backends: dict[str, Backend] = {}
    providers: dict[str, str] = {}
    for entry_point in entry_points(group=BACKEND_ENTRY_POINT_GROUP):
        try:
            backend = entry_point.load()()
        except Exception as error:  # a broken plugin must not break discovery
            logger.warning(
                "Failed to load backend %r: %s", entry_point.name, error
            )
            continue
        if not isinstance(backend, Backend):
            logger.warning(
                "Entry point %r did not yield a Backend; skipping",
                entry_point.name,
            )
            continue
        if backend.name in backends:
            raise BackendError(
                f"duplicate backend name {backend.name!r}: provided by both "
                f"entry points {providers[backend.name]!r} and "
                f"{entry_point.name!r}; uninstall one of the conflicting "
                "plugins."
            )
        backends[backend.name] = backend
        providers[backend.name] = entry_point.name
    return backends
