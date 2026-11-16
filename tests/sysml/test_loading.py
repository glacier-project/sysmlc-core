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


_FIXED_WIDTH_MODEL = """package M {
    private import FixedWidthScalarValues::*;
    part def P {
        attribute c :> uint8 := 0;
        attribute d :> int16 := 3 * 4;
    }
}
"""


def _library_file() -> Path:
    import sysmlc_library

    (path,) = [
        Path(p)
        for p in sysmlc_library.library_files()
        if Path(p).name == "FixedWidthScalarValues.kerml"
    ]
    return path


def test_fixed_width_library_is_loaded(tmp_path: Path) -> None:
    (tmp_path / "m.sysml").write_text(_FIXED_WIDTH_MODEL)
    model = load_model(tmp_path)
    attribute = resolve(model, syside.AttributeUsage, "M::P::c")
    names = [
        membership.member_element.name
        for membership in attribute.inherited_memberships.collect()
        if isinstance(membership.member_element, syside.Invariant)
    ]
    assert "uint8Range" in names


def test_duplicate_library_copy_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "m.sysml").write_text(_FIXED_WIDTH_MODEL)
    copy = tmp_path / "FixedWidthScalarValues.kerml"
    copy.write_text(_library_file().read_text())
    with pytest.raises(ValueError) as info:
        load_model(tmp_path)
    message = str(info.value)
    assert "FixedWidthScalarValues" in message
    assert str(copy) in message
    assert str(_library_file()) in message
    assert "copy of an installed library" in message
    assert "remove the copy" in message


def test_duplicate_user_packages_are_an_error(tmp_path: Path) -> None:
    (tmp_path / "a.sysml").write_text("package A { part def X; }\n")
    (tmp_path / "b.sysml").write_text("package A { part def Y; }\n")
    with pytest.raises(ValueError) as info:
        load_model(tmp_path)
    message = str(info.value)
    assert str(tmp_path / "a.sysml") in message
    assert str(tmp_path / "b.sysml") in message
    assert "rename or remove one" in message
    assert "copy of an installed library" not in message


def test_duplicate_installed_libraries_are_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # two providers ship the same library: no file is a model-directory copy
    copies = [tmp_path / name / "Lib.kerml" for name in ("alpha", "beta")]
    for copy in copies:
        copy.parent.mkdir()
        copy.write_text(_library_file().read_text())
    _install_points(
        monkeypatch,
        [
            _FakeEntryPoint(copy.parent.name, provider=lambda c=copy: [c])
            for copy in copies
        ],
    )
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "m.sysml").write_text(_FIXED_WIDTH_MODEL)
    with pytest.raises(ValueError) as info:
        load_model(model_dir)
    message = str(info.value)
    assert all(str(copy) in message for copy in copies)
    assert "rename or remove one" in message
    assert "copy of an installed library" not in message


_FIXED_WIDTH_FEATURES = [
    ("int8", "Integer"),
    ("int16", "Integer"),
    ("int32", "Integer"),
    ("int64", "Integer"),
    ("uint8", "Natural"),
    ("uint16", "Natural"),
    ("uint32", "Natural"),
    ("uint64", "Natural"),
    ("float32", "Real"),
    ("float64", "Real"),
]


@pytest.mark.parametrize(("name", "scalar"), _FIXED_WIDTH_FEATURES)
def test_fixed_width_feature_type_and_range(
    tmp_path: Path, name: str, scalar: str
) -> None:
    (tmp_path / "m.sysml").write_text(
        "package M { private import FixedWidthScalarValues::*; "
        f"part def P {{ attribute a :> {name}; }} }}\n"
    )
    model = load_model(tmp_path)
    attribute = resolve(model, syside.AttributeUsage, "M::P::a")
    feature = resolve(model, syside.Feature, f"FixedWidthScalarValues::{name}")
    declared = [str(t.qualified_name) for t in feature.types.collect()]
    assert f"ScalarValues::{scalar}" in declared
    invariants = [
        membership.member_element.name
        for membership in attribute.inherited_memberships.collect()
        if isinstance(membership.member_element, syside.Invariant)
    ]
    if scalar == "Real":
        assert invariants == []
    else:
        assert invariants == [f"{name}Range"]


def test_warnings_are_logged_in_full(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # a self-specialization is a Syside warning, not an error
    (tmp_path / "m.sysml").write_text("package M { part def P :> P; }\n")
    with caplog.at_level(logging.WARNING, logger=loading.logger.name):
        load_model(tmp_path)
    assert any(
        "Type specialization to itself has no effect" in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]
