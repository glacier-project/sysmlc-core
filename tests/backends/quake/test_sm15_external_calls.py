from __future__ import annotations

import pytest
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

from sysmlc.backends.quake import build_statechart
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.loading import load_model
from tests.backends.quake.conftest import transition_from

SM15_DIR = SM_EXAMPLES_DIR / "sm15-external"


def test_external_call_builds_sm15_ramp() -> None:
    model = load_model(SM15_DIR)
    sc = build_statechart(
        model, "SM15::Ramp", external=("ramp", frozenset({"step"}))
    )

    assert transition_from(sc, "run").action == "x = step(x, 0.1)"
    assert "from ramp import step" in sc.preamble.splitlines()


def test_unused_external_names_are_not_imported() -> None:
    # Importing a function the machine never calls would make the emitted
    # statechart depend on the module for no reason.
    model = load_model(SM15_DIR)
    sc = build_statechart(
        model,
        "SM15::Ramp",
        external=("ramp", frozenset({"step", "unused"})),
    )

    lines = sc.preamble.splitlines()
    assert "from ramp import step" in lines
    assert "from ramp import unused" not in lines


def test_missing_external_function_names_function_and_module() -> None:
    model = load_model(SM15_DIR)
    with pytest.raises(
        UnsupportedConstructError, match=r"step.*phys|phys.*step"
    ):
        build_statechart(model, "SM15::Ramp", external=("phys", frozenset()))
