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
    "sm10",
    "sm11",
    "sm12",
    "sm17",
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


def _run_last_line(
    tmp_path: Path,
    program: CProgram,
    events: tuple[str, ...],
    check: bool = True,
) -> str:
    """Write, compile, and run a program; return runner's last stdout line."""
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
        check=check,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip().splitlines()[-1]


@pytest.fixture
def statix_run(tmp_path: Path) -> Callable[..., str]:
    """Build, compile, and run a program; return the final state name."""

    def _run(program: CProgram, events: tuple[str, ...] = ()) -> str:
        line = _run_last_line(tmp_path, program, events)
        tail = line.rsplit("state=", maxsplit=1)[1].strip()
        return tail.split()[0]

    return _run


@pytest.fixture
def statix_run_final(tmp_path: Path) -> Callable[..., tuple[str, bool]]:
    """Build, compile, run a program; return (final state name, is_final)."""

    def _run(
        program: CProgram, events: tuple[str, ...] = ()
    ) -> tuple[str, bool]:
        line = _run_last_line(tmp_path, program, events)
        tokens = line.rsplit("state=", maxsplit=1)[1].strip().split()
        leaf = tokens[0]
        final = any(tok == "final=1" for tok in tokens[1:])
        return leaf, final

    return _run


@pytest.fixture
def statix_run_status(tmp_path: Path) -> Callable[..., str]:
    """Build/compile/run; return the runner's last status= token.

    Tolerant of a non-zero exit, so a constraint violation (which makes the
    runner exit 1 after printing status=SC_STATUS_CONSTRAINT_VIOLATED) is
    observable rather than raising.
    """

    def _run(program: CProgram, events: tuple[str, ...] = ()) -> str:
        line = _run_last_line(tmp_path, program, events, check=False)
        return line.rsplit("status=", maxsplit=1)[1].split()[0]

    return _run
