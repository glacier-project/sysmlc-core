"""Signal-interface collector for SysML state definitions.

Drives a state machine through the generic ``StateMachineDriver`` using a
lightweight ``TargetBuilder`` that records only which signal names the machine
*accepts* (via SIGNAL triggers) and which it *sends* (via ``send`` actions in
entry/do/exit slots and transition effects).  No artifact is rendered, so
models that a full backend would reject can still yield their interface.
"""

from __future__ import annotations

from dataclasses import dataclass

import syside

from sysmlc.codegen.python import payload_signature
from sysmlc.semantics.statemachine import actions
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import (
    AttributeBinding,
    StateFact,
    TransitionFact,
    TriggerKind,
)


@dataclass(frozen=True)
class MachineInterface:
    """The signal surface of one state machine."""

    accepted: frozenset[str]
    sent: frozenset[str]


class SignalInterfaceCollector:
    """A TargetBuilder that records signal names and nothing else.

    Used to learn what a peer machine accepts/sends before the real
    build; it renders nothing, so models that the rosetta builder would
    reject still yield their interface.
    """

    def __init__(self) -> None:
        self._accepted: set[str] = set()
        self._sent: set[str] = set()

    def bind_attribute(self, binding: AttributeBinding) -> None:
        """Ignore attributes (the interface is signals only)."""

    def add_state(self, state: StateFact) -> None:
        """Scan the state's action slots for sends."""
        for slot in (state.entry_action, state.do_action, state.exit_action):
            self._scan(slot)

    def add_transition(self, transition: TransitionFact) -> None:
        """Record a signal trigger; scan the effect for sends."""
        trigger = transition.trigger
        if trigger is not None and trigger.kind is TriggerKind.SIGNAL:
            assert trigger.signal_name is not None
            self._accepted.add(trigger.signal_name)
        self._scan(transition.effect)

    def result(self) -> MachineInterface:
        """Return the collected interface."""
        return MachineInterface(
            accepted=frozenset(self._accepted), sent=frozenset(self._sent)
        )

    def _scan(self, slot: syside.ActionUsage | None) -> None:
        for action in actions.inline_actions(slot):
            if isinstance(action, syside.SendActionUsage):
                event_name, _pairs = payload_signature(action)
                self._sent.add(event_name)


def machine_interface(
    model: syside.Model, state_def_qn: str
) -> MachineInterface:
    """Collect the accepted/sent signal names of one state definition."""
    result = StateMachineDriver(model).run(
        state_def_qn, SignalInterfaceCollector()
    )
    assert isinstance(result, MachineInterface)
    return result
