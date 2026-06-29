from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sismic.model import (
    BasicState,
    CompoundState,
    FinalState,
    OrthogonalState,
    Statechart,
    Transition,
)

from sysmlc.backends.quake.codegen import QuakeRenderNeeds, SismicCodeGen
from sysmlc.codegen.python import join_statements
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions, transitions
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import (
    AfterTrigger,
    AttributeBinding,
    AttributeValue,
    AtTrigger,
    CompletionTarget,
    CompositeValue,
    ConstraintFact,
    SignalTrigger,
    StateFact,
    StateKind,
    TransitionFact,
    Trigger,
    WhenTrigger,
)

if TYPE_CHECKING:
    import syside


@dataclass(frozen=True)
class _TimeTriggerPlan:
    """What an ``accept after`` or ``accept at`` transition references.

    Attributes:
        event_name: The synthetic internal event carrying the deadline.
        counter: Context name of the source state's activation counter.
    """

    event_name: str
    counter: str


@dataclass(frozen=True)
class _ChangeTriggerPlan:
    """How an ``accept when`` transition pair is emitted.

    Attributes:
        flag: Context name of the armed-observation flag.
        condition: The monitored boolean condition, already rendered as
            source text.
        consumer_priority: A distinct negative priority for the consumer
            transition (below the real transition's sismic default), or
            None when no ``if`` guard can reject the occurrence and no
            consumer is emitted.
    """

    flag: str
    condition: str
    consumer_priority: int | None


