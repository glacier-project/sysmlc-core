import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.statix

_C_DIR = Path(__file__).resolve().parent / "c"


def test_hand_written_c_runtime_tests_pass(tmp_path: Path) -> None:
    """Build and run tests/backends/statix/c/ (CMake+ctest) as part of CI.

    This harness instantiates sc_machine.h directly (below the level a
    generated-and-compiled model probes conveniently) -- it is the only place
    the parallel-region dispatch algorithm (fork/broadcast/join/timers) is
    exercised in isolation from the Python builder/serializer. Previously not
    wired into any executed pytest/CI path; see
    docs/superpowers/specs/2026-07-14-statix-parallel-regions-design.md Sec.10.
    """
    build = tmp_path / "build"
    subprocess.run(
        ["cmake", "-S", str(_C_DIR), "-B", str(build)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["cmake", "--build", str(build)], check=True, capture_output=True
    )
    result = subprocess.run(
        ["ctest", "--output-on-failure"],
        cwd=build,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
