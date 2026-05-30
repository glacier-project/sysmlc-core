from __future__ import annotations

import syside
from sismic.model import BasicState, CompoundState, Statechart, Transition

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

    ``StateUsage`` -> ``BasicState``;
    ``TransitionUsage`` -> eventless ``Transition``;
    ``StateDefinition`` -> ``CompoundState``;
    each owned scalar ``AttributeUsage`` with an initializer -> one
    assignment line in ``Statechart.preamble``;
    each owned structured ``AttributeUsage`` -> a ``SimpleNamespace``
    binding in ``Statechart.preamble``;
    a ``StateUsage``'s ``entry``/``exit`` action assignments ->
    ``BasicState.on_entry`` / ``BasicState.on_exit`` statements;
    a ``TransitionUsage``'s ``do action`` effect assignments ->
    ``Transition.action`` statements.
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
                ``StateDefinition``, if the definition's entry succession
                cannot be resolved, if a guard, attribute initializer,
                entry/exit assignment, or transition effect assignment
                uses an expression shape the emitter does not support, or
                if a structured attribute has a field with no value to
                bind.
        """
        self._state_def = self._queries.resolve_element_by_qn(
            syside.StateDefinition, self._state_def_qn
        )
        self._statechart = Statechart(
            name=self._state_def.name,
            preamble=self._build_preamble(),
        )
        self._add_root_compound()
        self._add_child_states()
        self._add_transitions()
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

    def _add_root_compound(self) -> None:
        """Add the root ``CompoundState`` representing the state def."""
        initial = self._resolve_initial_state()
        self._statechart.add_state(
            CompoundState(self._state_def.name, initial=initial.name),
            parent=None,
        )

    def _add_child_states(self) -> None:
        """Add a ``BasicState`` for each owned ``StateUsage``.

        A substate's ``entry`` / ``exit`` action assignments become the
        ``on_entry`` / ``on_exit`` Python statements of its ``BasicState``.

        Raises:
            ValueError: If an entry/exit assignment has an unsupported
                right-hand-side expression shape.
        """
        root_name = self._state_def.name
        for state_usage in self._state_def.owned_states.collect():
            self._statechart.add_state(
                BasicState(
                    state_usage.name,
                    on_entry=self._extract_action_statements(
                        state_usage.entry_action
                    ),
                    on_exit=self._extract_action_statements(
                        state_usage.exit_action
                    ),
                ),
                parent=root_name,
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
            action: A substate's ``entry`` or ``exit`` action, or ``None``
                when the substate declares no such action.

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

    def _add_transitions(self) -> None:
        """Add a ``Transition`` for each owned ``TransitionUsage``.

        A transition with no accepter becomes an eventless sismic
        ``Transition``; a transition with an ``accept E via port``
        accepter becomes a sismic ``Transition`` triggered by the
        payload type's simple name. A transition with an ``if expr``
        guard carries the emitted Python source of the guard
        expression in ``Transition.guard``. A transition with a
        ``do action { assign ... }`` effect carries the emitted
        assignment statements in ``Transition.action``.

        Raises:
            ValueError: If a transition has no source or target, if a
                guard contains an expression shape the emitter does not
                support, or if an effect assignment has an unsupported
                right-hand-side expression shape.
        """
        for trans in self._state_def.owned_transitions.collect():
            source = trans.source
            target = trans.target
            if source is None or target is None:
                raise ValueError(
                    f"Transition in state def "
                    f"{self._state_def.qualified_name} is missing "
                    "source or target."
                )
            event = self._extract_event_name(trans)
            guard = self._extract_guard_expression(trans)
            action = self._extract_action_statements(trans.effect_action)
            self._statechart.add_transition(
                Transition(
                    source=source.name,
                    target=target.name,
                    event=event,
                    guard=guard,
                    action=action,
                )
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

    def _resolve_initial_state(self) -> syside.StateUsage:
        """Resolve the initial state targeted by the entry pseudostate.

        Returns:
            The ``StateUsage`` that the entry pseudostate transitions to.

        Raises:
            ValueError: If no entry pseudostate is declared, or if no
                succession from the entry pseudostate to a ``StateUsage``
                can be found.
        """
        entry = self._state_def.entry_action
        if entry is None:
            raise ValueError(
                f"State def {self._state_def.qualified_name} has no "
                "entry pseudostate; expected an "
                "`entry; then <state>;` declaration."
            )

        for feat in self._state_def.owned_features.collect():
            if not isinstance(feat, syside.SuccessionAsUsage):
                continue
            if feat.source is not entry:
                continue
            for target in feat.targets.collect():
                if isinstance(target, syside.StateUsage):
                    return target
        raise ValueError(
            f"No entry succession found for state def "
            f"{self._state_def.qualified_name}; expected an "
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
            ``StateDefinition``, if the definition's entry succession
            cannot be resolved, or if a guard, attribute initializer,
            entry/exit assignment, or transition effect assignment uses
            an expression shape the emitter does not support.
    """
    return StatechartBuilder(model, state_def_qn).build()
