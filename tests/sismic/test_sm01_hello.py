from __future__ import annotations

from typing import TYPE_CHECKING

from sismic.interpreter import Interpreter
from sismic.model import Statechart, Transition

from sysml2frost.sismic import build_statechart

if TYPE_CHECKING:
    import syside

MACHINE_QN = "SM01::Machine"


def test_build_statechart_returns_statechart_instance(
    sm01_model: syside.Model,
) -> None:
    """The builder returns a sismic ``Statechart`` from a SysML state def."""
    sc = build_statechart(sm01_model, MACHINE_QN)
    assert isinstance(sc, Statechart)


def test_initial_substate_idle_is_active_after_initial_entry(
    sm01_model: syside.Model,
) -> None:
    """The ``then idle`` succession makes ``idle`` the initial substate.

    Per SysML v2 OMG spec, §7.18.2 "State Definitions and Usages":

        The initial state usage to be performed is indicated by a
        succession from the entry action to that state usage. […]
        A shorthand may also be used for a succession whose source is
        the entry action, consisting of the keyword `then` followed
        by a qualified name or feature chain for the target state
        usage, placed immediately after the entry action declaration.

    The generator must encode this as the parent CompoundState's
    ``initial="idle"`` — verified by checking ``idle`` is in the
    configuration after the first MacroStep.
    """
    sc = build_statechart(sm01_model, MACHINE_QN)
    interp = Interpreter(sc)
    interp.execute_once()
    assert "idle" in interp.configuration


def test_only_idle_to_running_transition_is_declared(
    sm01_model: syside.Model,
) -> None:
    """The Statechart has exactly one transition (no phantoms).

    Per SysML v2 OMG spec, §7.18.3 "Transition Usages", Note:

        An entry action can have outgoing transitions, but they will
        have the same semantics as conditional successions.

    The SysML declares one ``transition`` keyword; the
    ``entry; then idle;`` succession is *structural*, not a
    ``TransitionUsage``. The generator must not synthesize phantom
    transitions for it. Pins the structural counterpart to the
    runtime check that initial entry fires no transition.
    """
    sc = build_statechart(sm01_model, MACHINE_QN)
    assert len(sc.transitions) == 1
    only = sc.transitions[0]
    assert isinstance(only, Transition)
    assert only.source == "idle"
    assert only.target == "running"
