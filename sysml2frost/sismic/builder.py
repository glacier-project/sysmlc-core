from __future__ import annotations

import syside
from sismic.model import (
    BasicState,
    CompoundState,
    OrthogonalState,
    Statechart,
    Transition,
)

from sysml2frost.explore.model_queries import SysideModelQueries
from sysml2frost.sismic.py_emitter import emit_assignment, emit_expression


def _nested_attributes(
    attr: syside.AttributeUsage,
) -> list[syside.AttributeUsage]:
    """Return the attributes of ``attr``'s structured definition.

    An attribute is structured when its type resolves to an
    ``AttributeDefinition`` that owns attributes; it is scalar
    when its type resolves to a primitive ``DataType``.

    Args:
        attr: The attribute usage to inspect.

    Returns:
        The owned attributes of every ``AttributeDefinition`` typing
        ``attr``, or an empty list when ``attr`` is scalar.
    """
    nested: list[syside.AttributeUsage] = []
    for definition in attr.attribute_definitions.collect():
        if isinstance(definition, syside.AttributeDefinition):
            nested.extend(definition.owned_attributes.collect())
    return nested


def _bind_value(attr: syside.AttributeUsage) -> str | None:
    """Build the Python expression for an attribute's runtime value.

    A structured attribute becomes a ``SimpleNamespace(...)`` built
    recursively from its fields; a scalar attribute becomes its
    initializer expression.

    Args:
        attr: The attribute usage to bind.

    Returns:
        A Python expression constructing the attribute's runtime value
        (e.g. ``0.5`` or ``SimpleNamespace(x=0.5)``), or ``None`` when a
        scalar attribute has no initializer.

    Raises:
        ValueError: If a structured field has no value to bind, or if a
            value expression is a node kind the emitter does not support.
    """
    nested = _nested_attributes(attr)
    if not nested:
        value_expression = attr.feature_value_expression
        if value_expression is None:
            return None
        return emit_expression(value_expression)
    fields: list[str] = []
    for field in nested:
        assert field.name is not None
        value = _bind_value(field)
        if value is None:
            raise ValueError(
                f"Structured attribute field {field.name!r} has no value "
                "to bind; give it a default."
            )
        fields.append(f"{field.name}={value}")
    return f"SimpleNamespace({', '.join(fields)})"


