from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm01-helloworld"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


@pytest.mark.parametrize(
    "machine_qn,expected_state",
    [
        ("SM01::MachineInitial1_ByTransition", "idle"),
        ("SM01::MachineInitial2_ByEntry", "idle"),
        ("SM01::MachineInitial3_ByQualifiedName", "container::idle"),
        ("SM01::MachineInitial4_ByFeatureChain", "container::idle"),
    ],
)
def test_supported_initial_state_spellings_activate_idle(
    model: syside.Model,
    machine_qn: str,
    expected_state: str,
) -> None:
    """All supported SysML initial-state syntaxes activate `idle`."""
    sc = build_statechart(model, machine_qn)

    interp = Interpreter(sc)
    interp.execute_once()

    assert expected_state in interp.configuration
