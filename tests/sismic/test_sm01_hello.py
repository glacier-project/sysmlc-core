from __future__ import annotations

from typing import TYPE_CHECKING

from sismic.interpreter import Interpreter
from sismic.model import Statechart

from sysml2frost.sismic import build_statechart

if TYPE_CHECKING:
    import syside

MACHINE_QN = "SM01::Machine"


def test_builds(sm01_model: syside.Model) -> None:
    sc = build_statechart(sm01_model, MACHINE_QN)
    assert isinstance(sc, Statechart)


def test_reaches_final_state(sm01_model: syside.Model) -> None:
    sc = build_statechart(sm01_model, MACHINE_QN)
    interp = Interpreter(sc)
    interp.execute()
    assert "running" in interp.configuration
