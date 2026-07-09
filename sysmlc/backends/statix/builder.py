from __future__ import annotations

import re

import syside

from sysmlc.backends.statix.codegen import CCodeGen
from sysmlc.backends.statix.program import (
    COMPLETION_EVENT,
    TIMEOUT_EVENT,
    CAction,
    CContext,
    CField,
    CGuard,
    CInvariant,
    CProgram,
    CProject,
    CSend,
    CState,
    CStruct,
    CTimeout,
    CTransition,
)
from sysmlc.codegen.python import payload_signature
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine import actions
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
    WhenTrigger,
)
from sysmlc.semantics.statemachine.interface import send_receiver_is_own_port

_DEFAULT_QUEUE_CAPACITY = 8

# Mirrors sc_runtime.h's SC_TICKS_PER_SECOND default (1000u); a project that
# overrides that compile-time constant is responsible for its own literal
# duration/instant range, exactly as it already is for SC_MAX_TRANSITIONS et
# al. The builder can only validate against the documented default.
#
# CAVEAT: this check runs once, at build time, against the *default*
# (1000). Literal durations/instants fold to a symbolic C expression
# (`5u * SC_TICKS_PER_SECOND`) specifically so there is zero runtime cost --
# the actual multiplication happens in the C compiler, using whatever
# SC_TICKS_PER_SECOND value the project is *actually* compiled with. That
# value is unknown here. A literal validated in-range at the default stays
# safely in-range for any *larger* override (more ticks per second only
# shrinks the maximum representable duration further below what was
# checked). A project compiled with a *smaller* SC_TICKS_PER_SECOND (or one
# that otherwise needs literals larger than ~4294967.295s) must re-validate
# its own model: the generated multiplication is unsigned and wraps
# silently in C rather than erroring at compile time. This is the same
# override contract as SC_MAX_TRANSITIONS et al., stated loudly here because
# unlike those bounds, a silent wrap here would corrupt a due-condition
# rather than fail a loop guard.
_TICKS_PER_SECOND_DEFAULT = 1000
_MAX_TICKS = (1 << 32) - 1
_MAX_LITERAL_SECONDS = _MAX_TICKS / _TICKS_PER_SECOND_DEFAULT

# The top of the 16-bit sc_event_id_t space is reserved: SC_EVENT_TIMEOUT
# (0xFFFE) and SC_EVENT_COMPLETION (0xFFFF). Signal events are numbered from
# 1, so this bounds how many distinct signal events one machine may declare.
# Latent before this increment (a machine could in principle already collide
# with SC_EVENT_COMPLETION at 65535 events); adding a second reserved id
# makes the boundary worth checking explicitly rather than leaving both
# unchecked.
_MAX_SIGNAL_EVENTS = 0xFFFD


def _literal_ticks_expr(seconds: float) -> str:
    """Render a literal after/at duration/instant as a compile-time tick expr.

    Rejects a negative or out-of-representable-range literal at build time
    (an unambiguous model error); an in-range value folds to a C expression
    the compiler evaluates at compile time regardless of the actually
    compiled SC_TICKS_PER_SECOND value (see the CAVEAT above the module
    constants for what that implies for a `-DSC_TICKS_PER_SECOND` override).
    """
    if seconds < 0.0 or seconds > _MAX_LITERAL_SECONDS:
        raise UnsupportedConstructError(
            f"a time-triggered duration/instant of {seconds!r} [s] is out "
            "of the representable tick range (0 <= seconds <= "
            f"{_MAX_LITERAL_SECONDS!r}, at the default "
            "SC_TICKS_PER_SECOND=1000); statix rejects it at build time."
        )
    if seconds == int(seconds):
        return f"({int(seconds)}u * SC_TICKS_PER_SECOND)"
    return f"((sc_time_t)({seconds!r} * (double)SC_TICKS_PER_SECOND))"


def _c_identifier(name: str) -> str:
    """Sanitize a SysML name into a lowercase snake_case C identifier.

    CamelCase word boundaries become underscores, so ``MachineExitDecrement``
    reads as ``machine_exit_decrement`` rather than ``machineexitdecrement``.
    """
    ident = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    ident = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", ident)
    ident = re.sub(r"[^0-9a-zA-Z_]", "_", ident)
    ident = re.sub(r"_+", "_", ident).strip("_")
    return ident.lower() or "machine"


