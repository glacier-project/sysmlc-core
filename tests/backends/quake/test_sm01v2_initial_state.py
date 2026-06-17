from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm011-initial_state"]


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


@pytest.mark.parametrize(
    "machine_qn,expected_state,expect_error",
    [
        ("SM01v2::MachineInitial1_ByTransition", "idle", False),
        ("SM01v2::MachineInitial2_ByEntry", "idle", False),
        ("SM01v2::MachineInitial3_ByQualifiedName", "container::idle", False),
        ("SM01v2::MachineInitial4_ByFeatureChain", "container::idle", False),
        ("SM01v2::MachineInitial5_NoDeclared_TestError", None, True),
    ],
)
def test_idle_is_active_after_initialization(
    model: syside.Model,
    machine_qn: str,
    expected_state: str | None,
    expect_error: bool,
) -> None:
    """All supported SysML initial-state syntaxes activate `idle`,
    while undeclared raises ValueError."""

    if expect_error:
        with pytest.raises(ValueError, match="No initial state for"):
            build_statechart(model, machine_qn)
    else:
        sc = build_statechart(model, machine_qn)

        interp = Interpreter(sc)
        interp.execute_once()

        assert expected_state in interp.configuration
