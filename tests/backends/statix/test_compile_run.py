import pytest

from sysmlc.backends.statix.builder import build_statix

pytestmark = pytest.mark.statix


def test_sm01_settles_in_running(sm_models, statix_run):
    program = build_statix(sm_models["sm01"], "SM01::Machine")
    # idle(0) -> running(1) via the completion micro-step on init.
    assert statix_run(program) == 1


def test_sm07_firing_order_reaches_b(sm_models, statix_run):
    program = build_statix(sm_models["sm07"], "SM07::MachineFiringOrder")
    # a(0) -> b(1) via completion; exit(a) -> effect -> entry(b) all run.
    assert statix_run(program) == 1
