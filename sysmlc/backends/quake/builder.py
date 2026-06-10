from __future__ import annotations

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


class SismicBuilder:
    """Assemble a sismic ``Statechart`` from neutral state-machine facts.

    Implements the ``TargetBuilder`` protocol. This is where every
    sismic-specific representational choice lives: the flat preamble with its
    name-collision policy, the ``do`` -> run-once ``on_entry`` fusion, the
    ``then done`` -> ``FinalState`` synthesis, the ``after(...)`` guard, and the
    capability rejections (``at``/``when`` triggers, ``after`` combined with an
    ``if`` guard, non-inline ``do`` bodies, and unstable self-loops).

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

    def bind_attribute(self, binding: AttributeBinding) -> None:
        """Seed an attribute into sismic's flat preamble namespace.

        Raises:
            UnsupportedConstructError: If two attributes in different scopes
                share a simple name (sismic's context is flat).
        """
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
        if self._needs_namespace:
            self._preamble.insert(0, "from types import SimpleNamespace")
        statechart = Statechart(
            name=self._name, preamble="\n".join(self._preamble)
        )
        for state in self._state_facts:
            self._emit_state(statechart, state)
        for transition in self._transition_facts:
            self._emit_transition(statechart, transition)
        statechart.validate()
        return statechart

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
        parts = [part for part in (entry, do) if part is not None]
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
        self, statechart: Statechart, transition: TransitionFact
    ) -> None:
        guard = self._guard(transition)
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
        event = (
            transition.trigger.signal_name
            if transition.trigger is not None
            and transition.trigger.kind is TriggerKind.SIGNAL
            else None
        )
        statechart.add_transition(
            Transition(
                source=transition.source,
                target=target,
                event=event,
                guard=guard,
                action=self._statements(transition.effect),
            )
        )

    def _guard(self, transition: TransitionFact) -> str | None:
        time_guard = self._time_guard(transition.trigger)
        condition = (
            self._codegen.render_expression(transition.guard)
            if transition.guard is not None
            else None
        )
        if time_guard is not None and condition is not None:
            raise UnsupportedConstructError(
                "`accept after` combined with an `if` guard is unsupported."
            )
        return time_guard if time_guard is not None else condition

    def _time_guard(self, trigger: Trigger | None) -> str | None:
        if trigger is None or trigger.kind is TriggerKind.SIGNAL:
            return None
        if trigger.kind in (TriggerKind.AT, TriggerKind.WHEN):
            raise UnsupportedConstructError(
                f"an `accept {trigger.kind.name.lower()}` trigger is "
                "unsupported. Only the relative `accept after <duration>` time "
                "trigger is supported."
            )
        after = trigger.after
        if isinstance(after, float):
            return f"after({after!r})"
        assert after is not None  # AFTER always carries a duration
        return f"after({self._codegen.render_expression(after)})"

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
