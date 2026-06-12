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

from sysmlc.backends.quake.codegen import SismicCodeGen
from sysmlc.codegen.python import join_statements
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions, transitions
from sysmlc.semantics.statemachine.driver import StateMachineDriver
from sysmlc.semantics.statemachine.facts import (
    AttributeBinding,
    AttributeValue,
    CompletionTarget,
    CompositeValue,
    StateFact,
    StateKind,
    TransitionFact,
    Trigger,
    TriggerKind,
)

if TYPE_CHECKING:
    import syside


@dataclass(frozen=True)
class _TimeTriggerPlan:
    """What an ``accept after`` transition must reference when emitted.

    Attributes:
        event_name: The synthetic internal event carrying the deadline.
        counter: Context name of the source state's activation counter.
    """

    event_name: str
    counter: str


class SismicBuilder:
    """Assemble a sismic ``Statechart`` from neutral state-machine facts.

    Implements the ``TargetBuilder`` protocol. This is where every
    sismic-specific representational choice lives:
    - the flat preamble, with its name-collision policy;
    - the ``do`` -> run-once ``on_entry`` fusion;
    - the ``then done`` -> ``FinalState`` synthesis;
    - the one-shot delayed-event encoding of ``accept after``: a
      per-activation counter bumped ``on entry``, a ``send('_tick_...',
      n=..., delay=...)`` arming call, and an event-triggered transition
      whose guard checks ``event.n``;
    - the capability rejections: ``at``/``when`` triggers, non-inline ``do``
      bodies, unstable self-loops, and model names starting with ``_``
      (the underscore namespace is reserved for the generated machinery).

    Sismic's ``Statechart.preamble`` is read-only after construction, so facts
    are buffered and the whole statechart is built in :meth:`result`.
    """

    def __init__(self, name: str) -> None:
        """Initialize the builder.

        Args:
            name: The sismic statechart name (the state definition's name).
        """
        self._name = name
        self._codegen = SismicCodeGen()
        self._preamble: list[str] = []
        self._needs_namespace = False
        self._seen_attrs: dict[str, str] = {}
        self._state_facts: list[StateFact] = []
        self._transition_facts: list[TransitionFact] = []
        self._done_finals: set[str] = set()
        # Emission plans for time triggers, keyed by the transition fact's
        # position in `_transition_facts`; filled by `_plan_time_triggers`.
        self._planned_triggers: dict[int, _TimeTriggerPlan] = {}
        # Arming statements appended to each timed source state's on_entry
        # (the counter bump plus one send per time trigger), keyed by the
        # source state's path.
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

    def add_state(self, state: StateFact) -> None:
        """Buffer a state fact (emitted in :meth:`result`)."""
        self._state_facts.append(state)

    def add_transition(self, transition: TransitionFact) -> None:
        """Buffer a transition fact (emitted in :meth:`result`)."""
        self._transition_facts.append(transition)

    def result(self) -> Statechart:
        """Build, validate, and return the assembled sismic statechart."""
        self._plan_time_triggers()
        if self._needs_namespace:
            self._preamble.insert(0, "from types import SimpleNamespace")
        statechart = Statechart(
            name=self._name, preamble="\n".join(self._preamble)
        )
        for state in self._state_facts:
            self._emit_state(statechart, state)
        for index, transition in enumerate(self._transition_facts):
            self._emit_transition(
                statechart, transition, self._planned_triggers.get(index)
            )
        statechart.validate()
        return statechart

    def _plan_time_triggers(self) -> None:
        """Plan the delayed-event machinery for every ``accept after``.

        Walks the buffered transitions in declaration order and records,
        for each time trigger, the coordinated pieces its emission needs:
        the counter initialization (appended to the preamble), the arming
        statements for the source state's ``on entry`` (a counter bump plus
        one delayed ``send`` per trigger, stored in ``_arming_by_source``),
        and the event and counter names the transition will use (stored in
        ``_planned_triggers``).

        The counter exists to invalidate stale ticks: sismic never cancels
        a delayed event when its state exits, so a tick armed by an earlier
        activation must match nothing when it is delivered.
        """
        per_source_ordinal: dict[str, int] = {}
        for index, transition in enumerate(self._transition_facts):
            trigger = transition.trigger
            if trigger is None or trigger.kind is not TriggerKind.AFTER:
                continue
            source = transition.source
            ordinal = per_source_ordinal.get(source, 0) + 1
            per_source_ordinal[source] = ordinal
            ident = source.replace("::", "__")
            counter = f"_n_{ident}"
            delay = self._render_value(trigger.after)
            assert delay is not None  # AFTER always carries a duration
            event_name = f"_tick_{ident}_t{ordinal}"
            self._planned_triggers[index] = _TimeTriggerPlan(
                event_name=event_name, counter=counter
            )
            if source not in self._arming_by_source:
                self._preamble.append(f"{counter} = 0")
                self._arming_by_source[source] = [f"{counter} = {counter} + 1"]
            self._arming_by_source[source].append(
                f"send('{event_name}', n={counter}, delay={delay})"
            )

    def _render_value(self, value: AttributeValue) -> str | None:
        if value is None:
            return None
        if isinstance(value, CompositeValue):
            self._needs_namespace = True
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

    def _statements(self, action: syside.ActionUsage | None) -> str | None:
        rendered = join_statements(
            [
                self._codegen.render_action(candidate)
                for candidate in actions.inline_actions(action)
            ]
        )
        return rendered or None

    def _emit_transition(
        self,
        statechart: Statechart,
        transition: TransitionFact,
        plan: _TimeTriggerPlan | None,
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
        statechart.add_transition(
            Transition(
                source=transition.source,
                target=target,
                event=self._event(transition.trigger, plan),
                guard=self._guard(transition, plan),
                action=self._statements(transition.effect),
            )
        )

    def _event(
        self, trigger: Trigger | None, plan: _TimeTriggerPlan | None
    ) -> str | None:
        """Return the transition's sismic event name, or None.

        A signal accepter triggers on its payload type's name; a time
        trigger triggers on its planned ``_tick_*`` event.

        Raises:
            UnsupportedConstructError: If the trigger is an ``accept at`` or
                ``accept when`` (no sismic emission for them), or if a signal
                name starts with the reserved ``_`` prefix.
        """
        if trigger is None:
            return None
        if trigger.kind in (TriggerKind.AT, TriggerKind.WHEN):
            raise UnsupportedConstructError(
                f"an `accept {trigger.kind.name.lower()}` trigger is "
                "unsupported."
            )
        if trigger.kind is TriggerKind.AFTER:
            assert plan is not None  # planned for every AFTER trigger
            return plan.event_name
        name = trigger.signal_name
        if name is not None and name.startswith("_"):
            raise UnsupportedConstructError(
                f"signal {name!r} starts with an underscore; that "
                "namespace is reserved for the generated machinery. "
            )
        return name

    def _guard(
        self, transition: TransitionFact, plan: _TimeTriggerPlan | None
    ) -> str | None:
        """Compose the transition's sismic guard string, or None.

        A time trigger contributes the stale-tick check ``event.n ==
        <counter>``; an ``if`` guard contributes its rendered condition;
        when both are present they are conjoined. The conjunction is what
        makes ``accept after ... if ...`` faithful to SysML: a deadline
        delivered while the condition is false is consumed, with no late
        firing.
        """
        condition = (
            self._codegen.render_expression(transition.guard)
            if transition.guard is not None
            else None
        )
        if plan is None:
            return condition
        deadline = f"event.n == {plan.counter}"
        if condition is None:
            return deadline
        return f"{deadline} and ({condition})"

    def _final_state(self, statechart: Statechart, scope: str) -> str:
        scope_name = scope or self._name
        final_name = "done" if scope == "" else f"{scope}::done"
        if final_name not in self._done_finals:
            statechart.add_state(FinalState(final_name), parent=scope_name)
            self._done_finals.add(final_name)
        return final_name


def build_statechart(model: syside.Model, state_def_qn: str) -> Statechart:
    """Build a sismic Statechart from a SysML state definition.

    Wires the generic :class:`StateMachineDriver` to a :class:`SismicBuilder`.

    Args:
        model: Loaded syside model containing the SysML state def.
        state_def_qn: Qualified name of the SysML ``state def`` to translate.

    Returns:
        A sismic ``Statechart`` ready to feed into ``Interpreter``.
    """
    name = state_def_qn.split("::")[-1]
    return StateMachineDriver(model).run(state_def_qn, SismicBuilder(name))
