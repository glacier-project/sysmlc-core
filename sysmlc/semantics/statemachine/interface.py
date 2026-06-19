"""Signal-interface collector for SysML state definitions.

Drives a state machine through the generic ``StateMachineDriver`` using a
lightweight ``TargetBuilder`` that records only which signal names the machine
*accepts* (via SIGNAL triggers) and which it *sends* (via ``send`` actions in
entry/do/exit slots and transition effects).  No artifact is rendered, so
models that a full backend would reject can still yield their interface.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

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
    """The signal surface of one state machine.

    ``accepted``/``sent`` are the flat name sets the rig path consumes. The
    ``*_via`` maps additionally scope each signal to the ``via`` port it
    travels through (``accept E via p`` / ``send E via p``), which the part
    assembler uses for port-based connection routing; a signal with no
    ``via`` port keys on ``None``. The maps are additive — the rig path reads
    only the flat sets, so its output is unchanged.
    """

    accepted: frozenset[str]
    sent: frozenset[str]
    accepted_via: dict[str | None, frozenset[str]] = field(default_factory=dict)
    sent_via: dict[str | None, frozenset[str]] = field(default_factory=dict)


class SignalInterfaceCollector:
    """A TargetBuilder that records signal names and nothing else.

    Used to learn what a peer machine accepts/sends before the real
    build; it renders nothing, so models that the rosetta builder would
    reject still yield their interface.
    """

    def __init__(self) -> None:
        self._accepted: set[str] = set()
        self._sent: set[str] = set()
        self._accepted_via: dict[str | None, set[str]] = defaultdict(set)
        self._sent_via: dict[str | None, set[str]] = defaultdict(set)

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
            self._accepted_via[trigger.via_port].add(trigger.signal_name)
        self._scan(transition.effect)

    def result(self) -> MachineInterface:
        """Return the collected interface."""
        return MachineInterface(
            accepted=frozenset(self._accepted),
            sent=frozenset(self._sent),
            accepted_via=_freeze(self._accepted_via),
            sent_via=_freeze(self._sent_via),
        )

    def _scan(self, slot: syside.ActionUsage | None) -> None:
        for action in actions.inline_actions(slot):
            if isinstance(action, syside.SendActionUsage):
                event_name, _pairs = payload_signature(action)
                self._sent.add(event_name)
                self._sent_via[_send_via_port(action)].add(event_name)


def machine_interface(
    model: syside.Model, state_def_qn: str
) -> MachineInterface:
    """Collect the accepted/sent signal names of one state definition."""
    result = StateMachineDriver(model).run(
        state_def_qn, SignalInterfaceCollector()
    )
    assert isinstance(result, MachineInterface)
    return result


def _send_via_port(send: syside.SendActionUsage) -> str | None:
    """Return the simple name of a send's ``via`` (sender) port, or None.

    ``send E via p`` stores ``p`` as the sender argument (a
    ``FeatureReferenceExpression`` whose referent is the ``PortUsage``) —
    the mirror of the accepter's ``receiver_argument`` (``triggers._via_port``).
    """
    sender = send.sender_argument
    if isinstance(sender, syside.FeatureReferenceExpression):
        referent = sender.referent
        if referent is not None:
            return referent.name
    return None


def _freeze(
    via: dict[str | None, set[str]],
) -> dict[str | None, frozenset[str]]:
    return {port: frozenset(signals) for port, signals in via.items()}
