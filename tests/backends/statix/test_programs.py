from pathlib import Path

import pytest

from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.serialize import emit_files

_FIX = Path(__file__).resolve().parent / "fixtures"

CASES = [
    ("sm01", "SM01::Machine", "sm01_machine"),
    ("sm02", "SM02::Machine", "sm02_machine"),
    ("sm03", "SM03::MachineRef", "sm03_machineref"),
    ("sm04", "SM04::MachineEntryIncrement", "sm04_machineentryincrement"),
    ("sm05", "SM05::MachineChainNested", "sm05_machinechainnested"),
    ("sm06", "SM06::MachineEffect", "sm06_machineeffect"),
    ("sm07", "SM07::MachineFiringOrder", "sm07_machinefiringorder"),
]

# (emitted key suffix, golden filename)
_FILES = (
    (".h", "expected.h"),
    (".c", "expected.c"),
    ("_runner.c", "expected_runner.c"),
)


@pytest.mark.parametrize("stem,qn,prefix", CASES)
def test_generated_c_matches_fixture(sm_models, stem, qn, prefix):
    files = emit_files(build_statix(sm_models[stem], qn))
    for suffix, expected in _FILES:
        got = files[f"{prefix}{suffix}"]
        golden = _FIX / stem / expected
        assert got == golden.read_text(), f"{stem}:{suffix} drifted from golden"
