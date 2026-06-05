from __future__ import annotations

import math

import syside
from sismic.model import (
    BasicState,
    CompoundState,
    FinalState,
    OrthogonalState,
    Statechart,
    Transition,
)

from sysml2frost.explore.model_queries import SysideModelQueries
from sysml2frost.sismic.py_emitter import (
    emit_assignment,
    emit_expression,
    emit_send,
)


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


def _is_scalar_quantity(attr: syside.AttributeUsage) -> bool:
    """Whether ``attr``'s type is a scalar quantity value.

    A scalar quantity value (like ``DurationValue``) is a subtype of
    ``Quantities::ScalarQuantityValue``: it carries a unit and reduces to
    one number once that unit is normalized to SI base units, so
    ``2 [min]`` becomes ``120.0``.

    Args:
        attr: The attribute usage to inspect.

    Returns:
        ``True`` when an ``AttributeDefinition`` typing ``attr`` is a
        subtype of ``Quantities::ScalarQuantityValue``.
    """
    for definition in attr.attribute_definitions.collect():
        if isinstance(
            definition, syside.AttributeDefinition
        ) and definition.specializes(("Quantities", "ScalarQuantityValue")):
            return True
    return False


def _evaluate_to_number(
    expr: syside.Expression,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
) -> int | float | None:
    """Evaluate ``expr`` to a number in SI base units, or ``None``.

    Uses the syside compiler's quantity evaluation, so a quantity
    expression collapses to its SI base scalar (``2 [min]`` -> ``120.0``).

    Args:
        expr: The expression to evaluate.
        compiler: The syside compiler used to evaluate the expression.
        stdlib: The stdlib handle the compiler needs for quantity units.

    Returns:
        The evaluated ``int`` or ``float``, or ``None`` when the result is
        not a number (a ``bool`` does not count).
    """
    value, _report = compiler.evaluate(
        expr, stdlib=stdlib, experimental_quantities=True
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _scalar_quantity_value(
    attr: syside.AttributeUsage,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
) -> str | None:
    """Return a scalar quantity's value in SI base units, or ``None``.

    A quantity with a value collapses to one number in SI base units (so
    ``2 [min]`` becomes ``120.0``); one with no value yields ``None``, left
    unseeded for the host to bind at runtime like a scalar with no value.

    Args:
        attr: The scalar quantity attribute to evaluate.
        compiler: The syside compiler used to evaluate the value.
        stdlib: The stdlib handle the compiler needs for quantity units.

    Returns:
        The SI-base scalar as a Python literal (e.g. ``"120.0"``), or
        ``None`` when the attribute carries no value.
    """
    value_expression = attr.feature_value_expression
    if value_expression is None:
        return None
    number = _evaluate_to_number(value_expression, compiler, stdlib)
    assert number is not None
    return repr(float(number))


def _is_composite(attr: syside.AttributeUsage) -> bool:
    """Whether ``attr`` binds to a ``SimpleNamespace`` of named fields.

    True for a structured attribute that is not a scalar quantity - the
    one shape ``_bind_value`` renders as ``SimpleNamespace(...)``, and so
    the one that needs the ``from types import SimpleNamespace`` preamble
    line.

    Args:
        attr: The attribute usage to inspect.

    Returns:
        ``True`` when ``attr`` is structured and not a scalar quantity.
    """
    return bool(_nested_attributes(attr)) and not _is_scalar_quantity(attr)


def _bind_value(
    attr: syside.AttributeUsage,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
) -> str | None:
    """Build the Python expression for an attribute's runtime value.

    The result depends on the attribute's runtime shape:
    - a **scalar** attribute becomes its initializer expression;
    - a **scalar quantity** attribute (``DurationValue`` and the like)
      becomes that value in SI base units (so ``2 [min]`` becomes
      ``120.0``);
    - a **composite** attribute becomes a ``SimpleNamespace(...)``
      built recursively from those fields.

    A scalar or scalar-quantity attribute with no value yields ``None``;
    the caller leaves it unseeded for the host to bind at runtime.

    Args:
        attr: The attribute usage to bind.
        compiler: The syside compiler used to evaluate quantity values.
        stdlib: The stdlib handle the compiler needs for quantity units.

    Returns:
        A Python expression constructing the attribute's runtime value, or
        ``None`` when a scalar or scalar-quantity attribute has no value.

    Raises:
        ValueError: If a composite field has no value to bind, or if a
            value expression is a node kind the emitter does not support.
    """
    nested = _nested_attributes(attr)

    # Scalar: not nested.
    if not nested:
        expr = attr.feature_value_expression
        return emit_expression(expr) if expr is not None else None

    # Scalar quantity.
    if _is_scalar_quantity(attr):
        return _scalar_quantity_value(attr, compiler, stdlib)

    # Composite.
    fields: list[str] = []
    for field in nested:
        assert field.name is not None
        value = _bind_value(field, compiler, stdlib)
        if value is None:
            raise ValueError(
                f"Composite attribute field {field.name!r} has no value "
                "to bind; give it a default."
            )
        fields.append(f"{field.name}={value}")
    return f"SimpleNamespace({', '.join(fields)})"


def _is_done_target(feature_target: syside.Feature) -> bool:
    """Whether a transition target is the standard-library ``done``."""
    return str(feature_target.qualified_name) == "States::StateAction::done"


class StatechartBuilder:
    """Build a sismic Statechart from a SysML state definition.

    The build maps each SysML construct to its sismic counterpart:

    - a ``StateDefinition`` -> the root ``CompoundState``, or an
      ``OrthogonalState`` when it is ``parallel``;
    - a leaf ``StateUsage`` -> a ``BasicState``;
    - a composite ``StateUsage`` (one owning substates) -> a nested
      ``CompoundState``, recursively, or an ``OrthogonalState`` when it
      is ``parallel`` (its substates become concurrent regions);
    - each owned ``AttributeUsage`` with an initializer -> one
      ``Statechart.preamble`` line: the initializer for a scalar, the
      SI-base value for a quantity (``DurationValue`` and the like), a
      ``SimpleNamespace`` binding for a composite;
    - a state's ``entry`` and ``do`` actions (each an ``assign`` and/or
      ``send`` body) -> its ``on_entry`` statements, entry first then do;
      its ``exit`` action -> its ``on_exit`` statements;
    - a ``TransitionUsage`` -> a ``Transition`` whose ``event`` /
      ``guard`` / ``action`` carry any accepter, ``if`` guard, and ``do``
      effect. A signal accepter (``accept Sig via port``) becomes the
      ``event``; a relative time trigger (``accept after <duration>``)
      becomes an ``after(...)`` guard, AND-combined with any ``if`` guard;
      the ``do`` effect becomes the ``action`` (an ``assign`` mutation
      and/or a ``send`` event-raise);
    - a transition target of ``done`` -> a ``FinalState`` synthesized in
      the source's containing scope.

    A ``do`` action runs once at entry (after the entry statements):
    sismic has no activity slot, and SysML starts the do after the entry
    action completes. States are named by their path relative to the
    state definition.
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
        self._done_finals: set[str]
        self._compiler: syside.Compiler
        self._stdlib: syside.Stdlib

    def build(self) -> Statechart:
        """Construct and return the sismic Statechart.

        Returns:
            A sismic ``Statechart`` ready to feed into ``Interpreter``.

        Raises:
            ValueError: If ``state_def_qn`` does not resolve to a
                ``StateDefinition``, if any composite's entry succession
                cannot be resolved, if a transition is missing its source
                or target, if a transition's time trigger is an unsupported
                kind (``at``/``when``) or its ``after`` duration does not
                evaluate to a finite, non-negative number, or if a guard,
                attribute initializer, or entry/exit/effect/do assignment
                uses an expression shape the emitter does not support, if a
                ``do`` action has a body the emitter cannot emit, or if a
                composite attribute has a field with no value to bind.
        """
        self._state_def = self._queries.resolve_element_by_qn(
            syside.StateDefinition, self._state_def_qn
        )
        self._compiler = syside.Compiler()
        self._stdlib = syside.Stdlib(self._model.index)
        root_name = self._state_def.name
        assert root_name is not None
        self._statechart = Statechart(
            name=root_name,
            preamble=self._build_preamble(),
        )
        self._done_finals = set()
        self._build_state_tree(self._state_def, root_name, parent=None)
        self._build_transition_tree(self._state_def)
        self._statechart.validate()
        return self._statechart

    def _build_preamble(self) -> str:
        """Build the sismic preamble that initializes the owned attributes.

        A scalar attribute with an initializer becomes one assignment
        line; a quantity attribute is evaluated to its value in SI base
        units; a composite attribute is bound to a ``SimpleNamespace``.

        Returns:
            Newline-joined preamble lines, or ``""`` when no attribute is
            bound.

        Raises:
            ValueError: If an initializer is an expression shape
                ``emit_expression`` does not support, or if a composite
                attribute has a field with no value to bind.
        """
        lines: list[str] = []
        needs_import = False
        for attr in self._state_def.owned_attributes.collect():
            assert attr.name is not None
            value = _bind_value(attr, self._compiler, self._stdlib)
            if value is None:
                continue
            if _is_composite(attr):
                needs_import = True
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
                cannot be resolved, if an entry/exit/do assignment has an
                unsupported right-hand-side expression shape, or if a
                ``do`` action has a body the emitter cannot emit.
        """
        on_entry = self._on_entry_statements(container)
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
                        on_entry=self._on_entry_statements(substate),
                        on_exit=self._extract_action_statements(
                            substate.exit_action
                        ),
                    ),
                    parent=name,
                )

    def _extract_action_statements(
        self, action: syside.ActionUsage | None
    ) -> str | None:
        """Emit an action's ``assign`` / ``send`` statements as Python.

        Covers both forms: the shorthand, where the action slot is
        itself the ``assign`` or ``send``, and the block form, where they
        are the wrapping action's owned features.

        Args:
            action: An ``entry``/``exit``/``do`` action or a transition
                effect, or ``None`` if none is declared.

        Returns:
            The statements newline-joined in declaration order, or ``None``
            when ``action`` is absent or carries no ``assign``/``send``.

        Raises:
            ValueError: If an ``assign`` or ``send`` uses an expression
                shape the emitter rejects.
        """
        if action is None:
            return None
        # Shorthand `do send new E() ...` / `entry assign x := e;`
        # the action slot is itself the send or assignment
        if isinstance(
            action, (syside.AssignmentActionUsage, syside.SendActionUsage)
        ):
            candidates: list[syside.Feature] = [action]
        else:
            candidates = action.owned_features.collect()
        statements: list[str] = []
        for candidate in candidates:
            if isinstance(candidate, syside.AssignmentActionUsage):
                statements.append(emit_assignment(candidate))
            elif isinstance(candidate, syside.SendActionUsage):
                statements.append(emit_send(candidate))
        return "\n".join(statements) or None

    def _on_entry_statements(
        self, container: syside.StateDefinition | syside.StateUsage
    ) -> str | None:
        """Build a state's ``on_entry`` from its entry and do actions.

        The entry action's statements run first; a ``do`` action starts
        after the entry action completes, so its
        statements follow the entry statements.

        Args:
            container: The root state definition or a state usage whose
                ``on_entry`` to build.

        Returns:
            The entry statements then the do statements, newline-joined in
            that order, or ``None`` when neither is present.

        Raises:
            ValueError: If an entry or do ``assign``/``send`` uses an
                expression shape the emitter rejects, or if the do action
                has a body the emitter cannot emit.
        """
        entry = self._extract_action_statements(container.entry_action)
        do = self._do_action_statements(container)
        parts = [part for part in (entry, do) if part is not None]
        return "\n".join(parts) or None

    def _do_action_statements(
        self, container: syside.StateDefinition | syside.StateUsage
    ) -> str | None:
        """Emit a state's ``do`` action body as run-once ``on_entry`` code.

        Only an ``assign``/``send`` body is emitted (reusing
        ``_extract_action_statements``).
        A do body the emitter cannot turn into a one-shot is rejected:
        containing an ``accept`` or a loop; references other actions.

        Args:
            container: The root state definition or a state usage whose
                ``do`` action to emit.

        Returns:
            The do body's ``assign``/``send`` statements newline-joined, or
            ``None`` when the state has no do action or an empty one.

        Raises:
            ValueError: If the do body contains an action the emitter
                cannot emit (e.g. an ``accept`` or a loop), or if the do
                action references another action (a typed perform or the
                reference-subsetting shorthand).
        """
        do_action = container.do_action
        if do_action is None:
            return None
        # A do that references another action: a typed perform or the
        # `do other;` shorthand cannot be emitted as a one-shot.
        if (
            do_action.owned_typings.collect()
            or do_action.owned_reference_subsetting is not None
        ):
            raise ValueError(
                f"State {container.qualified_name} has a `do` action that "
                "references another action; only inline `assign`/`send` "
                "do-action bodies are supported."
            )
        for action in do_action.nested_actions.collect():
            if not isinstance(
                action,
                (syside.AssignmentActionUsage, syside.SendActionUsage),
            ):
                raise ValueError(
                    f"State {container.qualified_name} has a `do` action "
                    f"whose body contains an unsupported "
                    f"{type(action).__name__}; only `assign` and `send` "
                    "do-action bodies are supported."
                )
        return self._extract_action_statements(do_action)

    def _build_transition_tree(
        self, container: syside.StateDefinition | syside.StateUsage
    ) -> None:
        """Add a sismic ``Transition`` for every transition in the subtree.

        Walks ``container`` and its composite substates, so transitions
        declared inside nested composites are added too. A transition
        with no accepter becomes an eventless
        sismic ``Transition``; an ``accept E via port`` signal accepter
        becomes the sismic ``Transition.event``; an ``accept after
        <duration>`` relative time trigger becomes an ``after(<seconds>)``
        guard; an ``if expr`` guard becomes the emitted guard, AND-combined
        with any time guard; a ``do action { assign ... }`` effect becomes
        the emitted ``Transition.action``. A transition targeting ``done``
        is pointed at a ``FinalState`` synthesized in ``container``'s scope.

        Args:
            container: The root state definition or a composite state
                usage whose transitions to add.

        Raises:
            ValueError: If a transition is missing its source or target,
                if a time trigger is an unsupported kind (``at``/``when``)
                or its ``after`` duration does not evaluate to a finite,
                non-negative number, if a guard contains an expression
                shape the emitter does not support, or if an effect
                assignment has an unsupported right-hand-side expression
                shape.
        """
        for trans in self._container_transitions(container):
            event = self._extract_event_name(trans)
            time_guard = self._extract_time_guard(trans)
            condition_guard = self._extract_guard_expression(trans)
            guard = self._combine_guards(time_guard, condition_guard)
            action = self._extract_action_statements(trans.effect_action)
            self._statechart.add_transition(
                Transition(
                    source=self._source_path(trans),
                    target=self._target_path(trans, container),
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

    def _target_path(
        self,
        trans: syside.TransitionUsage,
        container: syside.StateDefinition | syside.StateUsage,
    ) -> str:
        """Return the sismic name a transition's target resolves to.

        A transition's target is the target end of its succession.
        ``feature_target`` resolves that end uniformly: it returns the
        last segment of a dotted cross-boundary target (e.g.
        ``then running.hot`` -> ``running::hot``), or the target itself
        when it is a direct reference. (``trans.target`` is ``None`` for a
        dotted target, so it is not used here.)
        A ``then done`` is pointed at a ``FinalState`` synthesized
        once per scope under ``container``.

        Args:
            trans: SysML transition usage to inspect.
            container: The container owning ``trans`` (the scope a ``done``
                final state is synthesized under).

        Returns:
            The sismic name of the target state: a ``::``-joined relative
            path, or the name of the synthesized ``done`` final state.

        Raises:
            ValueError: If the transition has no resolved target.
        """
        succession = trans.succession
        targets = succession.targets.collect() if succession is not None else []
        if not targets:
            raise ValueError(
                f"Transition in state def {self._state_def.qualified_name} "
                "has no resolved target."
            )
        feature_target = targets[0].feature_target
        if _is_done_target(feature_target):
            return self._ensure_done_final_state(container)
        return self._state_path(feature_target)

    def _ensure_done_final_state(
        self, container: syside.StateDefinition | syside.StateUsage
    ) -> str:
        """Return the name of ``container``'s ``done`` final state.

        Created once per scope (reused by later ``then done``) and named
        like any substate: ``done`` at the root, ``<scope>::done`` under a
        composite or region.

        Args:
            container: The container owning the ``then done`` transition.

        Returns:
            The sismic name of the synthesized ``done`` final state.
        """
        if isinstance(container, syside.StateDefinition):
            assert container.name is not None
            scope_name = container.name
            final_name = "done"
        else:
            scope_name = self._state_path(container)
            final_name = f"{scope_name}::done"
        if final_name not in self._done_finals:
            self._statechart.add_state(
                FinalState(final_name), parent=scope_name
            )
            self._done_finals.add(final_name)
        return final_name

    def _extract_event_name(self, trans: syside.TransitionUsage) -> str | None:
        """Return the signal accepter's payload type simple name, or ``None``.

        A time or change trigger (``accept after``/``at``/``when``) is not a
        signal event: it carries a ``TriggerInvocationExpression`` payload
        and is handled by the time-guard branch, so this returns ``None``
        for it.

        Args:
            trans: SysML transition usage to inspect.

        Returns:
            The payload type's simple name when the transition has a signal
            ``accept`` accepter; ``None`` for a time/change trigger or an
            eventless transition.
        """
        if self._trigger_invocation(trans) is not None:
            return None
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

    def _trigger_invocation(
        self, trans: syside.TransitionUsage
    ) -> syside.TriggerInvocationExpression | None:
        """Return the transition's trigger-invocation payload, or ``None``.

        A time or change trigger (``accept after``/``at``/``when``) carries
        a ``TriggerInvocationExpression`` as its accepter payload argument;
        a signal accept or an eventless transition does not.

        Args:
            trans: SysML transition usage to inspect.

        Returns:
            The ``TriggerInvocationExpression`` when the accepter is a
            time/change trigger; ``None`` for a signal accept or an
            eventless transition.
        """
        triggers = list(trans.trigger_actions)
        if not triggers:
            return None
        payload = triggers[0].payload_argument
        if isinstance(payload, syside.TriggerInvocationExpression):
            return payload
        return None

    def _extract_time_guard(self, trans: syside.TransitionUsage) -> str | None:
        """Return the ``after(...)`` guard for a relative time trigger.

        Only the relative form (``accept after <duration>``) is supported,
        mapped to sismic's state-local ``after`` guard. An attribute
        reference, bare (``pickDuration``) or chained (``cfg.delay``), is
        kept live by name (its attribute is seeded in the preamble).

        Args:
            trans: SysML transition usage to inspect.

        Returns:
            ``"after(<name>)"`` for a bare or chained attribute-reference
            duration, ``"after(<seconds>)"`` for a literal duration, or
            ``None`` when the transition has no trigger invocation (a signal
            accept or an eventless transition).

        Raises:
            ValueError: If the trigger is an absolute ``at`` or change
                ``when`` trigger, or if a literal or computed ``after``
                duration does not evaluate to a finite, non-negative number.
        """
        invocation = self._trigger_invocation(trans)
        if invocation is None:
            return None
        if invocation.kind is not syside.TriggerKind.After:
            raise ValueError(
                f"Transition in state def {self._state_def.qualified_name} "
                f"uses an unsupported {invocation.kind!s} trigger; only the "
                "relative `accept after <duration>` time trigger is "
                "supported."
            )
        duration = invocation.arguments.collect()[0]
        if isinstance(
            duration,
            (
                syside.FeatureReferenceExpression,
                syside.FeatureChainExpression,
            ),
        ):
            return f"after({emit_expression(duration)})"
        seconds = self._evaluate_duration_seconds(invocation)
        return f"after({seconds!r})"

    def _evaluate_duration_seconds(
        self, invocation: syside.TriggerInvocationExpression
    ) -> float:
        """Evaluate a relative time trigger's duration to SI base seconds.

        Uses the syside compiler's quantity evaluation.

        Args:
            invocation: The ``after`` trigger invocation to evaluate.

        Returns:
            The duration in SI base seconds.

        Raises:
            ValueError: If the duration does not evaluate to a finite,
                non-negative number (for example a negative or non-finite
                literal duration).
        """
        number = _evaluate_to_number(invocation, self._compiler, self._stdlib)
        if number is None:
            raise ValueError(
                f"Transition in state def {self._state_def.qualified_name} "
                "has an `accept after` duration that does not evaluate to a "
                "number; the duration must be a DurationValue with a "
                "resolvable value."
            )
        seconds = float(number)
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError(
                f"Transition in state def {self._state_def.qualified_name} "
                f"has an `accept after` duration that evaluates to {seconds!r}"
                "; the duration must be a finite, non-negative DurationValue."
            )
        return seconds

    def _combine_guards(
        self, time_guard: str | None, condition_guard: str | None
    ) -> str | None:
        """Combine a time guard and an ``if`` guard into one guard string.

        A transition may carry both a relative time trigger and an ``if``
        guard; SysML fires it only once the timer has elapsed and the guard
        holds, so the two are ANDed.

        Args:
            time_guard: The ``after(<seconds>)`` guard, or ``None``.
            condition_guard: The emitted ``if`` guard, or ``None``.

        Returns:
            The combined guard string, the single non-``None`` guard, or
            ``None`` when neither is present.
        """
        if time_guard is not None and condition_guard is not None:
            return f"{time_guard} and ({condition_guard})"
        if time_guard is not None:
            return time_guard
        return condition_guard

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
            target, if a transition's time trigger is an unsupported kind
            (``at``/``when``) or its ``after`` duration does not evaluate to
            a finite, non-negative number, if a guard, attribute
            initializer, or entry/exit/effect/do assignment uses an
            expression shape the emitter does not support, or if a ``do``
            action has a body the emitter cannot emit.
    """
    return StatechartBuilder(model, state_def_qn).build()
