from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

from sysmlc.backends import Backend
from sysmlc.cli import _parse_external, main

if TYPE_CHECKING:
    from pathlib import Path

    from sysmlc.backends import OutputOptions

SM01_DIR = SM_EXAMPLES_DIR / "sm01-helloworld"


TWO_DEFS_MODEL = """\
package Two {
    state def First {
        entry; then a;
        state a;
        state b;
        transition first a then b;
    }
    state def Second {
        entry; then a;
        state a;
        state b;
        transition first a then b;
    }
}
"""

ONE_DEF_MODEL = """\
package One {
    state def Machine {
        entry; then idle;
        state idle;
        state running;
        transition first idle then running;
    }
}
"""


class _FakeBackend(Backend):
    """A minimal in-memory backend that records how the CLI drives it."""

    def __init__(self) -> None:
        super().__init__(
            name="fake",
            description="A fake backend for tests.",
            formats=(("txt", "plain text"),),
        )
        self.build_calls: list[str] = []
        self.built_models: list[object] = []
        self.write_calls: list[OutputOptions] = []

    def build(self, model: object, element_qn: str) -> object:
        self.build_calls.append(element_qn)
        self.built_models.append(model)
        return f"artifact:{element_qn}"

    def write(self, artifact: object, options: OutputOptions) -> list[Path]:
        self.write_calls.append(options)
        options.output_dir.mkdir(parents=True, exist_ok=True)
        path = options.output_dir / f"{options.basename or 'artifact'}.txt"
        path.write_text(str(artifact))
        return [path]

    def summary(self, artifact: object) -> str:
        return f"fake {artifact}"


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> _FakeBackend:
    """Register a stub backend as the only one the CLI discovers."""
    backend = _FakeBackend()
    monkeypatch.setattr(
        "sysmlc.cli.discover_backends", lambda: {"fake": backend}
    )
    return backend


def test_backends_lists_discovered_backends(
    fake: _FakeBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["backends"]) == 0
    assert "fake" in capsys.readouterr().out


def test_build_uses_sole_state_def(fake: _FakeBackend, tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "one.sysml").write_text(ONE_DEF_MODEL)

    exit_code = main(["fake", "build", str(model_dir), "-o", str(tmp_path)])
    assert exit_code == 0
    assert fake.build_calls == ["One::Machine"]


def test_build_passes_output_options_to_backend(
    fake: _FakeBackend, tmp_path: Path
) -> None:
    main(
        [
            "fake",
            "build",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "-o",
            str(tmp_path),
            "-f",
            "txt",
        ]
    )
    assert len(fake.write_calls) == 1
    options = fake.write_calls[0]
    assert options.output_dir == tmp_path
    assert options.formats == ("txt",)
    assert options.basename == "Machine"


def test_build_defaults_to_all_formats(
    fake: _FakeBackend, tmp_path: Path
) -> None:
    main(
        [
            "fake",
            "build",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "-o",
            str(tmp_path),
        ]
    )
    assert fake.write_calls[0].formats == ()


def test_build_selects_state_def_by_element(
    fake: _FakeBackend, tmp_path: Path
) -> None:
    exit_code = main(
        [
            "fake",
            "build",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "-o",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    assert fake.build_calls == ["SM01::Machine"]


def test_build_resolves_bundled_model_name(
    fake: _FakeBackend, tmp_path: Path
) -> None:
    exit_code = main(
        [
            "fake",
            "build",
            "sm-examples/sm01-helloworld",
            "-e",
            "SM01::Machine",
            "-o",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    assert fake.build_calls == ["SM01::Machine"]


def test_build_rejects_unknown_model_reference(
    fake: _FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["fake", "build", "no-such-model", "-o", str(tmp_path)])
    assert exit_code == 1
    assert "no-such-model" in capsys.readouterr().err


def test_unknown_backend_is_rejected_by_argparse(
    fake: _FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(["nope", "build", str(SM01_DIR), "-o", str(tmp_path)])
    assert "invalid choice" in capsys.readouterr().err


def test_unknown_format_is_rejected_by_argparse(
    fake: _FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "fake",
                "build",
                str(SM01_DIR),
                "-o",
                str(tmp_path),
                "-f",
                "json",
            ]
        )
    assert "invalid choice" in capsys.readouterr().err


def test_build_ambiguous_element_errors(
    fake: _FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "two.sysml").write_text(TWO_DEFS_MODEL)
    exit_code = main(
        [
            "fake",
            "build",
            str(model_dir),
            "-o",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 1
    assert "--element" in capsys.readouterr().err


def test_build_unknown_element_errors(
    fake: _FakeBackend, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "fake",
            "build",
            str(SM01_DIR),
            "-e",
            "SM01::Missing",
            "-o",
            str(tmp_path),
        ]
    )
    assert exit_code == 1
    assert "SM01::Missing" in capsys.readouterr().err


CONFIGURABLE_MODEL = """\
package Cfg {
    private import ScalarValues::*;
    state def Machine {
        attribute speed : Real := 1.0;
        entry; then a;
        state a;
    }
}
"""


def _write_configurable(tmp_path: Path) -> Path:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "m.sysml").write_text(CONFIGURABLE_MODEL)
    return model_dir


def test_build_applies_values_overrides(
    fake: _FakeBackend, tmp_path: Path
) -> None:
    # --values must hand EVERY backend a configured (reloaded) model.
    import syside

    from sysmlc.sysml.queries import resolve

    model_dir = _write_configurable(tmp_path)
    values = tmp_path / "values.yaml"
    values.write_text("Cfg:\n  Machine:\n    speed: 2.5\n")
    exit_code = main(
        [
            "fake",
            "build",
            str(model_dir),
            "--values",
            str(values),
            "-o",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 0
    (model,) = fake.built_models
    assert isinstance(model, syside.Model)
    machine = resolve(model, syside.StateDefinition, "Cfg::Machine")
    (speed,) = [
        m
        for m in machine.owned_members.collect()
        if isinstance(m, syside.AttributeUsage)
    ]
    fve = speed.feature_value_expression
    assert isinstance(fve, syside.LiteralRational)
    assert fve.value == 2.5


def test_build_rejects_unknown_value_override(
    fake: _FakeBackend,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model_dir = _write_configurable(tmp_path)
    values = tmp_path / "values.yaml"
    values.write_text("Cfg:\n  Machine:\n    _speed: 2.5\n")
    exit_code = main(
        [
            "fake",
            "build",
            str(model_dir),
            "--values",
            str(values),
            "-o",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 1
    assert "does not match an attribute" in capsys.readouterr().err


def test_parse_external_collects_sync_functions(tmp_path: Path) -> None:
    py = tmp_path / "phys.py"
    py.write_text("def step(): ...\nasync def nope(): ...\nx = 1\n")
    module, names = _parse_external(py)
    assert module == "phys"
    assert names == frozenset({"step"})
