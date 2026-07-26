from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sismic.io import import_from_yaml
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

from sysmlc.backends import Backend
from sysmlc.cli import _parse_external, main

if TYPE_CHECKING:
    from sysmlc.backends import OutputOptions

SM01_DIR = SM_EXAMPLES_DIR / "sm01-helloworld"

RIG_DIR = Path(__file__).resolve().parents[1] / (
    "backends/rosetta/fixtures/rig-pair"
)

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


def test_rig_auto_select_builds_composition(tmp_path: Path) -> None:
    exit_code = main(["rosetta", "build", str(RIG_DIR), "-o", str(tmp_path)])
    assert exit_code == 0
    text = (tmp_path / "PlantRig.lf").read_text()
    assert "reactor PlantRig {" in text
    assert "plant = new Plant()" in text


def test_explicit_rig_element_builds_composition(tmp_path: Path) -> None:
    exit_code = main(
        [
            "rosetta",
            "build",
            str(RIG_DIR),
            "-e",
            "RigPair::PlantRig",
            "-o",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    text = (tmp_path / "PlantRig.lf").read_text()
    assert "reactor PlantRig {" in text


def test_explicit_state_def_still_builds_bare_machine(
    tmp_path: Path,
) -> None:
    exit_code = main(
        [
            "rosetta",
            "build",
            str(RIG_DIR),
            "-e",
            "RigPair::Plant",
            "-o",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    text = (tmp_path / "Plant.lf").read_text()
    assert "reactor PlantRig" not in text
    # assert "Done_act" in text  # bare build: the send stays a self-event


def test_rig_on_backend_without_composition_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "quake",
            "build",
            str(RIG_DIR),
            "-e",
            "RigPair::PlantRig",
            "-o",
            str(tmp_path),
        ]
    )
    assert exit_code == 1
    assert "cannot build a rig composition" in capsys.readouterr().err


def test_rig_values_apply_per_machine(tmp_path: Path) -> None:
    values = tmp_path / "values.yaml"
    values.write_text("RigPair:\n  PlantTest:\n    verdict: 1\n")
    exit_code = main(
        [
            "rosetta",
            "build",
            str(RIG_DIR),
            "-o",
            str(tmp_path / "out"),
            "--values",
            str(values),
        ]
    )
    assert exit_code == 0
    text = (tmp_path / "out" / "PlantRig.lf").read_text()
    assert "state verdict = {= 1 =}" in text


def test_build_with_python_copies_module_and_imports(tmp_path: Path) -> None:
    from sysmlc.cli import main

    model = tmp_path / "model"
    model.mkdir()
    (model / "m.sysml").write_text(
        "package M {\n"
        "  private import ScalarValues::*;\n"
        "  private import SI::*;\n"
        "  package P { calc def step { in x : Real; return : Real; } }\n"
        "  state def S {\n"
        "    attribute x : Real := 0.0;\n"
        "    entry; then a; state a; state b;\n"
        "    transition first a accept after 0.1 [s]\n"
        "      do assign x := P::step(x) then b;\n"
        "  }\n"
        "}\n"
    )
    py = tmp_path / "ext.py"
    py.write_text("def step(x):\n    return x + 1.0\n")
    out = tmp_path / "out"
    rc = main(
        [
            "rosetta",
            "build",
            str(model),
            "-e",
            "M::S",
            "-o",
            str(out),
            "--python",
            str(py),
        ]
    )
    assert rc == 0
    lf = (out / "S.lf").read_text()
    assert "from ext import step" in lf
    assert "self.x = step(self.x)" in lf
    assert (out / "ext.py").exists()  # copied next to the .lf


def test_quake_build_with_python_imports_without_copying(
    tmp_path: Path,
) -> None:
    model = SM_EXAMPLES_DIR / "sm15-external"
    py = tmp_path / "ext.py"
    py.write_text(
        "def step(x, dt):\n"
        "    return x + dt\n\n"
        "def unused():\n"
        "    return None\n"
    )
    out = tmp_path / "out"
    rc = main(
        [
            "quake",
            "build",
            str(model),
            "-e",
            "SM15::Ramp",
            "-o",
            str(out),
            "-f",
            "yaml",
            "--python",
            str(py),
        ]
    )

    assert rc == 0
    yaml_path = out / "Ramp.yaml"
    yaml = yaml_path.read_text()
    sc = import_from_yaml(filepath=str(yaml_path))
    assert sc.preamble.splitlines()[:3] == [
        "from math import cos as _cos, sin as _sin, tan as _tan",
        "from types import SimpleNamespace",
        "from ext import step",
    ]
    assert "x = step(x, 0.1)" in yaml
    assert not (out / "ext.py").exists()


def test_build_reps_generates_module_beside_lf(tmp_path: Path) -> None:
    # sm15-rep carries the calc body as a Python rep.
    out = tmp_path / "out"
    rc = main(
        [
            "rosetta",
            "build",
            str(SM_EXAMPLES_DIR / "sm15-rep"),
            "-e",
            "SM15Rep::Ramp",
            "-o",
            str(out),
        ]
    )
    assert rc == 0
    lf = (out / "Ramp.lf").read_text()
    assert "from Ramp_impl import step" in lf
    assert '"Ramp_impl.py"' in lf
    assert "step(self.x, 0.1)" in lf
    assert "def step(x, dt):" in (out / "Ramp_impl.py").read_text()


def test_rep_build_matches_explicit_python_build(tmp_path: Path) -> None:
    # The rep path and the --python path are one pipeline: feeding the
    # generated module back through --python yields a byte-identical .lf.
    rep_out = tmp_path / "rep"
    rc = main(
        [
            "rosetta",
            "build",
            str(SM_EXAMPLES_DIR / "sm15-rep"),
            "-e",
            "SM15Rep::Ramp",
            "-o",
            str(rep_out),
        ]
    )
    assert rc == 0
    python_out = tmp_path / "python"
    rc = main(
        [
            "rosetta",
            "build",
            str(SM_EXAMPLES_DIR / "sm15-rep"),
            "-e",
            "SM15Rep::Ramp",
            "-o",
            str(python_out),
            "--python",
            str(rep_out / "Ramp_impl.py"),
        ]
    )
    assert rc == 0
    rep_lf = (rep_out / "Ramp.lf").read_text()
    python_lf = (python_out / "Ramp.lf").read_text()
    assert rep_lf == python_lf


def test_explicit_python_wins_over_reps(tmp_path: Path) -> None:
    # A user-supplied --python module overrides the model's reps: the
    # explicit stem backs the calls and no module is generated.
    py = tmp_path / "ramp.py"
    py.write_text("def step(x, dt):\n    return x + dt\n")
    out = tmp_path / "out"
    rc = main(
        [
            "rosetta",
            "build",
            str(SM_EXAMPLES_DIR / "sm15-rep"),
            "-e",
            "SM15Rep::Ramp",
            "-o",
            str(out),
            "--python",
            str(py),
        ]
    )
    assert rc == 0
    lf = (out / "Ramp.lf").read_text()
    assert "from ramp import step" in lf
    assert '"ramp.py"' in lf
    assert '"Ramp_impl.py"' not in lf
    assert not (out / "Ramp_impl.py").exists()


def test_quake_build_with_reps_imports_generated_module(
    tmp_path: Path,
) -> None:
    # quake consumes the rep-generated module through the same pipeline
    # as --python; like --python, the module is not copied beside the
    # .yaml (the run command regenerates and imports it).
    out = tmp_path / "out"
    rc = main(
        [
            "quake",
            "build",
            str(SM_EXAMPLES_DIR / "sm15-rep"),
            "-e",
            "SM15Rep::Ramp",
            "-o",
            str(out),
            "-f",
            "yaml",
        ]
    )
    assert rc == 0
    yaml = (out / "Ramp.yaml").read_text()
    assert "from Ramp_impl import step" in yaml
    assert "x = step(x, 0.1)" in yaml
    assert not (out / "Ramp_impl.py").exists()


def test_build_part_system_emits_main_reactor(tmp_path: Path) -> None:
    out = tmp_path / "out"
    rc = main(
        [
            "rosetta",
            "build",
            str(SM_EXAMPLES_DIR / "part01-two-parts"),
            "-e",
            "Part01::pingSystem",
            "-o",
            str(out),
            "--timeout",
            "5 sec",
            "--fast",
        ]
    )
    assert rc == 0
    lf = (out / "pingSystem.lf").read_text()
    assert "main reactor {" in lf
    assert "fast: true" in lf
    assert "timeout: 5 sec" in lf
    assert "plant = new Plant()" in lf


def test_single_part_system_auto_selected(tmp_path: Path) -> None:
    # No --element: the model's single top-level part usage is selected.
    out = tmp_path / "out"
    rc = main(
        [
            "rosetta",
            "build",
            str(SM_EXAMPLES_DIR / "part01-two-parts"),
            "-o",
            str(out),
        ]
    )
    assert rc == 0
    assert (out / "pingSystem.lf").exists()


def test_quake_build_part_system_writes_artifact_directory(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    rc = main(
        [
            "quake",
            "build",
            str(SM_EXAMPLES_DIR / "part01-two-parts"),
            "-o",
            str(out),
            "-f",
            "yaml",
        ]
    )
    assert rc == 0
    assert (out / "pingSystem" / "routing.json").exists()
    assert (out / "pingSystem" / "plant.yaml").exists()
    assert (out / "pingSystem" / "tb.yaml").exists()


def test_build_part_system_with_python_copies_module_and_imports(
    tmp_path: Path,
) -> None:
    # --python must work for part usages: the generated .lf includes the
    # external import and the bump.py module is copied beside the .lf.
    part_ext = SM_EXAMPLES_DIR / "part-external"
    out = tmp_path / "out"
    rc = main(
        [
            "rosetta",
            "build",
            str(part_ext),
            "-e",
            "PartExt::counterSystem",
            "-o",
            str(out),
            "--python",
            str(part_ext / "bump.py"),
        ]
    )
    assert rc == 0
    lf = (out / "counterSystem.lf").read_text()
    assert "from bump import bump" in lf
    assert '"bump.py"' in lf  # listed in files: so lfc copies it to src-gen
    assert (out / "bump.py").exists()  # copied beside the .lf


def test_quake_build_part_system_with_python_imports_without_copying(
    tmp_path: Path,
) -> None:
    # --python for a quake part build: the per-instance YAML imports the
    # external function, and the module is not copied.
    part_ext = SM_EXAMPLES_DIR / "part-external"
    py = tmp_path / "ext.py"
    py.write_text("def bump(v):\n    return v + 1.0\n")
    out = tmp_path / "out"
    rc = main(
        [
            "quake",
            "build",
            str(part_ext),
            "-o",
            str(out),
            "-f",
            "yaml",
            "--python",
            str(py),
        ]
    )

    assert rc == 0
    assert (out / "counterSystem" / "routing.json").exists()
    yaml = (out / "counterSystem" / "c.yaml").read_text()
    assert "from ext import bump" in yaml
    assert not (out / "ext.py").exists()


def test_parse_external_collects_sync_functions(tmp_path: Path) -> None:
    py = tmp_path / "phys.py"
    py.write_text("def step(): ...\nasync def nope(): ...\nx = 1\n")
    module, names = _parse_external(py)
    assert module == "phys"
    assert names == frozenset({"step"})


def test_quake_run_part_system(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["quake", "run", str(SM_EXAMPLES_DIR / "part01-two-parts")])

    assert rc == 0
    assert "status=" in capsys.readouterr().out


def test_rosetta_run_is_rejected() -> None:
    rc = main(["rosetta", "run", str(SM_EXAMPLES_DIR / "part01-two-parts")])

    assert rc == 1


def test_quake_run_respects_max_steps(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(
        [
            "quake",
            "run",
            str(SM_EXAMPLES_DIR / "part01-two-parts"),
            "--max-steps",
            "1",
        ]
    )

    assert rc == 1
    assert "status=hit step cap" in capsys.readouterr().out


INCOMPLETE_GUARD_MODEL = """\
package Incomplete {
    private import ScalarValues::*;
    state def Machine {
        attribute threshold : Integer;
        entry; then waiting;
        state waiting;
        transition waiting if threshold > 0 then done;
    }
}
"""


def test_quake_run_reports_code_evaluation_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "m.sysml").write_text(INCOMPLETE_GUARD_MODEL)

    rc = main(["quake", "run", str(model_dir)])

    assert rc == 1
    assert "not defined" in capsys.readouterr().err


NONTERMINATING_MODEL = """\
package Loop {
    private import SI::*;
    state def Machine {
        entry; then running;
        state running;
        transition running accept after 1 [s] then running;
    }
}
"""


def test_quake_run_until_bounds_a_nonterminating_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "m.sysml").write_text(NONTERMINATING_MODEL)

    rc = main(["quake", "run", str(model_dir), "--until", "3"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "clock=3.0" in out
    assert "status=reached time bound" in out


@pytest.mark.usefixtures("fresh_external_modules")
def test_quake_run_state_def_with_python(
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = SM_EXAMPLES_DIR / "sm15-external"
    rc = main(
        [
            "quake",
            "run",
            str(model),
            "--python",
            str(model / "ramp.py"),
            "--until",
            "0.25",
        ]
    )

    assert rc == 0
    assert "status=reached time bound" in capsys.readouterr().out


@pytest.mark.usefixtures("fresh_external_modules")
def test_quake_run_part_system_with_python(
    capsys: pytest.CaptureFixture[str],
) -> None:
    part_ext = SM_EXAMPLES_DIR / "part-external"
    rc = main(
        [
            "quake",
            "run",
            str(part_ext),
            "--python",
            str(part_ext / "bump.py"),
            "--until",
            "0.25",
        ]
    )

    assert rc == 0
    assert "status=reached time bound" in capsys.readouterr().out


NONDETERMINISTIC_MODEL = """\
package Nondet {
    private import ScalarValues::*;
    state def Machine {
        attribute x : Integer := 1;
        entry; then idle;
        state idle;
        state left;
        state right;
        transition first idle if x > 0 then left;
        transition first idle if x < 2 then right;
    }
}
"""


def test_quake_run_reports_nondeterminism_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "m.sysml").write_text(NONDETERMINISTIC_MODEL)

    rc = main(["quake", "run", str(model_dir)])

    assert rc == 1
    assert "on-determinis" in capsys.readouterr().err


def test_quake_run_with_missing_python_file_fails_cleanly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(
        [
            "quake",
            "run",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            "/nonexistent/typo.py",
        ]
    )

    assert rc == 1
    assert "typo.py" in capsys.readouterr().err


def test_quake_run_with_invalid_python_file_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n")

    rc = main(
        [
            "quake",
            "run",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            str(bad),
        ]
    )

    assert rc == 1
    assert "bad.py" in capsys.readouterr().err


def test_quake_run_unregisters_failed_python_module(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    boom = tmp_path / "boom.py"
    boom.write_text("def f():\n    return 1\nraise RuntimeError('exploded')\n")

    rc = main(
        [
            "quake",
            "run",
            str(SM01_DIR),
            "-e",
            "SM01::Machine",
            "--python",
            str(boom),
        ]
    )

    assert rc == 1
    assert "exploded" in capsys.readouterr().err
    # The broken half-executed module must not stay importable.
    assert "boom" not in sys.modules
