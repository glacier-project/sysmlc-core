from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.loader import load_syside_model
from tests.generator.sismic.conftest import SM_EXAMPLES_BY_DIR

if TYPE_CHECKING:
    import syside

EXAMPLE = SM_EXAMPLES_BY_DIR["sm07-firing-order"]

STATE_DEF_QN = "SM07::MachineFiringOrder"


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(EXAMPLE.model_dir)


def test_firing_order_is_exit_then_effect_then_entry(
    model: syside.Model,
) -> None:
    """Source exit, transition effect, target entry run in §7.18.3 order.

    Their relative ordering is fixed by sismic's MicroStep
    (``_apply_step`` runs exit actions, then the transition action, then
    entry actions).
    """
    sc = build_statechart(model, STATE_DEF_QN)
    interpreter = Interpreter(sc)
    interpreter.execute()
    # exitAt < effectAt < entryAt, each action having run exactly once.
    assert interpreter.context["exitAt"] == 1
    assert interpreter.context["effectAt"] == 2
    assert interpreter.context["entryAt"] == 3
