from __future__ import annotations

from typing import TYPE_CHECKING

from sysmlc.cli import main
from tests.cli.test_cli import ONE_DEF_MODEL, _FakeBackend

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from sysmlc.sysml.foreign_artifact.base import ForeignArtifact


class _WholeModelBackend(_FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.external: list[ForeignArtifact] = []
        self.strict = False

    def accepts_strict_extern(self) -> bool:
        return True

    def build_model(
        self,
        model: object,
        *,
        external: list[ForeignArtifact] | None = None,
        strict_extern: bool = False,
    ) -> object:
        self.external = external or []
        self.strict = strict_extern
        return "whole-model artifact"


def test_whole_model_build_resolves_and_delivers_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _WholeModelBackend()
    monkeypatch.setattr(
        "sysmlc.cli.discover_backends", lambda: {"fake": backend}
    )
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.sysml").write_text(ONE_DEF_MODEL)
    support = tmp_path / "support.py"
    support.write_text("def step(): return 1\n")
    output = tmp_path / "out"
    assert (
        main(
            [
                "fake",
                "build",
                str(model),
                "--strict-extern",
                "--python",
                str(support),
                "--python",
                str(support),
                "-o",
                str(output),
            ]
        )
        == 0
    )
    assert backend.strict
    assert [a.path for a in backend.external] == [support]
    assert (output / "support.py").read_text() == support.read_text()
