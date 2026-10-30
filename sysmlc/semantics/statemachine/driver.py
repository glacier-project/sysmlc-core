from __future__ import annotations

from typing import TYPE_CHECKING

import syside

from sysmlc.semantics.statemachine import (
    attributes,
    bindings,
    constraints,
    states,
    transitions,
    triggers,
)
from sysmlc.semantics.statemachine.facts import (
    AttributeBinding,
    ConstraintFact,
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
    knows nothing about statecharts. Bound (``=``) values, including those
    of inherited attributes, and the assignments in every action slot are
    admitted (see ``bindings``) before the facts carrying them are pushed.
    """

    def __init__(self, model: syside.Model) -> None:
        """Initialize the driver.

        Args:
            model: The loaded syside model containing the state definition.
        """
        self._model = model
        self._compiler = syside.Compiler()
        self._stdlib = syside.Stdlib(model.index)

    def run(
        self,
        state_def_qn: str,
        builder: TargetBuilder,
        *,
        strict_signals: bool = False,
    ) -> object:
        """Drive ``builder`` to assemble the artifact for ``state_def_qn``.

        Args:
            state_def_qn: Qualified name of the SysML ``state def`` to walk.
            builder: The backend collaborator that assembles the artifact.
            strict_signals: Reject unresolved, untyped or value-bound signal
                accepts instead of using legacy classification.

        Returns:
            The artifact returned by ``builder.result()``.

        Raises:
            UnsupportedConstructError: If executable actions or strict signal
                accepts use unsupported forms.
            ValueError: If state resolution or structural/trigger semantics
                are invalid.
        """
        state_def = resolve(self._model, syside.StateDefinition, state_def_qn)
        set_compiler_context = getattr(builder, "set_compiler_context", None)
        if set_compiler_context is not None:
            set_compiler_context(self._compiler, self._stdlib)
        self._bind_attributes(state_def, builder)
        self._bind_constraints(state_def, builder)
        assert state_def.name is not None
        self._walk_states(state_def, state_def, state_def.name, None, builder)
        self._walk_transitions(
            state_def,
            state_def,
            builder,
            transitions.declaration_order(state_def),
            strict_signals,
        )
        return builder.result()

    def _bind_attributes(
        self, state_def: syside.StateDefinition, builder: TargetBuilder
    ) -> None:
        bindings.require_no_inherited_bindings(state_def)
        for scope, attr in attributes.iter_scope_attributes(state_def):
            assert attr.name is not None
            scope_path = (
                ""
                if isinstance(scope, syside.StateDefinition)
                else states.state_path(state_def, scope)
            )
            defs_iter = getattr(attr, "attribute_definitions", None) or getattr(
                attr, "definitions", None
            )
            type_def = (
                next(
                    (
                        d
                        for d in defs_iter.collect()
                        if getattr(d, "name", None)
                    ),
                    None,
                )
                if defs_iter is not None
                else None
            )
            type_name = type_def.name if type_def is not None else None
            builder.bind_attribute(
                AttributeBinding(
                    scope=scope_path,
                    name=attr.name,
                    value=attributes.bind_value(
                        attr, self._compiler, self._stdlib
                    ),
                    direction=attributes.direction_of(attr),
                    type_name=type_name,
                    type_definition=type_def,
                )
            )

    def _bind_constraints(
        self, state_def: syside.StateDefinition, builder: TargetBuilder
    ) -> None:
        """Push asserted constraints through the OPTIONAL builder hook.

        ``bind_constraint`` is not part of the ``TargetBuilder`` protocol:
        builders that do not declare it simply never receive constraints.
        """
        hook = getattr(builder, "bind_constraint", None)
        if hook is None:
            return
        for scope, constraint in constraints.iter_scope_constraints(state_def):
            expression = constraint.result_expression
            if expression is None:
                continue  # a bodiless constraint checks nothing
            scope_path = (
                ""
                if isinstance(scope, syside.StateDefinition)
                else states.state_path(state_def, scope)
            )
            hook(
                ConstraintFact(
                    scope=scope_path,
                    name=constraint.name,
                    expression=expression,
                    is_negated=constraint.is_negated,
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
        for phase, slot in (
            ("entry", container.entry_action),
            ("do", container.do_action),
            ("exit", container.exit_action),
        ):
            bindings.require_assignable_actions(
                slot, f"the `{phase}` action of state {name!r}"
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
        declaration_order: dict[syside.TransitionUsage, int],
        strict_signals: bool,
    ) -> None:
        for trans in transitions.container_transitions(container):
            source = transitions.source_path(state_def, trans)
            bindings.require_assignable_actions(
                trans.effect_action,
                f"the effect of a transition from {source!r}",
            )
            builder.add_transition(
                TransitionFact(
                    source=source,
                    target=transitions.target(state_def, trans, container),
                    trigger=triggers.classify(
                        trans,
                        self._compiler,
                        self._stdlib,
                        strict_signals=strict_signals,
                    ),
                    guard=trans.guard_expression,
                    effect=trans.effect_action,
                    declaration_order=declaration_order.get(trans),
                )
            )
        for substate in states.substates(container):
            if states.substates(substate):
                self._walk_transitions(
                    state_def,
                    substate,
                    builder,
                    declaration_order,
                    strict_signals,
                )
