import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import syside

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.program import CProgram
from sysmlc.sysml.loading import load_model

_MODELS = Path(__file__).resolve().parents[3] / "models" / "sm-examples"

# The sm-examples referenced across the statix backend tests, by folder stem.
_WANTED = {
    "sm01",
    "sm02",
    "sm03",
    "sm04",
    "sm05",
    "sm06",
    "sm07",
    "sm08",
    "sm09",
    "sm11",
}


@pytest.fixture(scope="session")
def sm_models() -> dict[str, syside.Model]:
    """Load each referenced sm-example once, keyed by folder stem (sm01…)."""
    out: dict[str, syside.Model] = {}
    for folder in sorted(_MODELS.glob("sm*-*")):
        stem = folder.name.split("-")[0]
        if stem in _WANTED:
            out[stem] = load_model(folder)
    return out


@pytest.fixture
def statix_run(
    tmp_path: Path,
) -> Callable[..., str]:
    """Return a callable that builds, compiles, and runs a program.

    The callable writes the generated project, compiles it via the generated
    CMake (under the strict warning set), runs the generated host runner, and
    returns the final state name printed by the runner.
    """

    def _run(program: CProgram, events: tuple[str, ...] = ()) -> str:
        StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
        build = tmp_path / "build"
        subprocess.run(
            ["cmake", "-S", str(tmp_path), "-B", str(build)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["cmake", "--build", str(build)],
            check=True,
            capture_output=True,
        )
        out = subprocess.run(
            [str(build / f"{program.prefix}_runner"), *events],
            check=True,
            capture_output=True,
            text=True,
        )
        last = out.stdout.strip().splitlines()[-1]
        return last.rsplit("state=", maxsplit=1)[1].strip()

    return _run
