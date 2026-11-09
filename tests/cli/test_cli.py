from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

from sysmlc.backends import Backend, BuildOption
from sysmlc.cli import CliError, _copy_python_support, main
from sysmlc.sysml.foreign_artifact.base import parse_artifact

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from sysmlc.backends import OutputOptions
    from sysmlc.sysml.foreign_artifact.base import ForeignArtifact

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
        self.run_events: list[str] = []

    def build(
        self,
        model: object,
        element_qn: str,
        external: list[ForeignArtifact] | None = None,
        strict_extern: bool = False,
    ) -> object:
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

    def consumes_python_support(self) -> bool:
        return True

    def defers_python_support_loading(self) -> bool:
        return True

    def run_state_def(
        self,
        model: object,
        element_qn: str,
        *,
        max_steps: int = 1000,
        until: float | None = None,
        external: list[ForeignArtifact] | None = None,
        load_external: Callable[[], None] | None = None,
    ) -> _FakeRunReport:
        self.run_events.append("prepared")
        if load_external is not None:
            load_external()
            self.run_events.append("loaded")
        return _FakeRunReport()


class _FakeRunReport:
    hit_step_cap = False

    def render(self) -> str:
        return "complete"


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
    module, names = parse_artifact(py)
    assert module == "phys"
    assert names == frozenset({"step"})


def test_build_copies_python_support_beside_artifact(
    fake: _FakeBackend, tmp_path: Path
) -> None:
    support = tmp_path / "support.py"
    support.write_text("def step(): ...\n")
    out = tmp_path / "out"

    exit_code = main(
        [
            "fake",
            "build",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            str(support),
            "-o",
            str(out),
        ]
    )

    assert exit_code == 0
    assert (out / "support.py").read_text() == support.read_text()


def test_build_copies_every_repeated_support_flag(
    fake: _FakeBackend, tmp_path: Path
) -> None:
    """Repeating ``--python`` carries every file along, e.g. a companion."""
    impl = tmp_path / "impl.py"
    impl.write_text("def step(): ...\n")
    helper = tmp_path / "helper.py"
    helper.write_text("VALUE = 1\n")
    out = tmp_path / "out"

    exit_code = main(
        [
            "fake",
            "build",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            str(impl),
            "--python",
            str(helper),
            "-o",
            str(out),
        ]
    )

    assert exit_code == 0
    assert (out / "impl.py").read_text() == impl.read_text()
    assert (out / "helper.py").read_text() == helper.read_text()


class _OwnsDeliveryFakeBackend(_FakeBackend):
    """A backend that claims to place external artifacts itself."""

    def owns_external_delivery(self) -> bool:
        return True


def test_build_skips_generic_copy_when_backend_owns_delivery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = _OwnsDeliveryFakeBackend()
    monkeypatch.setattr(
        "sysmlc.cli.discover_backends", lambda: {"fake": backend}
    )
    support = tmp_path / "support.py"
    support.write_text("def step(): ...\n")
    out = tmp_path / "out"

    exit_code = main(
        [
            "fake",
            "build",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            str(support),
            "-o",
            str(out),
        ]
    )

    assert exit_code == 0
    # write() itself did not place a copy; the CLI's generic copy is the
    # only thing that would have, and it must have been skipped.
    assert not (out / "support.py").exists()


