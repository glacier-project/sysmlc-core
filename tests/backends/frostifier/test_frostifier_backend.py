from __future__ import annotations

from sysmlc.backends import discover_backends
from sysmlc.backends.frostifier.backend import FrostifierBackend


def test_frostifier_backend_is_discoverable() -> None:
    backends = discover_backends()
    assert "frostifier" in backends
    assert isinstance(backends["frostifier"], FrostifierBackend)
