from collections.abc import Callable

import pytest

from sysmlc.backends.statix.builder import build_statix

pytestmark = pytest.mark.statix


def test_sm01_settles_in_running(sm_models: dict, statix_run: Callable) -> None:
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    assert statix_run(program) == "running"


def test_sm07_firing_order_reaches_b(
    sm_models: dict, statix_run: Callable
) -> None:
    program = build_statix(sm_models["sm07"], "SM07::MachineFiringOrder")
    assert statix_run(program) == "b"