def test_python_support_is_loaded_when_backend_is_ready(
    fake: _FakeBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    support = tmp_path / "support.py"
    support.write_text("def step(): ...\n")

    def record_load(path: Path) -> None:
        assert path == support
        fake.run_events.append("load")

    monkeypatch.setattr("sysmlc.cli._load_external_module", record_load)

    exit_code = main(
        [
            "fake",
            "run",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            str(support),
        ]
    )

    assert exit_code == 0
    assert fake.run_events == ["prepared", "load", "loaded"]


def test_python_support_loading_remains_eager_without_opt_in(
    fake: _FakeBackend,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    support = tmp_path / "support.py"
    support.write_text("def step(): ...\n")
    monkeypatch.setattr(fake, "defers_python_support_loading", lambda: False)

    def record_load(path: Path) -> None:
        assert path == support
        fake.run_events.append("load")

    monkeypatch.setattr("sysmlc.cli._load_external_module", record_load)

    exit_code = main(
        [
            "fake",
            "run",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            str(support),
        ]
    )

    assert exit_code == 0
    assert fake.run_events == ["load", "prepared"]


def test_run_still_drives_backends_predating_load_external(
    fake: _FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A backend released before the load_external contract: its run hook
    # does not accept the kwarg, and it does not defer loading.
    def legacy_run_state_def(
        model: object,
        element_qn: str,
        *,
        max_steps: int = 1000,
        until: float | None = None,
        external: tuple[str, frozenset[str]] | None = None,
    ) -> _FakeRunReport:
        fake.run_events.append("legacy-ran")
        return _FakeRunReport()

    monkeypatch.setattr(fake, "run_state_def", legacy_run_state_def)
    monkeypatch.setattr(fake, "defers_python_support_loading", lambda: False)

    exit_code = main(["fake", "run", str(SM01_DIR), "-e", "SM01::Machine"])

    assert exit_code == 0
    assert fake.run_events == ["legacy-ran"]


def test_copy_python_support_rejects_generated_path_collision(
    tmp_path: Path,
) -> None:
    support = tmp_path / "source" / "support.py"
    support.parent.mkdir()
    support.write_text("def step(): ...\n")
    generated = tmp_path / "out" / "support.py"
    generated.parent.mkdir()
    generated.write_text("generated = True\n")

    with pytest.raises(CliError, match="conflicts with generated artifact"):
        _copy_python_support(support, [generated])


class _TargetFakeBackend(_FakeBackend):
    """A fake backend with a ``--target`` build option.

    ``configured`` returns a new instance bound to the chosen target that
    shares this one's call logs, so a test can tell which instance the CLI
    drove.
    """

    def __init__(self, target: str = "unconfigured") -> None:
        super().__init__()
        self.target = target

    def build_options(self) -> tuple[BuildOption, ...]:
        return (
            BuildOption(
                "target",
                "language to generate",
                choices=("python", "c"),
                default="python",
            ),
        )

    def configured(
        self, options: Mapping[str, str | None]
    ) -> _TargetFakeBackend:
        target = options["target"]
        assert target is not None
        bound = _TargetFakeBackend(target)
        bound.build_calls = self.build_calls
        bound.write_calls = self.write_calls
        return bound

    def build(
        self,
        model: object,
        element_qn: str,
        external: list[ForeignArtifact] | None = None,
        strict_extern: bool = False,
    ) -> object:
        self.build_calls.append(f"{self.target}:{element_qn}")
        return f"artifact:{element_qn}"

    def summary(self, artifact: object) -> str:
        return f"{self.target} {artifact}"


@pytest.fixture
def target_fake(monkeypatch: pytest.MonkeyPatch) -> _TargetFakeBackend:
    backend = _TargetFakeBackend()
    monkeypatch.setattr(
        "sysmlc.cli.discover_backends", lambda: {"fake": backend}
    )
    return backend


def _build_sm01(tmp_path: Path, *extra: str) -> int:
    return main(
        [
            *("fake", "build", str(SM01_DIR), "-e", "SM01::Machine"),
            *("-o", str(tmp_path)),
            *extra,
        ]
    )


def test_build_option_value_reaches_the_configured_backend(
    target_fake: _TargetFakeBackend, tmp_path: Path
) -> None:
    assert _build_sm01(tmp_path, "--target", "c") == 0

    assert target_fake.build_calls == ["c:SM01::Machine"]


def test_build_option_defaults_when_the_flag_is_absent(
    target_fake: _TargetFakeBackend, tmp_path: Path
) -> None:
    _build_sm01(tmp_path)

    assert target_fake.build_calls == ["python:SM01::Machine"]


def test_configured_backend_also_writes_and_summarizes(
    target_fake: _TargetFakeBackend,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="sysmlc.cli"):
        _build_sm01(tmp_path, "--target", "c")

    assert len(target_fake.write_calls) == 1
    assert "c artifact:SM01::Machine" in caplog.text


def test_build_option_rejects_a_value_outside_its_choices(
    target_fake: _TargetFakeBackend, tmp_path: Path
) -> None:
    with pytest.raises(SystemExit):
        _build_sm01(tmp_path, "--target", "rust")

    assert target_fake.build_calls == []


def test_build_option_flag_exists_only_for_backends_declaring_it(
    fake: _FakeBackend, tmp_path: Path
) -> None:
    with pytest.raises(SystemExit):
        _build_sm01(tmp_path, "--target", "c")

    assert fake.build_calls == []
