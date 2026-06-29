from __future__ import annotations

from typing import TYPE_CHECKING

from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model
from tests.backends.test_sm_examples import SM_EXAMPLES_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from sismic.model import Statechart, Transition

SM14_DIR = SM_EXAMPLES_DIR / "sm14-call-effect"


def _transition_from(statechart: Statechart, source: str) -> Transition:
    """Return the single transition leaving ``source`` in ``statechart``."""
    matches = [t for t in statechart.transitions if t.source == source]
    assert len(matches) == 1
    return matches[0]


def test_builtin_call_effect_renders_and_runs() -> None:
    model = load_model(SM14_DIR)
    sc = build_statechart(model, "SM14::MachineAssignCall")

    assert _transition_from(sc, "a").action == "x = max(x, 0.0)"

    interpreter = Interpreter(sc)
    interpreter.execute()
    interpreter.context["x"] = -2.0
    interpreter.clock.time = 0.1
    interpreter.execute()
    assert interpreter.context["x"] == 0.0


def test_trig_call_renders_math_target_and_imports_math(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(
        tmp_path,
        """
        package TrigCall {
            private import ScalarValues::*;
            private import TrigFunctions::*;

            state def Machine {
                attribute x : Real := 0.0;
                entry; then idle;
                state idle;
                state running;
                transition first idle if TrigFunctions::cos(x) <= 1.0
                    then running;
            }
        }
        """,
    )

    sc = build_statechart(model, "TrigCall::Machine")

    assert sc.preamble.splitlines()[0] == "import math"
    assert sc.preamble.splitlines()[1] == "from types import SimpleNamespace"
    assert _transition_from(sc, "idle").guard == "math.cos(x) <= 1.0"