class SismicBuilder:
    """Assemble a sismic ``Statechart`` from neutral state-machine facts.

    Implements the ``TargetBuilder`` protocol. This is where every
    sismic-specific representational choice lives:
    - the flat preamble, with its name-collision policy;
    - the ``do`` -> run-once ``on_entry`` fusion;
    - the ``then done`` -> ``FinalState`` synthesis;
    - the one-shot delayed-event encoding of ``accept after`` and
      ``accept at``: a
      per-activation counter bumped ``on entry``, a ``send('_tick_...',
      n=..., delay=...)`` arming call, and an event-triggered transition
      whose guard checks ``event.n``. Absolute-time triggers additionally
      use ``_d_*`` arming-delta variables and send only for non-past
      instants;
    - the armed-flag encoding of ``accept when``: a ``_w_*`` flag re-armed
      ``on entry``, an eventless transition (at sismic's default priority)
      guarded by the flag and the condition, and, with an ``if`` guard, a
      negative-priority internal consumer transition that disarms the flag
      when the occurrence is rejected;
    - the named-payload aliasing: a signal accepter that binds its payload
      (``accept reading : Measurement``) renders references to that binding
      against sismic's runtime ``event``, so ``reading.value`` becomes
      ``event.value``;
    - the capability rejections: non-inline ``do`` bodies, unstable
      self-loops, and model names starting with ``_``.

    Sismic's ``Statechart.preamble`` is read-only after construction, so facts
    are buffered and the whole statechart is built in :meth:`result`.
    """

    def __init__(
        self,
        name: str,
        *,
        external: tuple[str, frozenset[str]] | None = None,
    ) -> None:
        """Initialize the builder.

        Args:
            name: The sismic statechart name (the state definition's name).
            external: Optional ``(module_stem, function_names)`` pair for
                external calc-def backing.
        """
        self._name = name
        self._needs = QuakeRenderNeeds()
        if external is not None:
            self._needs.register_external(module=external[0], names=external[1])
        self._codegen = SismicCodeGen(needs=self._needs)
        self._preamble: list[str] = []
        self._seen_attrs: dict[str, str] = {}
        self._constraints: list[ConstraintFact] = []
        self._state_facts: list[StateFact] = []
        self._transition_facts: list[TransitionFact] = []
        self._done_finals: set[str] = set()
        self._planned_triggers: dict[
            int, _TimeTriggerPlan | _ChangeTriggerPlan
        ] = {}
        self._arming_by_source: dict[str, list[str]] = {}

    def bind_attribute(self, binding: AttributeBinding) -> None:
        """Seed an attribute into sismic's flat preamble namespace.

        Raises:
            UnsupportedConstructError: If two attributes in different scopes
                share a simple name (sismic's context is flat), or if an
                attribute name starts with the reserved ``_`` prefix.
        """
        if binding.name.startswith("_"):
            raise UnsupportedConstructError(
                f"attribute {binding.name!r} starts with an underscore; "
                "that namespace is reserved for the generated machinery. "
            )
        if binding.name in self._seen_attrs:
            first = self._seen_attrs[binding.name]
            raise UnsupportedConstructError(
                f"attribute {binding.name!r} is declared in two scopes "
                f"({first!r} and {binding.scope!r}). Sismic's flat namespace "
                "cannot represent both. Rename one."
            )
        self._seen_attrs[binding.name] = binding.scope
        rendered = self._render_value(binding.value)
        if rendered is None:
            return
        self._preamble.append(f"{binding.name} = {rendered}")

    def bind_constraint(self, fact: ConstraintFact) -> None:
        """Buffer an asserted constraint for sismic invariant emission."""
        self._constraints.append(fact)

    def add_state(self, state: StateFact) -> None:
        """Buffer a state fact (emitted in :meth:`result`)."""
        self._state_facts.append(state)

    def add_transition(self, transition: TransitionFact) -> None:
        """Buffer a transition fact (emitted in :meth:`result`)."""
        self._transition_facts.append(transition)

    def result(self) -> Statechart:
        """Build, validate, and return the assembled sismic statechart."""
        self._plan_triggers()
        imports = self._preamble_import_lines()
        if imports:
            self._preamble[0:0] = imports
        statechart = Statechart(
            name=self._name, preamble="\n".join(self._preamble)
        )
        for state in self._state_facts:
            self._emit_state(statechart, state)
        self._emit_constraints(statechart)
        for index, transition in enumerate(self._transition_facts):
            self._emit_transition(
                statechart, transition, self._planned_triggers.get(index)
            )
        statechart.validate()
        return statechart

    def _preamble_import_lines(self) -> list[str]:
        """Return import lines before seeded context variables."""
        lines = [
            "from math import cos, sin, tan",
            "from types import SimpleNamespace",
        ]
        lines.extend(self._needs.external_import_lines())
        return lines

    def _plan_triggers(self) -> None:
        """Plan the emitted machinery for time and change triggers.

        Walks the buffered transitions in declaration order, delegating
        per trigger kind.
        """
        per_source_time: dict[str, int] = {}
        per_source_when: dict[str, int] = {}
        next_consumer: dict[str, int] = {}
        for index, transition in enumerate(self._transition_facts):
            trigger = transition.trigger
            if trigger is None:
                continue
            if isinstance(trigger, (AfterTrigger, AtTrigger)):
                self._plan_time(
                    index, trigger, transition.source, per_source_time
                )
            elif isinstance(trigger, WhenTrigger):
                self._plan_when(
                    index, trigger, transition, per_source_when, next_consumer
                )

    def _plan_time(
        self,
        index: int,
        trigger: AfterTrigger | AtTrigger,
        source: str,
        per_source_ordinal: dict[str, int],
    ) -> None:
        """Plan the delayed-event machinery for one time trigger.

        The counter invalidates stale ticks: sismic never cancels a
        delayed event when its state exits, so a tick armed by an earlier
        activation must match nothing when it is delivered.
        """
        ordinal = per_source_ordinal.get(source, 0) + 1
        per_source_ordinal[source] = ordinal
        ident = source.replace("::", "__")
        counter = f"_n_{ident}"
        delay = (
            self._render_value(trigger.duration)
            if isinstance(trigger, AfterTrigger)
            else self._render_value(trigger.instant)
        )
        assert delay is not None
        event_name = f"_tick_{ident}_t{ordinal}"
        self._planned_triggers[index] = _TimeTriggerPlan(
            event_name=event_name, counter=counter
        )
        if ordinal == 1:
            self._preamble.append(f"{counter} = 0")
            self._arming_by_source.setdefault(source, []).append(
                f"{counter} = {counter} + 1"
            )
        if isinstance(trigger, AfterTrigger):
            self._arming_by_source[source].append(
                f"send('{event_name}', n={counter}, delay={delay})"
            )
            return
        delta = f"_d_{ident}_t{ordinal}"
        self._arming_by_source[source].extend(
            [
                f"{delta} = ({delay}) - time",
                f"if {delta} >= 0:",
                f"    send('{event_name}', n={counter}, delay={delta})",
            ]
        )

    def _plan_when(
        self,
        index: int,
        trigger: WhenTrigger,
        transition: TransitionFact,
        per_source_ordinal: dict[str, int],
        next_consumer: dict[str, int],
    ) -> None:
        """Plan the armed-flag machinery for one ``accept when``.

        The real transition keeps sismic's default priority;
        only the consumer use a distinct negative priority.
        """
        source = transition.source
        ordinal = per_source_ordinal.get(source, 0) + 1
        per_source_ordinal[source] = ordinal
        ident = source.replace("::", "__")
        flag = f"_w_{ident}_t{ordinal}"
        consumer_priority = None
        if transition.guard is not None:
            # Distinct negatives per source, from -2 down: below the real's
            # default 0, and skipping -1, which sismic serializes as the
            # named priority `low`.
            consumer_priority = next_consumer.get(source, -2)
            next_consumer[source] = consumer_priority - 1
        self._planned_triggers[index] = _ChangeTriggerPlan(
            flag=flag,
            condition=self._codegen.render_expression(trigger.condition),
            consumer_priority=consumer_priority,
        )
        self._preamble.append(f"{flag} = False")
        self._arming_by_source.setdefault(source, []).append(f"{flag} = True")

    def _render_value(self, value: AttributeValue) -> str | None:
        if value is None:
            return None
        if isinstance(value, CompositeValue):
            fields = ", ".join(
                f"{name}={self._render_value(field)}"
                for name, field in value.fields
            )
            return f"SimpleNamespace({fields})"
        if isinstance(value, float):
            return repr(value)
        return self._codegen.render_expression(value)

    def _emit_state(self, statechart: Statechart, state: StateFact) -> None:
        on_entry = self._on_entry(state)
        on_exit = self._statements(state.exit_action)
        sismic_state: BasicState | CompoundState | OrthogonalState
        if state.kind is StateKind.LEAF:
            sismic_state = BasicState(
                state.name, on_entry=on_entry, on_exit=on_exit
            )
        elif state.kind is StateKind.PARALLEL:
            sismic_state = OrthogonalState(
                state.name, on_entry=on_entry, on_exit=on_exit
            )
        elif state.kind is StateKind.COMPOSITE:
            sismic_state = CompoundState(
                state.name,
                initial=state.initial_substate,
                on_entry=on_entry,
                on_exit=on_exit,
            )
        else:
            raise UnsupportedConstructError(
                f"cannot emit a sismic state of kind {state.kind.name}"
            )
        statechart.add_state(sismic_state, parent=state.parent)

    def _on_entry(self, state: StateFact) -> str | None:
        entry = self._statements(state.entry_action)
        do = None
        if state.do_action is not None:
            actions.require_inline_one_shot(state.do_action)
            do = self._statements(state.do_action)
        # Armed last: durations must see the values entry/do just assigned.
        arming = "\n".join(self._arming_by_source.get(state.name, []))
        parts = [part for part in (entry, do, arming) if part]
        return "\n".join(parts) or None

    def _statements(
        self,
        action: syside.ActionUsage | None,
        codegen: SismicCodeGen | None = None,
    ) -> str | None:
        generator = self._codegen if codegen is None else codegen
        rendered = join_statements(
            [
                generator.render_action(candidate)
                for candidate in actions.inline_actions(action)
            ]
        )
        return rendered or None

    def _emit_constraints(self, statechart: Statechart) -> None:
        """Attach asserted constraints to their owning sismic states."""
        for fact in self._constraints:
            state_name = self._name if fact.scope == "" else fact.scope
            statechart.state_for(state_name).invariants.append(
                self._codegen.render_expression(fact.expression)
            )

    def _emit_transition(
        self,
        statechart: Statechart,
        transition: TransitionFact,
        plan: _TimeTriggerPlan | _ChangeTriggerPlan | None,
    ) -> None:
        if transitions.self_loop_is_unstable(transition):
            raise UnsupportedConstructError(
                "A self-loop transition would never stabilize (no event, "
                "timer, or effect to break the loop)."
            )
        target = (
            self._final_state(statechart, transition.target.scope)
            if isinstance(transition.target, CompletionTarget)
            else transition.target
        )
        if isinstance(plan, _ChangeTriggerPlan):
            self._emit_change_transitions(statechart, transition, plan, target)
            return
        codegen = self._transition_codegen(transition)
        statechart.add_transition(
            Transition(
                source=transition.source,
                target=target,
                event=self._event(transition.trigger, plan),
                guard=self._guard(transition, plan, codegen),
                action=self._statements(transition.effect, codegen),
            )
        )

    def _emit_change_transitions(
        self,
        statechart: Statechart,
        transition: TransitionFact,
        plan: _ChangeTriggerPlan,
        target: str,
    ) -> None:
        """Emit the transition pair realizing one ``accept when``.

        The consumer disarms in its action, not in a guard side effect,
        so an aborted macro step consumes nothing; having no target, it
        consumes without re-running ``on entry`` (which would re-arm).
        """
        delivery = f"{plan.flag} and ({plan.condition})"
        codegen = self._transition_codegen(transition)
        guard = delivery
        if transition.guard is not None:
            condition = codegen.render_expression(transition.guard)
            guard = f"{delivery} and ({condition})"
        statechart.add_transition(
            Transition(
                source=transition.source,
                target=target,
                guard=guard,
                action=self._statements(transition.effect, codegen),
            )
        )
        if plan.consumer_priority is not None:
            statechart.add_transition(
                Transition(
                    source=transition.source,
                    guard=delivery,
                    action=f"{plan.flag} = False",
                    priority=plan.consumer_priority,
                )
            )

    def _event(
        self, trigger: Trigger | None, plan: _TimeTriggerPlan | None
    ) -> str | None:
        """Return the transition's sismic event name, or None.

        A signal accepter triggers on its payload type's name; a time
        trigger triggers on its planned ``_tick_*`` event.

        Raises:
            UnsupportedConstructError: If a signal name starts with the
                reserved ``_`` prefix.
        """
        if trigger is None:
            return None
        if isinstance(trigger, (AfterTrigger, AtTrigger)):
            assert plan is not None
            return plan.event_name
        assert isinstance(trigger, SignalTrigger)
        name = trigger.signal_name
        if name.startswith("_"):
            raise UnsupportedConstructError(
                f"signal {name!r} starts with an underscore; that "
                "namespace is reserved for the generated machinery. "
            )
        return name

    def _guard(
        self,
        transition: TransitionFact,
        plan: _TimeTriggerPlan | None,
        codegen: SismicCodeGen,
    ) -> str | None:
        """Compose the transition's sismic guard string, or None.

        Conjoining the ``if`` condition with the ``event.n`` check is what
        makes a time trigger plus guard faithful: a deadline delivered
        while the condition is false is consumed, with no late firing.
        """
        condition = (
            codegen.render_expression(transition.guard)
            if transition.guard is not None
            else None
        )
        if plan is None:
            return condition
        deadline = f"event.n == {plan.counter}"
        if condition is None:
            return deadline
        return f"{deadline} and ({condition})"

    def _transition_codegen(self, transition: TransitionFact) -> SismicCodeGen:
        """Return a code generator scoped to ``transition``."""
        trigger = transition.trigger
        if (
            not isinstance(trigger, SignalTrigger)
            or trigger.payload_feature is None
        ):
            return self._codegen
        return SismicCodeGen(
            needs=self._needs,
            feature_aliases=((trigger.payload_feature, "event"),),
        )

    def _final_state(self, statechart: Statechart, scope: str) -> str:
        scope_name = scope or self._name
        final_name = "done" if scope == "" else f"{scope}::done"
        if final_name not in self._done_finals:
            statechart.add_state(FinalState(final_name), parent=scope_name)
            self._done_finals.add(final_name)
        return final_name


def build_statechart(
    model: syside.Model,
    state_def_qn: str,
    *,
    external: tuple[str, frozenset[str]] | None = None,
) -> Statechart:
    """Build a sismic Statechart from a SysML state definition.

    Wires the generic :class:`StateMachineDriver` to a :class:`SismicBuilder`.

    Args:
        model: Loaded syside model containing the SysML state def.
        state_def_qn: Qualified name of the SysML ``state def`` to translate.
        external: Optional ``(module_stem, function_names)`` pair for
            external calc-def backing.

    Returns:
        A sismic ``Statechart`` ready to feed into ``Interpreter``.
    """
    name = state_def_qn.split("::")[-1]
    return StateMachineDriver(model).run(
        state_def_qn, SismicBuilder(name, external=external)
    )