class StatechartBuilder:
    """Build a sismic Statechart from a SysML state definition.

    ``StateDefinition`` -> the root ``CompoundState``, or an
    ``OrthogonalState`` when the state def is ``parallel``;
    a leaf ``StateUsage`` -> ``BasicState``;
    a composite ``StateUsage`` (one that owns substates) -> a nested
    ``CompoundState``, recursively, or an ``OrthogonalState`` when the
    substate is ``parallel`` (its substates become concurrent regions);
    each owned scalar ``AttributeUsage`` with an initializer -> one
    assignment line in ``Statechart.preamble``;
    each owned structured ``AttributeUsage`` -> a ``SimpleNamespace``
    binding in ``Statechart.preamble``;
    a state's ``entry``/``exit`` action assignments -> its
    ``on_entry`` / ``on_exit`` statements;
    a ``TransitionUsage`` -> a ``Transition`` whose ``event``/``guard``/
    ``action`` carry any accepter / ``if`` guard / ``do`` effect.

    States are named by their path relative to the state definition.
    """

    def __init__(self, model: syside.Model, state_def_qn: str) -> None:
        """Initialize the builder.

        Args:
            model: Loaded syside model containing the SysML state def.
            state_def_qn: Qualified name of the SysML ``state def`` to
                translate.
        """
        self._model = model
        self._state_def_qn = state_def_qn
        self._queries = SysideModelQueries(model)
        self._state_def: syside.StateDefinition
        self._statechart: Statechart

    def build(self) -> Statechart:
        """Construct and return the sismic Statechart.

        Returns:
            A sismic ``Statechart`` ready to feed into ``Interpreter``.

        Raises:
            ValueError: If ``state_def_qn`` does not resolve to a
                ``StateDefinition``, if any composite's entry succession
                cannot be resolved, if a transition is missing its source
                or target, or if a guard, attribute initializer, or
                entry/exit/effect assignment uses an expression shape the
                emitter does not support, or if a structured attribute has
                a field with no value to bind.
        """
        self._state_def = self._queries.resolve_element_by_qn(
            syside.StateDefinition, self._state_def_qn
        )
        root_name = self._state_def.name
        assert root_name is not None
        self._statechart = Statechart(
            name=root_name,
            preamble=self._build_preamble(),
        )
        self._build_state_tree(self._state_def, root_name, parent=None)
        self._build_transition_tree(self._state_def)
        self._statechart.validate()
        return self._statechart

    def _build_preamble(self) -> str:
        """Build the sismic preamble that initializes the owned attributes.

        A scalar attribute with an initializer becomes one assignment
        line. A structured attribute is bound to a ``SimpleNamespace``.

        Returns:
            Newline-joined preamble lines, or ``""`` when no attribute is
            bound.

        Raises:
            ValueError: If an initializer is an expression shape
                ``emit_expression`` does not support, or if a structured
                attribute has a field with no value to bind.
        """
        lines: list[str] = []
        needs_import = False
        for attr in self._state_def.owned_attributes.collect():
            assert attr.name is not None
            if _nested_attributes(attr):
                needs_import = True
            value = _bind_value(attr)
            if value is not None:
                lines.append(f"{attr.name} = {value}")
        if needs_import:
            lines.insert(0, "from types import SimpleNamespace")
        return "\n".join(lines)

    def _state_path(self, state: syside.Feature) -> str:
        """Return a state's sismic name: its path relative to the state def.

        The path is the state's qualified name with the state
        definition's own qualified name stripped off.

        Args:
            state: The state to name. Only its qualified name is read.
                The type is the broad ``Feature`` (not ``StateUsage``) so
                the same helper can also name a transition's source and
                target, which syside returns typed as actions, not states.

        Returns:
            The ``::``-joined relative path of ``state``.
        """
        prefix = f"{self._state_def.qualified_name}::"
        return str(state.qualified_name).removeprefix(prefix)

    def _substates(
        self, container: syside.StateDefinition | syside.StateUsage
    ) -> list[syside.StateUsage]:
        """Return the immediate substates of a state container.

        A ``StateDefinition`` exposes them as ``owned_states``; a
        composite ``StateUsage`` exposes them as ``nested_states``.

        Args:
            container: The root state definition or a composite state
                usage to read substates from.

        Returns:
            The container's immediate substate usages, in declaration
            order; empty when ``container`` is a leaf state.
        """
        if isinstance(container, syside.StateDefinition):
            return container.owned_states.collect()
        return container.nested_states.collect()

    def _container_transitions(
        self, container: syside.StateDefinition | syside.StateUsage
    ) -> list[syside.TransitionUsage]:
        """Return the transitions owned directly by a state container.

        A ``StateDefinition`` exposes them as ``owned_transitions``; a
        composite ``StateUsage`` exposes them as ``nested_transitions``.

        Args:
            container: The root state definition or a composite state
                usage to read transitions from.

        Returns:
            The container's own transition usages, in declaration order.
        """
        if isinstance(container, syside.StateDefinition):
            return container.owned_transitions.collect()
        return container.nested_transitions.collect()

    def _build_state_tree(
        self,
        container: syside.StateDefinition | syside.StateUsage,
        name: str,
        parent: str | None,
    ) -> None:
        """Add ``container`` as a compound/orthogonal state and recurse.

        A non-parallel container becomes a ``CompoundState`` whose
        ``initial`` is its entry-selected substate; a ``parallel``
        container becomes an ``OrthogonalState`` whose substates are
        concurrent regions and which has no single initial. Either way
        its ``on_entry`` / ``on_exit`` carry any entry/exit assignments,
        and each substate is added as a nested compound/orthogonal state
        or a ``BasicState``.

        Args:
            container: The root state definition or a composite state
                usage to build.
            name: The sismic name for ``container``.
            parent: The name of the parent state, or ``None`` for the
                root.

        Raises:
            ValueError: If a non-parallel container's entry succession
                cannot be resolved, or if an entry/exit assignment has an
                unsupported right-hand-side expression shape.
        """
        on_entry = self._extract_action_statements(container.entry_action)
        on_exit = self._extract_action_statements(container.exit_action)
        state: CompoundState | OrthogonalState
        if container.is_parallel:
            state = OrthogonalState(name, on_entry=on_entry, on_exit=on_exit)
        else:
            initial = self._resolve_initial(container)
            state = CompoundState(
                name,
                initial=self._state_path(initial),
                on_entry=on_entry,
                on_exit=on_exit,
            )
        self._statechart.add_state(state, parent=parent)
        for substate in self._substates(container):
            substate_name = self._state_path(substate)
            if self._substates(substate):
                self._build_state_tree(substate, substate_name, parent=name)
            else:
                self._statechart.add_state(
                    BasicState(
                        substate_name,
                        on_entry=self._extract_action_statements(
                            substate.entry_action
                        ),
                        on_exit=self._extract_action_statements(
                            substate.exit_action
                        ),
                    ),
                    parent=name,
                )

    def _extract_action_statements(
        self, action: syside.ActionUsage | None
    ) -> str | None:
        """Emit the assignment statements of an entry/exit action.

        Handles both surface forms the convention allows: the block form
        ``entry action n { assign ...; }``, where the assignments are
        owned features of a wrapping action, and the shorthand form
        ``entry assign x := e;``, where the action slot is itself the
        assignment.

        Args:
            action: A state's ``entry`` or ``exit`` action, or ``None``
                when the state declares no such action.

        Returns:
            The newline-joined Python assignment statements for the
            action's assignments in declaration order, or ``None`` when
            the action is absent or carries no assignment.

        Raises:
            ValueError: If an assignment has an unsupported right-hand-side
                expression shape.
        """
        if action is None:
            return None
        # Shorthand `entry/exit assign x := e;`
        if isinstance(action, syside.AssignmentActionUsage):
            candidates: list[syside.Feature] = [action]
        else:
            candidates = action.owned_features.collect()
        statements = [
            emit_assignment(a)
            for a in candidates
            if isinstance(a, syside.AssignmentActionUsage)
        ]
        return "\n".join(statements) or None

    def _build_transition_tree(
        self, container: syside.StateDefinition | syside.StateUsage
    ) -> None:
        """Add a sismic ``Transition`` for every transition in the subtree.

        Walks ``container`` and its composite substates, so transitions
        declared inside nested composites are added too. A transition
        with no accepter becomes an eventless
        sismic ``Transition``; an ``accept E via port`` accepter becomes
        the sismic ``Transition.event``; an ``if expr`` guard becomes the
        emitted ``Transition.guard``; a ``do action { assign ... }``
        effect becomes the emitted ``Transition.action``.

        Args:
            container: The root state definition or a composite state
                usage whose transitions to add.

        Raises:
            ValueError: If a transition is missing its source or target,
                if a guard contains an expression shape the emitter does
                not support, or if an effect assignment has an unsupported
                right-hand-side expression shape.
        """
        for trans in self._container_transitions(container):
            event = self._extract_event_name(trans)
            guard = self._extract_guard_expression(trans)
            action = self._extract_action_statements(trans.effect_action)
            self._statechart.add_transition(
                Transition(
                    source=self._source_path(trans),
                    target=self._target_path(trans),
                    event=event,
                    guard=guard,
                    action=action,
                )
            )
        for substate in self._substates(container):
            if self._substates(substate):
                self._build_transition_tree(substate)

    def _source_path(self, trans: syside.TransitionUsage) -> str:
        """Return the relative path of a transition's source state.

        Args:
            trans: SysML transition usage to inspect.

        Returns:
            The ``::``-joined relative path of the source state.

        Raises:
            ValueError: If the transition has no resolved source.
        """
        source = trans.source
        if source is None:
            raise ValueError(
                f"Transition in state def {self._state_def.qualified_name} "
                "has no resolved source."
            )
        return self._state_path(source)

    def _target_path(self, trans: syside.TransitionUsage) -> str:
        """Return the relative path of a transition's target state.

        A transition's target is the target end of its succession.
        ``feature_target`` resolves that end uniformly: it returns the
        last segment of a dotted cross-boundary target (e.g.
        ``then running.hot`` -> ``running::hot``), or the target itself
        when it is a direct reference. (``trans.target`` is ``None`` for a
        dotted target, so it is not used here.)

        Args:
            trans: SysML transition usage to inspect.

        Returns:
            The ``::``-joined relative path of the target state.

        Raises:
            ValueError: If the transition has no resolved target.
        """
        succession = trans.succession
        targets = succession.targets.collect() if succession is not None else []
        if targets:
            return self._state_path(targets[0].feature_target)
        raise ValueError(
            f"Transition in state def {self._state_def.qualified_name} "
            "has no resolved target."
        )

    def _extract_event_name(self, trans: syside.TransitionUsage) -> str | None:
        """Return the accepter payload type's simple name, or ``None``.

        Args:
            trans: SysML transition usage to inspect.

        Returns:
            The payload type's simple name when the transition has an
            ``accept`` accepter; ``None`` for an eventless transition.
        """
        triggers = list(trans.trigger_actions)
        if not triggers:
            return None
        param = triggers[0].payload_parameter
        if param is None:
            return None
        typings = param.owned_typings.collect()
        if not typings:
            return None
        general = typings[0].general
        if general is None:
            return None
        return general.name

    def _extract_guard_expression(
        self, trans: syside.TransitionUsage
    ) -> str | None:
        """Return the Python source for an ``if expr`` guard, or ``None``.

        Args:
            trans: SysML transition usage to inspect.

        Returns:
            The emitted Python expression string when the transition has
            an ``if`` clause; ``None`` for a guardless transition.

        Raises:
            ValueError: If the guard expression contains a node kind
                the sismic expression emitter does not support.
        """
        expr = trans.guard_expression
        if expr is None:
            return None
        return emit_expression(expr)

    def _resolve_initial(
        self, container: syside.StateDefinition | syside.StateUsage
    ) -> syside.StateUsage:
        """Resolve the initial substate selected by a container's entry.

        Args:
            container: The root state definition or a composite state
                usage whose initial substate to resolve.

        Returns:
            The ``StateUsage`` the entry pseudostate transitions to.

        Raises:
            ValueError: If no entry pseudostate is declared, or if no
                succession from the entry pseudostate to a ``StateUsage``
                can be found.
        """
        entry = container.entry_action
        if entry is None:
            raise ValueError(
                f"State {container.qualified_name} has no entry "
                "pseudostate; expected an `entry; then <state>;` "
                "declaration."
            )

        for feat in container.owned_features.collect():
            if not isinstance(feat, syside.SuccessionAsUsage):
                continue
            if feat.source is not entry:
                continue
            for target in feat.targets.collect():
                if isinstance(target, syside.StateUsage):
                    return target
        raise ValueError(
            f"No entry succession found for state "
            f"{container.qualified_name}; expected an "
            f"`entry; then <state>;` declaration."
        )


def build_statechart(model: syside.Model, state_def_qn: str) -> Statechart:
    """Build a sismic Statechart from a SysML state definition.

    Args:
        model: Loaded syside model containing the SysML state def.
        state_def_qn: Qualified name of the SysML ``state def`` to
            translate.

    Returns:
        A sismic ``Statechart`` ready to feed into ``Interpreter``.

    Raises:
        ValueError: If ``state_def_qn`` does not resolve to a
            ``StateDefinition``, if any composite's entry succession
            cannot be resolved, if a transition is missing its source or
            target, or if a guard, attribute initializer, or
            entry/exit/effect assignment uses an expression shape the
            emitter does not support.
    """
    return StatechartBuilder(model, state_def_qn).build()
