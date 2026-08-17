from collections.abc import Callable

import pytest

from sysmlc.backends.base import Backend, OutputOptions, discover_backends
from sysmlc.errors import BackendError
from sysmlc.sysml.foreign_artifact.base import ForeignArtifact


class _StubBackend(Backend):
    def __init__(self, name: str) -> None:
        super().__init__(name, f"{name} backend")

    def build(
        self,
        model: object,
        element_qn: str,
        external: list[ForeignArtifact] | None = None,
    ) -> object:
        return object()

    def write(self, artifact: object, options: OutputOptions) -> list:
        return []

    def summary(self, artifact: object) -> str:
        return "stub"


class _FakeEntryPoint:
    def __init__(self, name: str, backend_name: str) -> None:
        self.name = name
        self._backend_name = backend_name

    def load(self) -> Callable[[], _StubBackend]:
        return lambda: _StubBackend(self._backend_name)


def test_discover_backends_rejects_duplicate_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Two entry points whose backends both claim the name "quake": the second
    # would silently shadow the first, so discovery must refuse it.
    entry_points = [
        _FakeEntryPoint("quake", "quake"),
        _FakeEntryPoint("quake-fork", "quake"),
    ]
    monkeypatch.setattr(
        "sysmlc.backends.base.entry_points", lambda group: entry_points
    )
    with pytest.raises(BackendError, match="duplicate backend name 'quake'"):
        discover_backends()


def test_python_support_loading_is_eager_by_default() -> None:
    assert not _StubBackend("stub").defers_python_support_loading()