def _c_prefix(qualified_name: str) -> str:
    """Sanitize a SysML qualified name into a stable C symbol prefix."""
    return _c_identifier(qualified_name.replace("::", "_"))


class StatixBuilder:
    """Assemble a C statechart (:class:`CProgram`) from neutral facts.

    Implements ``TargetBuilder``. Every C representational choice lives here:
    states become an enum + a per-state table; eventless transitions carry
    :data:`COMPLETION_EVENT`; signal triggers become events; guards/effects/
    attributes lower via :class:`CCodeGen` into a generated context struct.
    Composite states, ``then done`` finals, one-shot ``do`` actions, asserted
    constraints (invariants), and ``send`` self-events (id-only, or including a
    readable scalar Real payload like ``reading.value``) are supported.
    Parallel, history, timers (``after``/``at``/``when``), sends to other
    parts, reading accept payload data beyond the single marshalled Real
    attribute, external function calls in expressions, and
    non-scalar/non-composite attributes are rejected loudly.
    """

    def __init__(self, qualified_name: str) -> None:
        name = qualified_name.split("::")[-1]
        self._name = name
        self._qualified_name = qualified_name
        self._prefix = _c_prefix(qualified_name)
        # Guard/action codegen is re-created in result() once the attribute
        # names are known; the init codegen never sees a context pointer.
        self._gen = CCodeGen()
        self._init_gen = CCodeGen(allow_context=False)
        self._root: StateFact | None = None
        self._state_facts: list[StateFact] = []
        self._transition_facts: list[TransitionFact] = []
        self._bindings: list[AttributeBinding] = []
        self._guard_names: dict[str, str] = {}
        self._guards: list[CGuard] = []
        self._actions: list[CAction] = []
        self._used_action_names: set[str] = set()
        self._events: dict[str, None] = {}
        self._structs: dict[str, CStruct] = {}
        self._finals: dict[str, CState] = {}
        self._constraints: list[ConstraintFact] = []
        self._has_send = False
        self._sends: list[CSend] = []
        self._payload_reads: dict[str, tuple[str, ...]] = {}
        self._scoped_gens: list[CCodeGen] = []
        self._real_attribute_names: frozenset[str] = frozenset()
        self._attribute_names: frozenset[str] = frozenset()
        self._attribute_c_types: dict[str, str] = {}
        self._state_kinds: dict[str, StateKind] = {}
        self._timeouts: list[CTimeout] = []
        self._timeout_sources: set[str] = set()
        self._has_timer = False
        self._timeouts_use_ctx = False

    # -- TargetBuilder protocol --

    def bind_attribute(self, binding: AttributeBinding) -> None:
        """Buffer a root-scope attribute (state-scoped ones are rejected)."""
        if binding.scope:
            raise UnsupportedConstructError(
                f"attribute {binding.name!r} is scoped to state "
                f"{binding.scope!r}; statix supports root-scope attributes "
                "only."
            )
        self._bindings.append(binding)

    def bind_constraint(self, fact: ConstraintFact) -> None:
        """Buffer asserted constraint; emitted as an invariant in result()."""
        self._constraints.append(fact)

    def add_state(self, state: StateFact) -> None:
        """Buffer a state; remember the root, reject parallel/final states."""
        if state.parent is None:
            self._root = state
            return
        if state.kind in (StateKind.PARALLEL, StateKind.FINAL):
            raise UnsupportedConstructError(
                f"state {state.name!r} is {state.kind.name}; statix supports "
                "composite and leaf states only (no parallel/history yet)."
            )
        self._state_kinds[state.name] = state.kind
        self._state_facts.append(state)

    def add_transition(self, transition: TransitionFact) -> None:
        """Buffer a transition fact (emitted in :meth:`result`)."""
        self._transition_facts.append(transition)

    def result(self) -> CProgram:
        """Assemble and return the C statechart program."""
        root = self._root
        if root is None or root.kind is StateKind.PARALLEL:
            raise UnsupportedConstructError(
                "statix requires a composite root state with leaf substates."
            )
        if root.kind is not StateKind.COMPOSITE:
            raise UnsupportedConstructError(
                "the state definition declares no substates."
            )
        self._reject_machine_level_actions(root)
        context = self._build_context()
        self._real_attribute_names = frozenset(
            f.name for f in context.fields if f.c_type == "double"
        )
        self._attribute_names = frozenset(f.name for f in context.fields)
        self._attribute_c_types = {f.name: f.c_type for f in context.fields}
        self._gen = CCodeGen(
            attribute_names=self._attribute_names,
            real_attributes=self._real_attribute_names,
        )
        self._payload_reads = self._detect_payload_reads()
        real_states = tuple(self._build_state(f) for f in self._state_facts)
        transitions = tuple(
            self._build_transition(t) for t in self._transition_facts
        )
        for event in self._payload_reads:
            if not any(s.event == event for s in self._sends):
                raise UnsupportedConstructError(
                    f"the payload of event {event!r} is read, but no `send` "
                    "in this machine marshals it; statix cannot receive "
                    "payload-bearing events from outside yet."
                )
        states = real_states + tuple(self._finals.values())
        invariants = tuple(self._build_invariant(c) for c in self._constraints)
        if root.initial_substate is None:
            raise UnsupportedConstructError(
                "the machine declares no initial state."
            )
        max_depth = max((s.name.count("::") + 1 for s in states), default=1)
        needs_math = self._gen.needs_math or any(
            g.needs_math for g in self._scoped_gens
        )
        if len(self._events) > _MAX_SIGNAL_EVENTS:
            raise UnsupportedConstructError(
                f"this machine declares {len(self._events)} distinct signal "
                f"events, exceeding the representable range (at most "
                f"{_MAX_SIGNAL_EVENTS}); the top of the 16-bit event id "
                "space is reserved for SC_EVENT_TIMEOUT/SC_EVENT_COMPLETION."
            )
        return CProgram(
            name=self._name,
            qualified_name=self._qualified_name,
            prefix=self._prefix,
            states=states,
            events=tuple(self._events),
            guards=tuple(self._guards),
            actions=tuple(self._actions),
            transitions=transitions,
            context=context,
            queue_capacity=_DEFAULT_QUEUE_CAPACITY,
            initial=root.initial_substate,
            max_depth=max_depth,
            invariants=invariants,
            needs_math=needs_math,
            has_send=self._has_send,
            timeouts=tuple(self._timeouts),
            has_timer=self._has_timer,
            timeouts_use_ctx=self._timeouts_use_ctx,
        )

    def _payload_gen(self, payload_feature: syside.Feature) -> CCodeGen:
        return CCodeGen(
            attribute_names=frozenset(
                self._attribute_names | {b.name for b in self._bindings}
            ),
            real_attributes=self._real_attribute_names,
            payload_feature=payload_feature,
        )

    def _detect_payload_reads(self) -> dict[str, tuple[str, ...]]:
        """Map event name -> read payload path, before lowering sends.

        Renders each payload-bound transition's guard and assignment RHSs
        with a throwaway scoped codegen whose only job is to flag (and
        shape-check) payload reads; the text is discarded. Runs before any
        action lowering so `_csend_for` can decide marshalled vs id-only
        without ever rendering an unread constructor argument. A path is one
        segment (`.value`) or two (one composite hop, `.sample.value`).
        """
        reads: dict[str, tuple[str, ...]] = {}
        for t in self._transition_facts:
            trigger = t.trigger
            if (
                not isinstance(trigger, SignalTrigger)
                or trigger.payload_feature is None
            ):
                continue
            probe = self._payload_gen(trigger.payload_feature)
            if t.guard is not None:
                probe.render_expression(t.guard)
            for a in actions.inline_actions(t.effect):
                if isinstance(a, syside.AssignmentActionUsage):
                    probe.render_action(a)
            for path in sorted(probe.payload_reads):
                known = reads.setdefault(trigger.signal_name, path)
                if known != path:
                    raise UnsupportedConstructError(
                        f"event {trigger.signal_name!r} payload is read as "
                        f"both .{'.'.join(known)} and .{'.'.join(path)}; "
                        "statix supports one readable path per event."
                    )
        return reads

    def _reject_machine_level_actions(self, root: StateFact) -> None:
        """Reject inline entry/do/exit actions on the state def itself."""
        for slot in (root.entry_action, root.do_action, root.exit_action):
            if actions.inline_actions(slot):
                raise UnsupportedConstructError(
                    "machine-level entry/do/exit actions are not supported by "
                    "statix yet; put actions on states."
                )

    # -- attributes -> context struct --

    def _build_context(self) -> CContext:
        fields = tuple(self._field(binding) for binding in self._bindings)
        return CContext(fields=fields, structs=tuple(self._structs.values()))

    def _field(self, binding: AttributeBinding) -> CField:
        value = binding.value
        if isinstance(value, CompositeValue):
            c_type = self._register_struct(value)
            return CField(binding.name, c_type, self._struct_init(value))
        c_type = self._scalar_c_type(value, binding.name)
        return CField(binding.name, c_type, self._scalar_init(value, c_type))

    def _scalar_c_type(self, value: AttributeValue, name: str) -> str:
        if isinstance(value, float):
            return "double"
        if isinstance(value, syside.LiteralBoolean):
            return "bool"
        if isinstance(value, syside.LiteralInteger):
            return "int32_t"
        if isinstance(value, syside.LiteralRational):
            return "double"
        raise UnsupportedConstructError(
            f"attribute {name!r} has no scalar literal default; statix "
            "iteration 1 infers a C type from a Boolean/Integer/Real literal "
            "initializer (or a composite attribute def)."
        )

    def _scalar_init(self, value: AttributeValue, c_type: str) -> str:
        if isinstance(value, float):
            return repr(value) if c_type == "double" else str(int(value))
        assert not isinstance(value, CompositeValue) and value is not None
        return self._init_gen.render_expression(value)

    def _register_struct(self, composite: CompositeValue) -> str:
        c_type = f"{self._prefix}_{_c_identifier(composite.type_name)}_t"
        if c_type not in self._structs:
            fields: list[CField] = []
            for field_name, field_value in composite.fields:
                if isinstance(field_value, CompositeValue):
                    field_type = self._register_struct(field_value)
                else:
                    field_type = self._scalar_c_type(field_value, field_name)
                fields.append(CField(field_name, field_type, ""))
            # Added AFTER nested structs so the emit order is nested-first.
            self._structs[c_type] = CStruct(name=c_type, fields=tuple(fields))
        return c_type

    def _struct_init(self, composite: CompositeValue) -> str:
        parts: list[str] = []
        for field_name, field_value in composite.fields:
            if isinstance(field_value, CompositeValue):
                rendered = self._struct_init(field_value)
            elif isinstance(field_value, float):
                rendered = repr(field_value)
            else:
                assert field_value is not None
                rendered = self._init_gen.render_expression(field_value)
            parts.append(f".{field_name} = {rendered}")
        return "{" + ", ".join(parts) + "}"

    # -- states / transitions --

    def _build_state(self, fact: StateFact) -> CState:
        # Display name is the driver's root-relative dotted path; the C
        # identifier is derived from it by the serializer.
        name = fact.name
        stem = _c_identifier(name)
        root_name = self._root.name if self._root is not None else None
        parent = None if fact.parent == root_name else fact.parent
        return CState(
            name=name,
            entry_action_id=self._entry_action_id(fact, stem),
            exit_action_id=self._action_for(fact.exit_action, f"{stem}_exit"),
            parent=parent,
            initial_child=fact.initial_substate,
        )

    def _final_for(self, scope: str) -> str:
        """Return the display name of the (deduped) final state for a scope.

        Mirrors quake: root scope ``""`` synthesizes ``done`` (top-level, parent
        None); a composite scope ``running`` synthesizes ``running::done`` under
        it. Multiple ``then done`` in one scope share the single final.
        """
        name = "done" if scope == "" else f"{scope}::done"
        if name not in self._finals:
            self._finals[name] = CState(
                name=name,
                entry_action_id=None,
                exit_action_id=None,
                parent=None if scope == "" else scope,
                initial_child=None,
                is_final=True,
            )
        return name

    def _build_transition(self, t: TransitionFact) -> CTransition:
        event = self._event_of(t.trigger, t.source)
        gen = self._gen
        if (
            isinstance(t.trigger, SignalTrigger)
            and t.trigger.payload_feature is not None
        ):
            gen = self._payload_gen(t.trigger.payload_feature)
            self._scoped_gens.append(gen)
        guard = self._guard_for(t.guard, gen)
        source = t.source
        label = (
            "completion"
            if event == COMPLETION_EVENT
            else "timeout"
            if event == TIMEOUT_EVENT
            else event
        )
        action = self._action_for(
            t.effect, f"{_c_identifier(source)}_{label}_effect", gen
        )
        if isinstance(t.target, CompletionTarget):
            target = self._final_for(t.target.scope)
        else:
            target = t.target
        return CTransition(source, event, guard, action, target)

    def _event_of(self, trigger: object | None, source: str) -> str:
        if trigger is None:
            return COMPLETION_EVENT
        if isinstance(trigger, SignalTrigger):
            # A bound payload name is allowed; reading its data is rejected by
            # the codegen (the payload feature is not a context attribute).
            self._events.setdefault(trigger.signal_name, None)
            return trigger.signal_name
        if isinstance(trigger, (AfterTrigger, AtTrigger)):
            return self._register_timeout(source, trigger)
        if isinstance(trigger, WhenTrigger):
            raise UnsupportedConstructError(
                "change triggers (`when`) are not supported by statix yet."
            )
        raise UnsupportedConstructError(
            f"unsupported trigger: {type(trigger).__name__}"
        )

    def _register_timeout(
        self, source: str, trigger: AfterTrigger | AtTrigger
    ) -> str:
        """Build (or reject) the CTimeout row for one after/at transition.

        Rejections (composite source, second timer on one state) are
        implemented here in Task 4; this task only wires the happy path.
        """
        self._timeout_sources.add(source)
        self._has_timer = True
        if isinstance(trigger, AtTrigger):
            is_at = True
            value = trigger.instant
        else:
            is_at = False
            value = trigger.duration
        if isinstance(value, float):
            self._timeouts.append(
                CTimeout(
                    source=source,
                    is_at=is_at,
                    literal_ticks=_literal_ticks_expr(value),
                )
            )
        else:
            self._timeouts_use_ctx = True
            self._timeouts.append(
                CTimeout(
                    source=source,
                    is_at=is_at,
                    attr_expr=self._gen.render_expression(value),
                )
            )
        return TIMEOUT_EVENT

    def _build_invariant(self, fact: ConstraintFact) -> CInvariant:
        rendered = self._gen.render_expression(fact.expression)
        if fact.is_negated:
            rendered = f"!({rendered})"
        guard = self._register_rendered_guard(rendered)
        scope = None if fact.scope == "" else fact.scope
        return CInvariant(scope=scope, guard=guard)

    def _register_rendered_guard(self, rendered: str) -> str:
        """Register (deduped) a guard from an already-rendered C bool expr."""
        if rendered not in self._guard_names:
            name = f"g{len(self._guards)}"
            self._guard_names[rendered] = name
            self._guards.append(CGuard(name=name, expr=rendered))
        return self._guard_names[rendered]

    def _guard_for(
        self, guard: syside.Expression | None, gen: CCodeGen | None = None
    ) -> str | None:
        if guard is None:
            return None
        return self._register_rendered_guard(
            (gen or self._gen).render_expression(guard)
        )

    def _register_action(
        self, statements: tuple[str | CSend, ...], id_hint: str
    ) -> str | None:
        """Register a CAction from statements; return its id or None."""
        if not statements:
            return None
        name = id_hint
        counter = 1
        while name in self._used_action_names:
            name = f"{id_hint}_{counter}"
            counter += 1
        self._used_action_names.add(name)
        self._actions.append(CAction(name=name, statements=statements))
        return name

    def _render_inline_action(
        self, a: syside.ActionUsage, gen: CCodeGen
    ) -> str | CSend:
        """Lower one inline action: a send becomes a CSend, rest goes to C."""
        if isinstance(a, syside.SendActionUsage):
            return self._csend_for(a)
        return gen.render_action(a)

    def _csend_for(self, send: syside.SendActionUsage) -> CSend:
        if not send_receiver_is_own_port(send):
            raise UnsupportedConstructError(
                "statix only supports `send` to the machine's own port "
                "(an internal self-event); sending to another part is not "
                "supported yet."
            )
        try:
            event_name, pairs = payload_signature(send)
        except ValueError as exc:
            raise UnsupportedConstructError(
                f"unsupported send payload: {exc}"
            ) from exc
        value_expr = (
            self._marshal_expr(event_name, pairs)
            if event_name in self._payload_reads
            else None  # unread event: drop raw args without rendering them
        )
        self._events.setdefault(event_name, None)
        self._has_send = True
        result = CSend(event=event_name, value_expr=value_expr)
        self._sends.append(result)
        return result

    def _marshal_expr(
        self,
        event_name: str,
        pairs: list[tuple[str, syside.Expression]],
    ) -> str:
        """Render the marshalled Real expression for a read event, or reject.

        `path` is the event's read path (from `_detect_payload_reads`):
        either one segment (position-0 case) or exactly two (one composite
        hop then a Real leaf, e.g. `.sample.value`). `payload_signature`
        binds constructor arguments positionally; the argument matching
        `path[0]` is the one that must supply the read value, whichever
        position it sits at -- any other argument is unread and is never
        rendered.
        """
        path = self._payload_reads[event_name]
        match = next((p for p in pairs if p[0] == path[0]), None)
        if match is None:
            raise UnsupportedConstructError(
                f"the payload of event {event_name!r} is read as "
                f".{'.'.join(path)}; no `send` constructor argument is "
                f"bound to attribute {path[0]!r}."
            )
        expr = match[1]
        if len(path) == 1:
            if isinstance(expr, syside.LiteralRational):
                return repr(expr.value)
            if isinstance(expr, syside.FeatureReferenceExpression):
                ref = expr.referent
                if ref is not None and ref.name in self._real_attribute_names:
                    return f"ctx->{ref.name}"
            raise UnsupportedConstructError(
                f"the marshalled payload of event {event_name!r} must be "
                "provably Real: a Real literal or a Real machine attribute; "
                "other expressions are unsupported by statix yet."
            )
        # len(path) == 2: the matched argument must be a bare reference to a
        # registered composite attribute; mechanically resolve path[1]
        # against its fields (never a vibe check -- the field's generated C
        # type comes from the struct registry built from the model's own
        # composite attribute defs).
        base_error = UnsupportedConstructError(
            f"the payload of event {event_name!r} is read as "
            f".{'.'.join(path)}; the matching `send` argument "
            f"({path[0]!r}) must be a bare reference to a composite "
            "machine attribute."
        )
        if not isinstance(expr, syside.FeatureReferenceExpression):
            raise base_error
        ref = expr.referent
        if ref is None or ref.name is None:
            raise base_error
        base_type = self._attribute_c_types.get(ref.name)
        struct = None if base_type is None else self._structs.get(base_type)
        if struct is None:
            raise base_error
        field = next((f for f in struct.fields if f.name == path[1]), None)
        if field is None or field.c_type != "double":
            raise UnsupportedConstructError(
                f"the payload of event {event_name!r} is read as "
                f".{'.'.join(path)}, but {base_type}.{path[1]!r} is not a "
                "Real (double) field."
            )
        return f"ctx->{ref.name}.{path[1]}"

    def _action_for(
        self,
        action: syside.ActionUsage | None,
        id_hint: str,
        gen: CCodeGen | None = None,
    ) -> str | None:
        statements = tuple(
            self._render_inline_action(a, gen or self._gen)
            for a in actions.inline_actions(action)
        )
        return self._register_action(statements, id_hint)

    def _entry_action_id(self, fact: StateFact, stem: str) -> str | None:
        """Build state entry action, fusing one-shot inline ``do`` after it.

        SysML ``do`` has no separate runtime slot; like quake, statix runs it
        once at entry by appending its statements after the entry statements. A
        ``do`` that references another action or holds non-``assign``/``send``
        bodies is rejected; a ``do send`` lowers like any other send
        (an internal self-event).
        """
        statements = [
            self._render_inline_action(a, self._gen)
            for a in actions.inline_actions(fact.entry_action)
        ]
        if fact.do_action is not None:
            actions.require_inline_one_shot(fact.do_action)
            statements += [
                self._render_inline_action(a, self._gen)
                for a in actions.inline_actions(fact.do_action)
            ]
        return self._register_action(tuple(statements), f"{stem}_entry")


def build_statix(model: syside.Model, state_def_qn: str) -> CProgram:
    """Build a C statechart program from a SysML state definition."""
    result = StateMachineDriver(model).run(
        state_def_qn, StatixBuilder(state_def_qn)
    )
    assert isinstance(result, CProgram)
    return result


def build_statix_project(
    model: syside.Model, state_def_qns: tuple[str, ...]
) -> CProject:
    """Build a statix C project from several state definitions."""
    programs = tuple(build_statix(model, qn) for qn in state_def_qns)
    prefixes = [program.prefix for program in programs]
    if len(set(prefixes)) != len(prefixes):
        raise UnsupportedConstructError(
            "two state definitions produce the same C prefix; rename or "
            "repackage one of them before building a combined statix project."
        )
    return CProject(programs=programs)
