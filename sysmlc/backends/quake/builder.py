from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from types import ModuleType

import syside
from sismic.model import (
    BasicState,
    CompoundState,
    FinalState,
    OrthogonalState,
    Statechart,
    Transition,
)

from sysmlc.backends.quake.codegen import (
    TICK_METADATA_KEY,
    QuakeRenderNeeds,
    SismicCodeGen,
    math_import_lines,
    py_type,
)
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
from sysmlc.sysml.queries import feature_value

logger = logging.getLogger(__name__)


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
    - the ``_c_*`` completion-flag encoding of an eventless transition
      leaving a composite or ``parallel`` state: a flag per completing
      scope (the composite itself, or each region of a parallel state),
      conjoined into the transition's guard so it fires only once every
      scope has reached its own ``done``; a region with no ``then done``
      of its own is conjoined as a literal ``False`` once any sibling
      scope is gated, so the join can never fire on a subset;
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
        needs: QuakeRenderNeeds | None = None,
        part_system_mode: bool = False,
    ) -> None:
        """Initialize the builder.

        Args:
            name: The sismic statechart name (the state definition's name).
            external: Optional ``(module_stem, function_names)`` pair for
                external calc-def backing.
            needs: A shared preamble registry, or ``None`` for a fresh one.
            part_system_mode: True when the machine is built inside a part
                system, where ``send ... via <port>`` renders as a call to
                the injected router; false for a standalone statechart,
                where such a send is dropped.
        """
        self._name = name
        self._part_system_mode = part_system_mode
        self._needs = needs if needs is not None else QuakeRenderNeeds()
        if external is not None:
            self._needs.register_external(module=external[0], names=external[1])
        self._codegen = SismicCodeGen(
            needs=self._needs, part_system_mode=part_system_mode
        )
        self._preamble: list[str] = []
        self._seen_attrs: dict[str, str] = {}
        self._constraints: list[ConstraintFact] = []
        self._state_facts: list[StateFact] = []
        self._transition_facts: list[TransitionFact] = []
        self._planned_triggers: dict[
            int, _TimeTriggerPlan | _ChangeTriggerPlan
        ] = {}
        self._arming_by_source: dict[str, list[str]] = {}
        self._completion_flag_by_scope: dict[str, str] = {}
        self._completion_flags_by_source: dict[str, str] = {}

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
        self._collect_sends()
        self._plan_triggers()
        self._plan_completions()
        if self._needs.external_module is not None:
            # Assemble a scratch statechart first purely to record the calls;
            self._assemble(Statechart(name=self._name, preamble=""))
        imports = self._preamble_import_lines()
        if imports:
            self._preamble[0:0] = imports
        statechart = self._assemble(
            Statechart(name=self._name, preamble="\n".join(self._preamble))
        )
        for event_name, port in sorted(self._needs.undeliverable_sends):
            logger.warning(
                "machine %r sends %r via %r; without a connected system "
                "context the signal is never delivered",
                self._name,
                event_name,
                port,
            )
        return statechart

    def _collect_sends(self) -> None:
        """Register a dataclass for every signal payload type sends.

        Mirrors rosetta's ``RosettaBuilder._collect_sends``: scans every
        buffered action slot (state entry/do/exit, transition effects) for
        ``send new <Type>(...)`` actions and registers the constructed type,
        independent of codegen and before the preamble is assembled.
        """
        slots: list[syside.ActionUsage | None] = []
        for state in self._state_facts:
            slots += [state.entry_action, state.do_action, state.exit_action]
        slots += [transition.effect for transition in self._transition_facts]
        for slot in slots:
            for action in actions.inline_actions(slot):
                if not isinstance(action, syside.SendActionUsage):
                    continue
                payload = action.payload_argument
                if isinstance(payload, syside.ConstructorExpression):
                    item_type = payload.instantiated_type
                    if isinstance(item_type, syside.Definition):
                        self._register_dataclass(item_type)

    def _assemble(self, statechart: Statechart) -> Statechart:
        """Emit every buffered fact into ``statechart`` and validate it."""
        done_finals: set[str] = set()
        for state in self._state_facts:
            self._emit_state(statechart, state)
        self._emit_constraints(statechart)
        for index, transition in enumerate(self._transition_facts):
            self._emit_transition(
                statechart,
                transition,
                self._planned_triggers.get(index),
                done_finals,
            )
        statechart.validate()
        return statechart

    def _preamble_import_lines(self) -> list[str]:
        """Return import lines before seeded context variables."""
        lines = math_import_lines()
        lines.extend(self._needs.types_import_lines())
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

    @staticmethod
    def _ident(name: str) -> str:
        """Return ``name`` as a Python-identifier-safe fragment."""
        return name.replace("::", "__")

    def _declare_armed(
        self, source: str, name: str, initial: str, armed: str
    ) -> None:
        """Declare a preamble variable, re-armed on every entry of ``source``.

        ``name`` starts at ``initial`` in the preamble, and is set to
        ``armed`` every time ``source`` is (re-)entered, so a restart
        re-arms whatever the variable tracks.
        """
        self._preamble.append(f"{name} = {initial}")
        self._arming_by_source.setdefault(source, []).append(
            f"{name} = {armed}"
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
        ident = self._ident(source)
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
            self._declare_armed(source, counter, "0", f"{counter} + 1")
        # The time-trigger event self-describes which state and counter its
        # guard checks, so a runner can drop events the guard would ignore.
        stamp = f"{TICK_METADATA_KEY}=('{source}', '{counter}')"
        if isinstance(trigger, AfterTrigger):
            self._arming_by_source[source].append(
                f"send('{event_name}', n={counter}, delay={delay}, {stamp})"
            )
            return
        delta = f"_d_{ident}_t{ordinal}"
        tick_send = f"send('{event_name}', n={counter}, delay={delta}, {stamp})"
        self._arming_by_source[source].extend(
            [
                f"{delta} = ({delay}) - time",
                f"if {delta} >= 0:",
                f"    {tick_send}",
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
        ident = self._ident(source)
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
        self._declare_armed(source, flag, "False", "True")

    def _plan_completions(self) -> None:
        """Plan the completion-flag machinery for eventless-out composites.

        An eventless transition sourced at a composite or ``parallel``
        state may only fire once that state reaches its own ``done``, not
        the instant it is entered. Sismic has no built-in notion of this,
        so each completing scope (a parallel state's regions, or the
        composite itself) gets a flag: false on entry, true once its own
        final state is reached, conjoined into the transition's guard.

        A source with no completing scope targeted by a ``then done``
        stays entirely ungated. Once any scope is gated, every scope is
        required: a region with no ``then done`` of its own is conjoined
        as a literal ``False``, so the join can never fire on a subset.
        """
        eventless_sources: set[str] = set()
        completion_scopes: set[str] = set()
        for transition in self._transition_facts:
            if transition.trigger is None:
                eventless_sources.add(transition.source)
            if isinstance(transition.target, CompletionTarget):
                completion_scopes.add(transition.target.scope)
        children_by_parent: dict[str, list[str]] = {}
        for child in self._state_facts:
            if child.parent is not None:
                children_by_parent.setdefault(child.parent, []).append(
                    child.name
                )
        for state in self._state_facts:
            if state.name not in eventless_sources:
                continue
            if state.kind is StateKind.PARALLEL:
                scopes = children_by_parent.get(state.name, [])
            elif state.kind is StateKind.COMPOSITE:
                scopes = [state.name]
            else:
                continue
            if not any(scope in completion_scopes for scope in scopes):
                continue
            flags: list[str] = []
            for scope in scopes:
                if scope not in completion_scopes:
                    # This scope never reaches a done of its own, so the
                    # join it participates in can never legitimately fire.
                    flags.append("False")
                    continue
                flag = f"_c_{self._ident(scope)}"
                self._declare_armed(state.name, flag, "False", "False")
                self._completion_flag_by_scope[scope] = flag
                flags.append(flag)
            self._completion_flags_by_source[state.name] = " and ".join(flags)

    def _register_dataclass(self, definition: syside.Definition) -> None:
        """Render ``definition`` as a dataclass and register it on the preamble.

        Handles item defs and composite attr defs.  Fields are typed via
        :func:`py_type` and default to the model's declared default, else
        ``None`` (every field defaulted, so the dataclass needs no
        field-ordering care).
        """
        assert definition.name is not None
        lines: list[str] = ["@dataclass", f"class {definition.name}:"]
        attrs = definition.owned_attributes.collect()
        if not attrs:
            lines.append("    pass")
        # NOTE: a field whose type is itself a composite is annotated with
        # that type's name via py_type(), but is NOT recursively registered
        # here. No current model nests composites; revisit if one does.
        for attr in attrs:
            assert attr.name is not None
            default_expr = feature_value(attr)
            if default_expr is None:
                default = "None"
            else:
                try:
                    default = self._codegen.render_expression(default_expr)
                except (ValueError, UnsupportedConstructError):
                    # Quantity / complex expressions can't render as plain
                    # Python literals; fall back to None (design note: only
                    # scalar literal defaults are rendered in the companion).
                    default = "None"
            lines.append(f"    {attr.name}: {py_type(attr)} = {default}")
        self._needs.register_dataclass(definition.name, tuple(lines))

    def _render_value(self, value: AttributeValue) -> str | None:
        if value is None:
            return None
        if isinstance(value, CompositeValue):
            self._register_dataclass(value.definition)
            fields = ", ".join(
                f"{name}={self._render_value(field)}"
                for name, field in value.fields
            )
            return f"{value.type_name}({fields})"
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
            rendered = self._codegen.render_expression(fact.expression)
            if fact.is_negated:
                rendered = f"not ({rendered})"
            statechart.state_for(state_name).invariants.append(rendered)

    def _emit_transition(
        self,
        statechart: Statechart,
        transition: TransitionFact,
        plan: _TimeTriggerPlan | _ChangeTriggerPlan | None,
        done_finals: set[str],
    ) -> None:
        if transitions.self_loop_is_unstable(transition):
            raise UnsupportedConstructError(
                "A self-loop transition would never stabilize (no event, "
                "timer, or effect to break the loop)."
            )
        target = (
            self._final_state(statechart, transition.target.scope, done_finals)
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

    @staticmethod
    def _conjoin(extra: str, condition: str | None) -> str:
        """Return ``extra`` alone, or ANDed with ``condition`` when present."""
        return extra if condition is None else f"{extra} and ({condition})"

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
        Conjoining the completion flags is what makes an eventless
        transition leaving a composite or parallel state wait for that
        state to reach its own ``done`` (every region, for a parallel
        state), instead of firing as soon as the state is entered.
        """
        condition = (
            codegen.render_expression(transition.guard)
            if transition.guard is not None
            else None
        )
        if transition.trigger is None:
            completion_condition = self._completion_flags_by_source.get(
                transition.source
            )
            if completion_condition is not None:
                condition = self._conjoin(completion_condition, condition)
        if plan is None:
            return condition
        return self._conjoin(f"event.n == {plan.counter}", condition)

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
            part_system_mode=self._part_system_mode,
            feature_aliases=((trigger.payload_feature, "event"),),
        )

    def _final_state(
        self, statechart: Statechart, scope: str, done_finals: set[str]
    ) -> str:
        scope_name = scope or self._name
        final_name = "done" if scope == "" else f"{scope}::done"
        if final_name not in done_finals:
            completion_flag = self._completion_flag_by_scope.get(scope)
            on_entry = (
                f"{completion_flag} = True"
                if completion_flag is not None
                else None
            )
            statechart.add_state(
                FinalState(final_name, on_entry=on_entry), parent=scope_name
            )
            done_finals.add(final_name)
        return final_name


def attach_types_module(
    statechart: Statechart, needs: QuakeRenderNeeds
) -> None:
    """Expose the companion types module on a built statechart."""
    lines = needs.companion_module_lines()
    statechart.types_module_name = needs.types_module if lines else None
    statechart.types_module_lines = tuple(lines)
    if lines and needs.types_module is not None:
        _register_module(needs.types_module, lines)


_module_sources: dict[str, str] = {}


def _register_module(name: str, lines: list[str]) -> None:
    """Materialize a companion module into ``sys.modules`` for import.

    Idempotent for identical source (rebuilding the same model in one
    process is a no-op); a different source under an already-used name is
    refused, since two builds sharing a module name would otherwise
    silently clobber each other's classes mid-run.
    """
    source = "\n".join(lines)
    existing = sys.modules.get(name)
    if existing is not None:
        if _module_sources.get(name) == source:
            return
        raise UnsupportedConstructError(
            f"types module {name!r} is already registered with different "
            "content; two builds picked the same module name for "
            "different types."
        )
    module = ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(source, f"<{name}>", "exec"), module.__dict__)
    except BaseException:
        del sys.modules[name]
        raise
    _module_sources[name] = source


def build_statechart(
    model: syside.Model,
    state_def_qn: str,
    *,
    external: tuple[str, frozenset[str]] | None = None,
    part_system_mode: bool = False,
    needs: QuakeRenderNeeds | None = None,
) -> Statechart:
    """Build a sismic Statechart from a SysML state definition.

    Wires the generic :class:`StateMachineDriver` to a :class:`SismicBuilder`.

    Args:
        model: Loaded syside model containing the SysML state def.
        state_def_qn: Qualified name of the SysML ``state def`` to translate.
        external: Optional ``(module_stem, function_names)`` pair for
            external calc-def backing.
        part_system_mode: True when the machine is built inside a part
            system, where ``send ... via <port>`` renders as a call to
            the injected router; false for a standalone statechart,
            where such a send is dropped.
        needs: A shared preamble registry, or ``None`` for a fresh one.

    Returns:
        A sismic ``Statechart`` ready to feed into ``Interpreter``.
    """
    name = state_def_qn.split("::")[-1]
    if needs is None:
        needs = QuakeRenderNeeds()
        needs.types_module = f"{name}_types"
        owns_needs = True
    else:
        owns_needs = False
    builder = SismicBuilder(
        name, external=external, part_system_mode=part_system_mode, needs=needs
    )
    statechart = StateMachineDriver(model).run(state_def_qn, builder)
    if owns_needs:
        attach_types_module(statechart, needs)
    return statechart
