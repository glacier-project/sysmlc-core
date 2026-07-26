from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sysmlc.semantics.statemachine.facts import (
        AttributeBinding,
        StateFact,
        TransitionFact,
    )


class TargetBuilder(Protocol):
    """Receives neutral state-machine facts and assembles a target artifact.

    The generic ``StateMachineDriver`` pushes facts in. Each backend implements
    this protocol to build its own artifact (a statechart, a reactor
    program, a C project, ...), rendering any carried syside nodes with
    its own codegen.
    """

    def bind_attribute(self, binding: AttributeBinding) -> None:
        """Seed an attribute value into the given scope."""
        ...

    def add_state(self, state: StateFact) -> None:
        """Register a state node."""
        ...

    def add_transition(self, transition: TransitionFact) -> None:
        """Register a transition between states."""
        ...

    def result(self) -> object:
        """Return the completed target artifact."""
        ...
