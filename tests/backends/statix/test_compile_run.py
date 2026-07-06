from collections.abc import Callable
from pathlib import Path

import pytest

from sysmlc.backends.statix.builder import build_statix
from sysmlc.sysml.loading import load_model

pytestmark = pytest.mark.statix

_SELFLOOP = Path(__file__).resolve().parent / "fixtures" / "selfloop"


def test_sm01_settles_in_running(sm_models: dict, statix_run: Callable) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    assert statix_run(program) == "running"


def test_sm07_firing_order_reaches_b(
    sm_models: dict, statix_run: Callable
) -> None:
    program = build_statix(sm_models["sm07"], "SM07::MachineFiringOrder")
    assert statix_run(program) == "b"


def test_self_transition_is_external(statix_run: Callable) -> None:
    # External self-loop re-enters `a` (n -> 2), so completion fires a -> b.
    model = load_model(_SELFLOOP)
    program = build_statix(model, "SELFLOOP::MachineSelfLoop")
    assert statix_run(program, ("E",)) == "b"
