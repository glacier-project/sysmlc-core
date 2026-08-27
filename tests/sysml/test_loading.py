import logging
from collections.abc import Callable
from pathlib import Path

import pytest
import syside

from sysmlc.sysml import loading
from sysmlc.sysml.loading import load_model, provider_library_files
from sysmlc.sysml.queries import resolve


class _FakeEntryPoint:
    """A stand-in for importlib.metadata's EntryPoint."""

    def __init__(
        self,
        name: str,
        provider: Callable[[], list[Path]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._provider = provider
        self._error = error

    def load(self) -> Callable[[], list[Path]] | None:
        if self._error is not None:
            raise self._error
        return self._provider


def _install_points(
    monkeypatch: pytest.MonkeyPatch, points: list[_FakeEntryPoint]
) -> None:
    def fake_entry_points(group: str) -> list[_FakeEntryPoint]:
        assert group == loading.LIBRARY_ENTRY_POINT_GROUP
        return points

    monkeypatch.setattr(loading, "entry_points", fake_entry_points)


def _explode() -> list[Path]:
    raise ValueError("bad provider")


def test_load_model_loads_ice_lab(model: syside.Model) -> None:
    assert isinstance(model, syside.Model)
    assert model.documents


def test_load_model_raises_on_diagnostic_errors(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "broken.sysml"
    broken.write_text("part def { this is not valid syntax")

    with pytest.raises(ValueError, match="syside diagnostics"):
        load_model(tmp_path)


def test_sysmlc_library_is_always_available(tmp_path: Path) -> None:
    (tmp_path / "m.sysml").write_text(
        "package M {\n  state def S { entry; then a; state a; }\n}\n"
    )
    model = load_model(tmp_path)
    fn = resolve(model, syside.CalculationDefinition, "sysmlc::log")
    assert fn.name == "log"


def test_providers_are_ordered_by_entry_point_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_points(
        monkeypatch,
        [
            _FakeEntryPoint("zeta", provider=lambda: [Path("/z/a.sysml")]),
            _FakeEntryPoint("alpha", provider=lambda: [Path("/a/b.sysml")]),
        ],
    )
    assert provider_library_files() == [
        Path("/a/b.sysml"),
        Path("/z/a.sysml"),
    ]


def test_duplicate_paths_keep_the_first_occurrence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared = Path("/shared/vocab.sysml")
    _install_points(
        monkeypatch,
        [
            _FakeEntryPoint("alpha", provider=lambda: [shared]),
            _FakeEntryPoint(
                "beta", provider=lambda: [shared, Path("/b/own.sysml")]
            ),
        ],
    )
    assert provider_library_files() == [shared, Path("/b/own.sysml")]


@pytest.mark.parametrize(
    ("failing", "name"),
    [
        (_FakeEntryPoint("broken", error=RuntimeError("boom")), "broken"),
        (_FakeEntryPoint("explodes", provider=_explode), "explodes"),
    ],
)
def test_a_failing_provider_does_not_hide_healthy_ones(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failing: _FakeEntryPoint,
    name: str,
) -> None:
    _install_points(
        monkeypatch,
        [
            failing,
            _FakeEntryPoint(
                "healthy", provider=lambda: [Path("/ok/lib.sysml")]
            ),
        ],
    )
    with caplog.at_level(logging.WARNING):
        assert provider_library_files() == [Path("/ok/lib.sysml")]
    assert name in caplog.text


def test_load_model_resolves_imports_from_a_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    library = tmp_path / "provider" / "vocab.sysml"
    library.parent.mkdir()
    library.write_text(
        "package ProviderVocabulary {\n    part def ProvidedDevice;\n}\n"
    )
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.sysml").write_text(
        "package Consumer {\n"
        "    private import ProviderVocabulary::*;\n"
        "    part device : ProvidedDevice;\n"
        "}\n"
    )
    _install_points(
        monkeypatch,
        [_FakeEntryPoint("vocab", provider=lambda: [library])],
    )
    model = load_model(model_dir)
    device = resolve(
        model, syside.PartDefinition, "ProviderVocabulary::ProvidedDevice"
    )
    assert device.name == "ProvidedDevice"

    # The control fails for the expected reason: without the provider
    # the same model does not resolve its import.
    _install_points(monkeypatch, [])
    with pytest.raises(ValueError, match="diagnostics"):
        load_model(model_dir)
