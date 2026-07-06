from __future__ import annotations

from typing import TYPE_CHECKING

from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model
from tests.backends.quake.conftest import transition_from
from tests.backends.test_sm_examples import SM_EXAMPLES_DIR

if TYPE_CHECKING:
    from pathlib import Path

SM14_DIR = SM_EXAMPLES_DIR / "sm14-call-effect"


def test_builtin_call_effect_renders_and_runs() -> None:
    model = load_model(SM14_DIR)
    sc = build_statechart(model, "SM14::MachineAssignCall")

    assert transition_from(sc, "a").action == "x = max(x, 0.0)"

    interpreter = Interpreter(sc)
    interpreter.execute()
    interpreter.context["x"] = -2.0
    interpreter.clock.time = 0.1
    interpreter.execute()
    assert interpreter.context["x"] == 0.0


def test_trig_call_renders_aliased_math_import(
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

    assert (
        sc.preamble.splitlines()[0]
        == "from math import cos as _cos, sin as _sin, tan as _tan"
    )
    assert sc.preamble.splitlines()[1] == "from types import SimpleNamespace"
    assert transition_from(sc, "idle").guard == "_cos(x) <= 1.0"


def test_trig_call_immune_to_attribute_named_cos(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(
        tmp_path,
        """
        package TrigShadow {
            private import ScalarValues::*;
            private import TrigFunctions::*;

            state def Machine {
                attribute cos : Real := 1.0;
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

    sc = build_statechart(model, "TrigShadow::Machine")

    interpreter = Interpreter(sc)
    interpreter.execute()
    assert interpreter.context["cos"] == 1.0
    assert "running" in interpreter.configuration
