from pathlib import Path

import pytest

from sysmlc.backends.statix.builder import build_statix
from sysmlc.backends.statix.serialize import emit_files

_FIX = Path(__file__).resolve().parent / "fixtures"

CASES = [
    ("sm01", "SM01::Machine", "machine"),
    ("sm02", "SM02::Machine", "machine"),
    ("sm03", "SM03::MachineRef", "machineref"),
    ("sm04", "SM04::MachineEntryIncrement", "machineentryincrement"),
    ("sm05", "SM05::MachineChainNested", "machinechainnested"),
    ("sm06", "SM06::MachineEffect", "machineeffect"),
    ("sm07", "SM07::MachineFiringOrder", "machinefiringorder"),
]

_SUFFIXES = (
    "statechart_ids.h",
    "statechart_config.c",
    "actions.c",
    "context.h",
)


@pytest.mark.parametrize("stem,qn,prefix", CASES)
def test_generated_c_matches_fixture(sm_models, stem, qn, prefix):
    files = emit_files(build_statix(sm_models[stem], qn))
    for suffix in _SUFFIXES:
        got = files[f"{prefix}_{suffix}"]
        golden = _FIX / stem / f"expected_{suffix}"
        assert got == golden.read_text(), f"{stem}:{suffix} drifted from golden"
