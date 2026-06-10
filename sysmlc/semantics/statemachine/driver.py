from __future__ import annotations

from typing import TYPE_CHECKING

import syside

from sysmlc.semantics.statemachine import (
    attributes,
    states,
    transitions,
    triggers,
)
from sysmlc.semantics.statemachine.facts import (
    AttributeBinding,
    StateFact,
    StateKind,
    TransitionFact,
)
from sysmlc.sysml.queries import resolve

if TYPE_CHECKING:
    from sysmlc.semantics.statemachine.target import TargetBuilder


class StateMachineDriver:
    """Walk a SysML state definition and push neutral facts to a TargetBuilder.

    The driver is generic over the target paradigm and language: it resolves,
    classifies, and walks the source state machine, then pushes neutral facts
    (``StateFact`` / ``TransitionFact`` / ``AttributeBinding``, which carry raw
    syside nodes) to the backend's ``TargetBuilder``. It renders nothing and
    knows nothing about statecharts.
    """

    def __init__(self, model: syside.Model) -> None:
        """Initialize the driver.

        Args:
            model: The loaded syside model containing the state definition.
        """
        self._model = model
        self._compiler = syside.Compiler()
        self._stdlib = syside.Stdlib(model.index)

    def run(self, state_def_qn: str, builder: TargetBuilder) -> object:
        """Drive ``builder`` to assemble the artifact for ``state_def_qn``.

        Args:
            state_def_qn: Qualified name of the SysML ``state def`` to walk.
            builder: The backend collaborator that assembles the artifact.

        Returns:
            The artifact returned by ``builder.result()``.
        """
        state_def = resolve(self._model, syside.StateDefinition, state_def_qn)
        self._bind_attributes(state_def, builder)
        assert state_def.name is not None
        self._walk_states(state_def, state_def, state_def.name, None, builder)
        self._walk_transitions(state_def, state_def, builder)
        return builder.result()

    def _bind_attributes(
        self, state_def: syside.StateDefinition, builder: TargetBuilder
    ) -> None:
        for scope, attr in attributes.iter_scope_attributes(state_def):
            assert attr.name is not None
            scope_path = (
                ""
                if isinstance(scope, syside.StateDefinition)
                else states.state_path(state_def, scope)
            )
            builder.bind_attribute(
                AttributeBinding(
                    scope=scope_path,
                    name=attr.name,
                    value=attributes.bind_value(
                        attr, self._compiler, self._stdlib
                    ),
                )
            )

    def _walk_states(
        self,
        state_def: syside.StateDefinition,
        container: syside.StateDefinition | syside.StateUsage,
        name: str,
        parent: str | None,
        builder: TargetBuilder,
    ) -> None:
        kind = states.state_kind(container)
        initial = (
            states.state_path(state_def, states.resolve_initial(container))
            if kind is StateKind.COMPOSITE
            else None
        )
        builder.add_state(
            StateFact(
                name=name,
                kind=kind,
                parent=parent,
                initial_substate=initial,
                entry_action=container.entry_action,
                do_action=container.do_action,
                exit_action=container.exit_action,
            )
        )
        for substate in states.substates(container):
            self._walk_states(
                state_def,
                substate,
                states.state_path(state_def, substate),
                name,
                builder,
            )

    def _walk_transitions(
        self,
        state_def: syside.StateDefinition,
        container: syside.StateDefinition | syside.StateUsage,
        builder: TargetBuilder,
    ) -> None:
        for trans in transitions.container_transitions(container):
            builder.add_transition(
                TransitionFact(
                    source=transitions.source_path(state_def, trans),
                    target=transitions.target(state_def, trans, container),
                    trigger=triggers.classify(
                        trans, self._compiler, self._stdlib
                    ),
                    guard=trans.guard_expression,
                    effect=trans.effect_action,
                )
            )
        for substate in states.substates(container):
            if states.substates(substate):
                self._walk_transitions(state_def, substate, builder)
