from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysmlc.backends.quake import build_statechart
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model
from tests.backends.quake.conftest import SM_EXAMPLES_BY_DIR, quake_preamble

if TYPE_CHECKING:
    from pathlib import Path

    import syside
    from sismic.model import Statechart, Transition

EXAMPLE = SM_EXAMPLES_BY_DIR["sm18-enum-literals"]


def _transition(sc: Statechart, source: str, target: str) -> Transition:
    """The transition from ``source`` to ``target``."""
    for transition in sc.transitions:
        if transition.source == source and transition.target == target:
            return transition
    raise AssertionError(f"no transition {source} -> {target}")


def _action_of(sc: Statechart, source: str, target: str) -> str | None:
    """The action string of the transition from ``source`` to ``target``."""
    action: str | None = _transition(sc, source, target).action
    return action


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(EXAMPLE.model_dir)


def test_string_enum_default_projects_to_value(model: syside.Model) -> None:
    """A String-valued literal default projects to its declared value."""
    sc = build_statechart(model, "SM18::MachineStringEnum")
    assert sc.preamble == quake_preamble('c = "red"')


def test_string_enum_effect_projects_to_value(model: syside.Model) -> None:
    """A String-valued literal in an effect projects to its value."""
    sc = build_statechart(model, "SM18::MachineStringEnum")
    assert _action_of(sc, "idle", "green") == 'c = "green"'


def test_string_enum_guard_projects_to_value(model: syside.Model) -> None:
    """A String-valued literal in a guard projects to its value."""
    sc = build_statechart(model, "SM18::MachineStringEnum")
    assert _transition(sc, "green", "matched").guard == 'c == "green"'


def test_real_enum_default_projects_to_float(model: syside.Model) -> None:
    """A Real-valued literal default projects to its float value."""
    sc = build_statechart(model, "SM18::MachineRealEnum")
    assert sc.preamble == quake_preamble("g = 4.0")


def test_real_enum_guard_projects_to_float(model: syside.Model) -> None:
    """A Real-valued literal in a numeric guard projects to its float."""
    sc = build_statechart(model, "SM18::MachineRealEnum")
    assert _transition(sc, "grading", "passed").guard == "g >= 3.0"


def test_plain_enum_default_projects_to_name(model: syside.Model) -> None:
    """A plain symbolic literal default projects to its name as a string."""
    sc = build_statechart(model, "SM18::MachinePlainEnum")
    assert sc.preamble == quake_preamble('m = "idle"')


def test_plain_enum_effect_projects_to_name(model: syside.Model) -> None:
    """A plain symbolic literal in an effect projects to its name."""
    sc = build_statechart(model, "SM18::MachinePlainEnum")
    assert _action_of(sc, "ready", "working") == 'm = "busy"'


def test_plain_enum_guard_projects_to_name(model: syside.Model) -> None:
    """A plain symbolic literal in a guard projects to its name."""
    sc = build_statechart(model, "SM18::MachinePlainEnum")
    assert _transition(sc, "working", "checked").guard == 'm == "busy"'


def test_enum_literal_send_payload_projects_to_value(
    model: syside.Model,
) -> None:
    """A literal send payload argument projects to its declared value."""
    sc = build_statechart(model, "SM18::MachineEnumPayload")
    assert _action_of(sc, "idle", "armed") == 'send("Announce", color="yellow")'


def test_string_enum_guard_gates_at_runtime(model: syside.Model) -> None:
    """The projected String-enum guard actually gates the transition."""
    sc = build_statechart(model, "SM18::MachineStringEnum")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "matched" in interpreter.configuration
    assert interpreter.context["c"] == "green"


def test_real_enum_guard_gates_at_runtime(model: syside.Model) -> None:
    """The projected Real-enum guard actually gates the transition."""
    sc = build_statechart(model, "SM18::MachineRealEnum")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "passed" in interpreter.configuration


def test_plain_enum_guard_gates_at_runtime(model: syside.Model) -> None:
    """The projected plain-enum guard actually gates the transition."""
    sc = build_statechart(model, "SM18::MachinePlainEnum")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "checked" in interpreter.configuration
    assert interpreter.context["m"] == "busy"


def test_enum_payload_send_drives_accept_end_to_end(
    model: syside.Model,
) -> None:
    """The enum-payload self-send drives the same-machine accept."""
    sc = build_statechart(model, "SM18::MachineEnumPayload")
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "fired" in interpreter.configuration


COMPUTED_VALUE_MODEL = """
package ComputedEnum {
    private import ScalarValues::*;

    enum def K :> Real {
        N = 2.0 + 2.0;
    }

    state def Machine {
        attribute x : Real := 3.0;
        entry;
            then s1;
        state s1;
        state s2;
        transition first s1 if x * K::N == 12.0 then s2;
    }
}
"""


def test_computed_enum_value_is_parenthesized(tmp_path: Path) -> None:
    """A non-atomic declared value keeps its grouping at the reference site.

    The projected value substitutes into the literal reference's atom
    position, so a computed value must be parenthesized: without parens,
    ``x * K::N`` with ``N = 2.0 + 2.0`` would emit ``x * 2.0 + 2.0`` and
    silently regroup the arithmetic.
    """
    model = _load_inline_model(tmp_path, COMPUTED_VALUE_MODEL)
    sc = build_statechart(model, "ComputedEnum::Machine")
    guard = _transition(sc, "s1", "s2").guard
    assert guard == "x * (2.0 + 2.0) == 12.0"
    interpreter = Interpreter(sc)
    interpreter.execute()
    assert "s2" in interpreter.configuration
