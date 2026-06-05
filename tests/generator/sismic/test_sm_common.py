from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysml2frost.loader import load_syside_model
from sysml2frost.generator.sismic import build_statechart
from tests.generator.sismic.conftest import ALL_EXAMPLE_QN_PAIRS

if TYPE_CHECKING:
    from tests.generator.sismic.conftest import SmExample


@pytest.mark.parametrize(
    ("example", "state_def_qn"),
    ALL_EXAMPLE_QN_PAIRS,
    ids=[f"{ex.dir_name}::{qn}" for ex, qn in ALL_EXAMPLE_QN_PAIRS],
)
def test_statechart_executes_without_evaluation_error(
    example: SmExample,
    state_def_qn: str,
) -> None:
    """``Interpreter(sc).execute()`` must not raise for any state def.

    Corpus-wide invariant: every ``state def`` in every example folder
    under ``models/sm-examples/`` must produce a sismic ``Statechart``
    whose initial-quiescence run goes through without
    ``CodeEvaluationError`` (the symptom of a name referenced in a
    guard, action, invariant or preamble that the generator forgot to
    seed). Catches regressions where a guard / action references a
    SysML attribute the builder failed to emit into the preamble, or
    a future generator branch leaves an undefined identifier in
    emitted Python.
    """
    model = load_syside_model(example.model_dir)
    sc = build_statechart(model, state_def_qn)
    Interpreter(sc).execute()
