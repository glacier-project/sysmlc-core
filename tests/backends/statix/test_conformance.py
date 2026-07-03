import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake.builder import build_statechart
from sysmlc.backends.statix.builder import build_statix
from typing import Callable

pytestmark = pytest.mark.statix

# Flat eventless machines whose settled state is deterministic on init.
CASES = [
    ("sm01", "SM01::Machine"),
    ("sm03", "SM03::MachineRef"),
    ("sm04", "SM04::MachineEntryIncrement"),
    ("sm06", "SM06::MachineEffect"),
]


@pytest.mark.parametrize("stem,qn", CASES)
def test_final_state_matches_sismic(
    sm_models: dict,
    statix_run: Callable,
    stem: str,
    qn: str,
) -> None:
    # Sismic reference (quake): settle on init, read the active leaf.
    interpreter = Interpreter(build_statechart(sm_models[stem], qn))
    interpreter.execute()
    sismic_leaf = sorted(interpreter.configuration)[-1]

    # statix C: build, compile, run the generated host runner.
    program = build_statix(sm_models[stem], qn)
    statix_leaf = statix_run(program)

    assert (
        statix_leaf == sismic_leaf
    ), f"{stem}: statix {statix_leaf!r} != sismic {sismic_leaf!r}"
