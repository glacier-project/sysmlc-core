from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from sysmlc.backends.base import OutputOptions

# The ignores below gate the frost-integration backend API, absent on
# some branches; `unused-ignore` keeps them inert once it lands.
try:
    from sysmlc.backends.frostifier.backend import (  # type: ignore[attr-defined,unused-ignore]
        FrostifierBackend,
        default_frost_source,
    )
    from sysmlc.backends.frostifier.parts import FROST_CHECKOUT_MARKER
except ImportError:
    pytest.skip(
        "frostifier program assembly not available on this branch",
        allow_module_level=True,
    )

from sysmlc.sysml.loading import load_model

pytestmark = pytest.mark.fmu

MODELS_DIR = Path(__file__).resolve().parents[3] / "models"
SHOWCASE_FROST_DIR = MODELS_DIR / "showcase-frost"
SHOWCASE = SHOWCASE_FROST_DIR / "quality-cell"


def _frost_source() -> str:
    """A clonable Frost source, or skip (URLs pass unprobed)."""
    frost: str | None = default_frost_source()
    if frost is not None and (
        "://" in frost or (Path(frost) / FROST_CHECKOUT_MARKER).is_file()
    ):
        return frost
    pytest.skip(
        "no Frost source found; set SYSMLC_FROST_PATH to a clone of "
        "github.com/glacier-project/frost"
    )


def _build_compile_run(
    model_dir: Path,
    usage_qn: str,
    basename: str,
    out_dir: Path,
    *,
    target_options: tuple[tuple[str, str], ...] = (),
) -> str:
    """Generate, lfc-compile, and run one Frost program; return its log.

    Termination is part of every caller's assertion: if the system never
    reaches its stopping state, the timers run forever and the wall
    timeout fails the test. The LF bin wrapper does not propagate the
    Python exit code, so success is asserted on the log content.
    """
    for module in ("fmpy", "LinguaFrancaBase", "machine_data_model", "yaml"):
        pytest.importorskip(module)
    frost = _frost_source()

    backend = FrostifierBackend()
    artifact = backend.build_part(  # type: ignore[attr-defined,unused-ignore]
        load_model(model_dir),
        usage_qn,
        frost=frost,
        target_options=target_options,
    )
    backend.write(
        artifact, OutputOptions(output_dir=out_dir, basename=basename)
    )
    config = out_dir / "resources" / "frost_config.yml"
    config.write_text(
        config.read_text().replace(
            "logging_level: INFO", "logging_level: DEBUG"
        )
    )

    # Activate this interpreter's virtualenv for lfc's CMake FindPython
    # (LF sets Python_FIND_VIRTUALENV FIRST), so the compiled program
    # runs on the interpreter that has the runtime deps.
    env = {
        **os.environ,
        "VIRTUAL_ENV": sys.prefix,
        "PATH": f"{Path(sys.prefix) / 'bin'}{os.pathsep}"
        f"{os.environ.get('PATH', '')}",
    }
    env.pop("FROST_CONFIG", None)  # exercise Frost's default lookup
    compiled = subprocess.run(
        ["lfc", str(Path("src") / f"{basename}.lf")],
        cwd=out_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert compiled.returncode == 0, compiled.stderr

    completed = subprocess.run(
        [str(out_dir / "bin" / basename)],
        cwd=out_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = completed.stdout + completed.stderr
    assert "Traceback" not in output, output
    return output


def test_quality_cell_cosimulation_reaches_passed(tmp_path: Path) -> None:
    output = _build_compile_run(
        SHOWCASE, "QualityCell::qualityStation", "qualityStation", tmp_path
    )
    assert "entered Cell.passed" in output, output
    # The Frost network layer came up alongside the co-simulation.
    assert output.count("registered to the link") == 2, output


def test_quality_cell_fmi2_cosimulation_reaches_passed(
    tmp_path: Path,
) -> None:
    """The same conversation against a real FMI 2.0 archive.

    The generated component self-hosts the slave (Frost's FrostFmu
    speaks the fmpy FMI 3.0 API only): setupExperiment ->
    initialization mode -> inline doStep. Reaching ``passed`` proves
    the whole 2.0 exchange — setInteger staging, the step, and the
    getBoolean verdict — against pythonfmu's ShapeCheckCell2.
    """
    output = _build_compile_run(
        SHOWCASE_FROST_DIR / "quality-cell-fmi2",
        "QualityCellFmi2::qualityStation2",
        "qualityStation2",
        tmp_path,
    )
    assert "entered Supervisor.passed" in output, output
    assert output.count("registered to the link") == 2, output


def test_quality_link_talks_over_the_frost_link(tmp_path: Path) -> None:
    """FMU and state chart joined only by a FrostChannel — no wire.

    The supervisor's ShapeCheck reaches the FMU as a method invocation
    routed by the link, and the FMU's passing Verdict comes back the
    same way; reaching ``passed`` proves both directions delivered.
    """
    output = _build_compile_run(
        SHOWCASE_FROST_DIR / "quality-link",
        "QualityLink::qualityLink",
        "qualityLink",
        tmp_path,
    )
    assert "entered Supervisor.passed" in output, output
    assert output.count("registered to the link") == 2, output
    # The link actually routed the invocations (DEBUG log of FrostLink).
    assert "FrostLink sent message" in output, output


def test_machine_only_pipeline_collects_and_stops(tmp_path: Path) -> None:
    """The frost-playground pipeline: 4 machines, no FMU, one link."""
    playground = MODELS_DIR / "frost-playground"
    output = _build_compile_run(
        playground / "multi-hop-pipeline",
        "Pipeline::pipeline",
        "pipeline",
        tmp_path,
        target_options=(("fast", "true"),),
    )
    assert output.count("registered to the link") == 4, output
    # Three items reach the sink (evens 2,4,6 doubled), then done stops
    # the program — the third exit has no re-entry.
    assert output.count("exited Sink.collecting") == 3, output
