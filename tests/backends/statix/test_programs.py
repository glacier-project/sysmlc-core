from pathlib import Path

import pytest

from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.serialize import _paths, emit_files

_FIX = Path(__file__).resolve().parent / "fixtures"

CASES = [
    ("sm01", "SM01::Machine", "sm01"),
    ("sm02", "SM02::Machine", "sm02"),
    ("sm03", "SM03::MachineRef", "sm03"),
    ("sm04", "SM04::MachineEntryIncrement", "sm04"),
    ("sm05", "SM05::MachineChainNested", "sm05"),
    ("sm06", "SM06::MachineEffect", "sm06"),
    ("sm07", "SM07::MachineFiringOrder", "sm07"),
    ("sm11", "SM11::MachineMixed", "sm11_machine_mixed"),
]


@pytest.mark.parametrize("stem,qn,fix_dir", CASES)
def test_generated_c_matches_fixture(
    sm_models: dict, stem: str, qn: str, fix_dir: str
) -> None:
    program = build_statix(sm_models[stem], qn)
    files = emit_files(program)
    d, s = _paths(program)
    checks: tuple[tuple[str, str], ...]
    if fix_dir == "sm11_machine_mixed":
        checks = (
            (f"include/{d}/{s}.h", f"include/{d}/{s}.h"),
            (f"src/{d}/{s}.c", f"src/{d}/{s}.c"),
            (f"host/{d}/{s}_runner.c", f"host/{d}/{s}_runner.c"),
            ("CMakeLists.txt", "CMakeLists.txt"),
        )
    else:
        checks = (
            (f"include/{d}/{s}.h", "expected.h"),
            (f"src/{d}/{s}.c", "expected.c"),
            (f"host/{d}/{s}_runner.c", "expected_runner.c"),
        )
    for key, expected in checks:
        golden = _FIX / fix_dir / expected
        assert files[key] == golden.read_text(), f"{fix_dir}:{key} drifted"
