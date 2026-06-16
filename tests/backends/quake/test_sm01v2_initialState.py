from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm011-initialState"]
MACHINES = [
    "SM01v2::MachineInitial_ByEntry",
    "SM01v2::MachineInitial_ByTransition",
    "SM01v2::MachineInitial_ByQualifiedName",
    "SM01v2::MachineInitial_ByFeatureChain",
    "SM01v2::MachineInitial_NoDeclared",
]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


@pytest.mark.parametrize(
    "machine_qn,expected_state",
    [
        ("SM01v2::MachineInitial_ByEntry", "idle"),
        ("SM01v2::MachineInitial_ByTransition", "idle"),
        (
            "SM01v2::MachineInitial_ByQualifiedName",
            "container::idle",
        ),
        (
            "SM01v2::MachineInitial_ByFeatureChain",
            "container::idle",
        ),
        ("SM01v2::MachineInitial_NoDeclared", "idle"),
    ],)
def test_idle_is_active_after_initialization(
    model: syside.Model,
    machine_qn: str,
    expected_state: str,
) -> None:
    """All supported SysML initial-state syntaxes activate `idle`."""
    sc = build_statechart(model, machine_qn)

    interp = Interpreter(sc)
    interp.execute_once()

    assert expected_state in interp.configuration