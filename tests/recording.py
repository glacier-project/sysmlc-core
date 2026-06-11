from sysmlc.semantics.statemachine.facts import (
    AttributeBinding,
    StateFact,
    TransitionFact,
)


class RecordingBuilder:
    """A ``TargetBuilder`` test double that records every fact pushed to it."""

    def __init__(self) -> None:
        self.attributes: list[AttributeBinding] = []
        self.states: list[StateFact] = []
        self.transitions: list[TransitionFact] = []

    def bind_attribute(self, binding: AttributeBinding) -> None:
        self.attributes.append(binding)

    def add_state(self, state: StateFact) -> None:
        self.states.append(state)

    def add_transition(self, transition: TransitionFact) -> None:
        self.transitions.append(transition)

    def result(self) -> object:
        return None
