from __future__ import annotations

import re
from typing import Final, NamedTuple

import syside

from sysmlc.backends.statix.codegen import CCodeGen
from sysmlc.backends.statix.payload import _walk_payload_fields
from sysmlc.backends.statix.program import (
    COMPLETION_EVENT,
    INTERNAL_TARGET,
    TIMEOUT_EVENT,
    CAction,
    CContext,
    CEnum,
    CExternFunction,
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
from sysmlc.semantics.statemachine import attributes as attributes_mod
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
from sysmlc.sysml.queries import feature_value

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


_NATIVE_ENUM_KINDS: Final[dict[type, str]] = {
    syside.LiteralBoolean: "bool",
    syside.LiteralInteger: "int32_t",
    syside.LiteralRational: "double",
}

_ALLOWED_ENUM_LITERAL_KINDS: Final[tuple[type, ...]] = (
    syside.LiteralBoolean,
    syside.LiteralInteger,
    syside.LiteralRational,
    syside.LiteralString,
)


def _enumeration_is_structured(
    definition: syside.EnumerationDefinition,
) -> bool:
    """Whether an enum def carries attribute features.

    Mirrors quake's own ``_enumeration_is_structured`` exactly
    (``sysmlc/backends/quake/codegen.py``): a plain or value-typed
    enumeration inherits only its implicit ``self`` feature; a structured
    enumeration (one that specializes an attribute definition) inherits
    named attribute usages, whose per-literal ``:>>`` redefinitions cannot
    be projected to a single primitive value.
    """
    return any(
        isinstance(f, syside.AttributeUsage)
        for f in definition.features.collect()
    )


def _render_native_enum_literal(value: syside.Expression | None) -> str:
    if isinstance(value, syside.LiteralBoolean):
        return "true" if value.value else "false"
    if isinstance(value, syside.LiteralInteger):
        return str(value.value)
    if isinstance(value, syside.LiteralRational):
        return repr(value.value)
    raise UnsupportedConstructError(
        "internal error: a native-classified enum literal has no "
        "renderable declared value"
    )


class _EnumProjection(NamedTuple):
    """Cached classification outcome for one enum definition.

    ``enum`` is ``None`` for a native Boolean/Integer/Real projection
    (``c_type`` is then the native scalar name); otherwise it is the emitted
    :class:`CEnum` and ``c_type`` is its C type name (``f"{enum.base}_t"``).
    ``constants`` maps each literal's simple name to its generated constant
    name; empty for the native case (a native literal renders its own declared
    value instead of a constant name).

    """

    c_type: str
    enum: CEnum | None
    constants: dict[str, str]


def _references_payload_feature(
    expr: syside.Expression, feature: syside.Feature
) -> bool:
    """Pre-pass helper: returns True if expr references the payload feature."""
    if (
        isinstance(expr, syside.FeatureReferenceExpression)
        and expr.referent == feature
    ):
        return True
    children: list[syside.Expression] = []
    if hasattr(expr, "operands"):
        children.extend(
            op
            for op in expr.operands.collect()
            if isinstance(op, syside.Expression)
        )
    if hasattr(expr, "owned_elements"):
        children.extend(
            elem
            for elem in expr.owned_elements.collect()
            if isinstance(elem, syside.Expression)
        )
    return any(
        _references_payload_feature(child, feature) for child in children
    )


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
        self._externs: dict[str, CExternFunction] = {}
        self._whole_payload_struct_types: set[str] = set()
        self._compiler: syside.Compiler | None = None
        self._stdlib: syside.Stdlib | None = None
        # Guard/action codegen is re-created in result() once the attribute
        # names are known; the init codegen never sees a context pointer.
        self._gen = CCodeGen(
            enum_resolver=self._resolve_enum_literal,
            extern_resolver=self._resolve_extern_call,
        )
        self._init_gen = CCodeGen(
            allow_context=False,
            enum_resolver=self._resolve_enum_literal,
            extern_resolver=self._resolve_extern_call,
        )
        self._root: StateFact | None = None
        self._state_facts: list[StateFact] = []
        self._transition_facts: list[TransitionFact] = []
        self._bindings: list[AttributeBinding] = []
        self._guard_names: dict[tuple[str | None, str], str] = {}
        self._guards: list[CGuard] = []
        self._actions: list[CAction] = []
        self._used_action_names: set[str] = set()
        self._events: dict[str, None] = {}
        self._structs: dict[str, CStruct] = {}
        self._enum_cache: dict[
            syside.EnumerationDefinition, _EnumProjection
        ] = {}
        self._enum_names: dict[str, syside.EnumerationDefinition] = {}
        self._enums: dict[str, CEnum] = {}
        self._finals: dict[str, CState] = {}
        self._constraints: list[ConstraintFact] = []
        self._has_send = False
        self._sends: list[CSend] = []
        self._referenced_payload_events: set[str] = set()
        self._scoped_gens: list[CCodeGen] = []
        self._real_attribute_names: frozenset[str] = frozenset()
        self._attribute_names: frozenset[str] = frozenset()
        self._attribute_c_types: dict[str, str] = {}
        self._state_kinds: dict[str, StateKind] = {}
        self._timeouts: list[CTimeout] = []
        self._timeout_sources: set[str] = set()
        self._has_timer = False
        self._timeouts_use_ctx = False
        self._when_slot_by_fact: dict[int, int] = {}
        self._when_arms_by_source: dict[str, list[int]] = {}
        self._when_count = 0
        self._has_when = False
        self._slots: dict[str, int] = {}
        self._region_roots: dict[str, list[str]] = {}
        self._regions_flat: list[str] = []
        self._active_capacity = 1

    def set_compiler_context(
        self, compiler: syside.Compiler, stdlib: syside.Stdlib
    ) -> None:
        """Give this builder access to the driver's own compiler/stdlib.

        Needed only for default-value materialization of a payload type's
        omitted constructor arguments (KerML 8.3.4.8.7 permits fewer
        arguments than attributes) -- reuses attributes.bind_value, the
        exact function driver.py's own _bind_attributes already uses for a
        machine's context attributes. `StatixBuilder` otherwise has no
        compiler/stdlib access (it is constructed from a bare qualified
        name); this is a lightweight, optional setter rather than a
        constructor change, so existing tests that construct a
        `StatixBuilder` directly (bypassing the driver) are unaffected.
        """
        self._compiler = compiler
        self._stdlib = stdlib

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
        if state.kind is StateKind.FINAL:
            raise UnsupportedConstructError(
                f"state {state.name!r} is {state.kind.name}; statix supports "
                "composite, leaf, and parallel states only (history not yet "
                "supported)."
            )
        self._reject_nested_parallel_state(state)
        self._state_kinds[state.name] = state.kind
        self._state_facts.append(state)

    def add_transition(self, transition: TransitionFact) -> None:
        """Buffer a transition fact (emitted in :meth:`result`)."""
        self._transition_facts.append(transition)

    def _assign_when_slots(self) -> None:
        """Pre-pass: assign each `when` trigger a project-wide slot index.

        Must run before `_build_state` (a source state's entry action needs
        its arm statements) and before `_build_transition` (which looks up
        each fact's pre-assigned slot by identity). No dedup even if two
        triggers share a textual condition: each occurrence is its own
        independent observation (`MachineWhenTwo`).
        """
        for t in self._transition_facts:
            if not isinstance(t.trigger, WhenTrigger):
                continue
            if self._state_kinds.get(t.source) in (
                StateKind.COMPOSITE,
                StateKind.PARALLEL,
            ):
                raise UnsupportedConstructError(
                    f"state {t.source!r} has a change-triggered transition, "
                    "but it is a composite or parallel (non-leaf) state; "
                    "statix only supports `when` sourced from a leaf state."
                )
            if isinstance(t.target, str) and t.target == t.source:
                raise UnsupportedConstructError(
                    f"state {t.source!r}'s change trigger targets itself; "
                    "statix rejects `when` self-loops."
                )
            self._has_when = True
            slot = self._when_count
            self._when_count += 1
            self._when_slot_by_fact[id(t)] = slot
            self._when_arms_by_source.setdefault(t.source, []).append(slot)

    def result(self) -> CProgram:
        """Assemble and return the C statechart program."""
        root = self._root
        if root is None:
            raise UnsupportedConstructError(
                "statix requires a composite or parallel root state with "
                "substates."
            )
        if root.kind not in (StateKind.COMPOSITE, StateKind.PARALLEL):
            raise UnsupportedConstructError(
                "the state definition declares no substates."
            )
        self._reject_machine_level_actions(root)
        facts_by_name = self._facts_by_name()
        self._reject_nested_parallel(facts_by_name)
        self._assign_activation_layout(facts_by_name)
        root_state: CState | None = None
        if root.kind is StateKind.PARALLEL:
            region_names = self._region_roots[root.name]
            root_state = CState(
                name=root.name,
                entry_action_id=None,
                exit_action_id=None,
                parent=None,
                initial_child=None,
                slot=self._slots[root.name],
                region_first=len(self._regions_flat),
                region_count=len(region_names),
            )
            self._regions_flat.extend(region_names)
        context_fields = tuple(
            self._field(binding) for binding in self._bindings
        )
        self._real_attribute_names = frozenset(
            f.name for f in context_fields if f.c_type == "double"
        )
        self._attribute_names = frozenset(f.name for f in context_fields)
        self._attribute_c_types = {f.name: f.c_type for f in context_fields}
        struct_field_types = self._struct_field_types()
        self._gen = CCodeGen(
            attribute_names=self._attribute_names,
            real_attributes=self._real_attribute_names,
            enum_resolver=self._resolve_enum_literal,
            extern_resolver=self._resolve_extern_call,
            attribute_c_types=self._attribute_c_types,
            struct_field_types=struct_field_types,
            structs_by_name=self._structs,
            generated_enum_types=self._generated_enum_type_names(),
        )
        self._referenced_payload_events = self._detect_payload_events()
        self._validate_referenced_payload_schemas()
        self._assign_when_slots()
        real_states = tuple(self._build_state(f) for f in self._state_facts)
        transitions = tuple(
            row
            for t in self._transition_facts
            for row in self._build_transition(t)
        )
        # Relaxed check: external payload-bearing events are allowed.
        states = (
            ((root_state,) if root_state is not None else ())
            + real_states
            + tuple(self._finals.values())
        )
        invariants = tuple(self._build_invariant(c) for c in self._constraints)
        if root.kind is StateKind.COMPOSITE:
            if root.initial_substate is None:
                raise UnsupportedConstructError(
                    "the machine declares no initial state."
                )
            assert root.initial_substate is not None
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
        assert (
            root.initial_substate is not None or root.kind is StateKind.PARALLEL
        )
        initial_substate = root.initial_substate
        if root.kind is StateKind.PARALLEL:
            initial = root.name
        else:
            assert initial_substate is not None
            initial = initial_substate
        for gen in self._scoped_gens:
            self._whole_payload_struct_types.update(gen.whole_payload_types)
        context = CContext(
            fields=context_fields, structs=tuple(self._structs.values())
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
            initial=initial,
            max_depth=max_depth,
            invariants=invariants,
            enums=tuple(self._enums.values()),
            needs_math=needs_math,
            has_send=self._has_send,
            timeouts=tuple(self._timeouts),
            has_timer=self._has_timer,
            timeouts_use_ctx=self._timeouts_use_ctx,
            has_when=self._has_when,
            when_count=self._when_count,
            regions=tuple(self._regions_flat),
            active_capacity=self._active_capacity,
            extern_functions=tuple(self._externs.values()),
            payload_struct_types=tuple(
                sorted(self._whole_payload_struct_types)
            ),
        )

    def _payload_gen(self, payload_feature: syside.Feature) -> CCodeGen:
        try:
            payload_c_type = self._resolve_extern_type(
                payload_feature, payload_feature.name or "payload"
            )
        except UnsupportedConstructError:
            # Deriving a C type eagerly would wrongly reject a named binding
            # to a type statix cannot represent (e.g. an empty/tag item like
            # SM02's `Tick`) even when the binding is never actually read in
            # a guard/effect. Defer: render with no payload C type, and let a
            # genuine whole-payload/subfield read raise its own clear error.
            payload_c_type = None
        return CCodeGen(
            attribute_names=frozenset(
                self._attribute_names | {b.name for b in self._bindings}
            ),
            real_attributes=self._real_attribute_names,
            payload_feature=payload_feature,
            payload_c_type=payload_c_type,
            enum_resolver=self._resolve_enum_literal,
            extern_resolver=self._resolve_extern_call,
            attribute_c_types=self._attribute_c_types,
            struct_field_types=self._struct_field_types(),
            structs_by_name=self._structs,
            generated_enum_types=self._generated_enum_type_names(),
        )

    def _struct_field_types(self) -> dict[str, dict[str, str]]:
        return {
            name: {f.name: f.c_type for f in struct.fields}
            for name, struct in self._structs.items()
        }

    def _generated_enum_type_names(self) -> frozenset[str]:
        return frozenset(f"{e.base}_t" for e in self._enums.values())

    def _detect_payload_events(self) -> set[str]:
        """Detect all events whose payload features are actually read.

        Renders each transition's guard and effect assignments to discover
        if the payload feature is referenced. If it is, the event uses payload
        encoding (so sends of this event must marshal and include payload bytes).
        Otherwise, if the payload feature is named but never read, the event
        stays payload-less (an id-only event).
        """
        payload_events: set[str] = set()
        for t in self._transition_facts:
            trigger = t.trigger
            if (
                not isinstance(trigger, SignalTrigger)
                or trigger.payload_feature is None
            ):
                continue
            feature = trigger.payload_feature
            has_ref = False
            if t.guard is not None and _references_payload_feature(
                t.guard, feature
            ):
                has_ref = True
            if not has_ref:
                for a in actions.inline_actions(t.effect):
                    if (
                        isinstance(a, syside.AssignmentActionUsage)
                        and a.value_expression is not None
                        and _references_payload_feature(
                            a.value_expression, feature
                        )
                    ):
                        has_ref = True
                        break
            if has_ref:
                payload_events.add(trigger.signal_name)
        return payload_events

    def _validate_referenced_payload_schemas(self) -> None:
        """Every REFERENCED event's full declared payload type must be representable.

        Not just the specific field(s) some transition
        happens to read. Every leaf crosses the wire together (Task 3's
        whole-struct transfer), so an unrepresentable sibling field breaks
        the transfer even if it's never itself read. An unreferenced event
        is never checked here (an id-only accept of a type statix cannot
        fully represent must still build, per the SM02 lazy-resolution fix).
        """
        checked: set[str] = set()
        for t in self._transition_facts:
            trigger = t.trigger
            if (
                not isinstance(trigger, SignalTrigger)
                or trigger.payload_feature is None
                or trigger.signal_name not in self._referenced_payload_events
                or trigger.signal_name in checked
            ):
                continue
            checked.add(trigger.signal_name)
            payload_c_type = self._resolve_extern_type(
                trigger.payload_feature,
                trigger.payload_feature.name or "payload",
            )
            leaf_paths = _walk_payload_fields(payload_c_type, self._structs)
            if not leaf_paths:
                raise UnsupportedConstructError(
                    f"event {trigger.signal_name!r} uses an empty "
                    "composite payload; a referenced payload requires at "
                    "least one leaf."
                )

    def _facts_by_name(self) -> dict[str, StateFact]:
        assert self._root is not None
        out: dict[str, StateFact] = {self._root.name: self._root}
        for fact in self._state_facts:
            out[fact.name] = fact
        return out

    def _reject_nested_parallel_state(self, state: StateFact) -> None:
        if state.kind is not StateKind.PARALLEL:
            return
        facts = {f.name: f for f in self._state_facts}
        if self._root is not None:
            facts[self._root.name] = self._root
        parent = state.parent
        ancestor = facts.get(parent) if parent is not None else None
        while ancestor is not None:
            if ancestor.kind is StateKind.PARALLEL:
                raise UnsupportedConstructError(
                    f"state {state.name!r} is parallel and nested inside "
                    f"another parallel state {ancestor.name!r}; statix "
                    "supports at most one fork level (no nested "
                    "parallel regions yet)."
                )
            parent = ancestor.parent
            ancestor = facts.get(parent) if parent is not None else None

    def _reject_nested_parallel(
        self, facts_by_name: dict[str, StateFact]
    ) -> None:
        """Reject a PARALLEL state with a PARALLEL ancestor (design Sec.1).

        Walks every PARALLEL fact's full ancestor chain (via `.parent` names,
        including the root); the statix-parallel-regions-design.md dispatch
        algorithm and join intrinsic both assume at most one fork level.
        """
        for fact in self._state_facts:
            if fact.kind is not StateKind.PARALLEL:
                continue
            parent = fact.parent
            ancestor = facts_by_name.get(parent) if parent is not None else None
            while ancestor is not None:
                if ancestor.kind is StateKind.PARALLEL:
                    raise UnsupportedConstructError(
                        f"state {fact.name!r} is parallel and nested inside "
                        f"another parallel state {ancestor.name!r}; statix "
                        "supports at most one fork level (no nested "
                        "parallel regions yet)."
                    )
                parent = ancestor.parent
                ancestor = (
                    facts_by_name.get(parent) if parent is not None else None
                )

    def _assign_activation_layout(
        self, facts_by_name: dict[str, StateFact]
    ) -> None:
        """Recursive capacity/slot allocation (design Sec.3.2).

        Composite children share a slot base (mutually exclusive, only one
        active at a time); a parallel state's regions get disjoint,
        concatenated ranges (simultaneously active). Populates
        self._slots (state name -> activation slot), self._region_roots
        (parallel state name -> ordered list of its region-root names), and
        self._active_capacity (the whole machine's max concurrent leaf
        count). Build-time Python recursion over the driver's small,
        statically-bounded state tree -- never touches the runtime's
        no-recursion rule (design Sec.10).
        """
        assert self._root is not None
        children: dict[str, list[StateFact]] = {}
        for fact in self._state_facts:
            if fact.parent is not None:
                children.setdefault(fact.parent, []).append(fact)

        def cap(name: str) -> int:
            fact = facts_by_name[name]
            kids = children.get(name, [])
            if fact.kind is StateKind.PARALLEL:
                return sum(cap(c.name) for c in kids)
            if kids:
                return max(cap(c.name) for c in kids)
            return 1

        def assign(name: str, base: int) -> None:
            self._slots[name] = base
            fact = facts_by_name[name]
            kids = children.get(name, [])
            if fact.kind is StateKind.PARALLEL:
                self._region_roots[name] = [c.name for c in kids]
                offset = base
                for c in kids:
                    assign(c.name, offset)
                    offset += cap(c.name)
            else:
                for c in kids:
                    assign(c.name, base)

        self._slots = {}
        self._region_roots = {}
        root_name = self._root.name
        self._active_capacity = cap(root_name)
        assign(root_name, 0)

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
        if (
            value is None
            and isinstance(
                binding.type_definition,
                (syside.AttributeDefinition, syside.ItemDefinition),
            )
            and binding.type_definition.owned_attributes.collect()
        ):
            c_type = self._register_struct_from_definition(
                binding.type_definition
            )
            return CField(
                binding.name, c_type, self._scalar_init(value, c_type)
            )
        c_type = self._scalar_c_type(value, binding.name, binding.type_name)
        return CField(binding.name, c_type, self._scalar_init(value, c_type))

    def _scalar_c_type(
        self, value: AttributeValue, name: str, type_name: str | None = None
    ) -> str:
        if isinstance(value, float):
            return "double"
        if isinstance(value, syside.LiteralBoolean):
            return "bool"
        if isinstance(value, syside.LiteralInteger):
            return "int32_t"
        if isinstance(value, syside.LiteralRational):
            return "double"
        if isinstance(value, syside.FeatureReferenceExpression) and isinstance(
            value.referent, syside.EnumerationUsage
        ):
            c_type, _rendered, _is_generated = self._resolve_enum_literal(
                value.referent
            )
            return c_type
        if value is None and type_name is not None:
            if type_name == "Integer":
                return "int32_t"
            if type_name == "Real":
                return "double"
            if type_name == "Boolean":
                return "bool"
            if type_name == "String":
                return "const char*"
            c_type = f"{self._prefix}_{_c_identifier(type_name)}_t"
            if c_type in self._structs:
                return c_type
        raise UnsupportedConstructError(
            f"attribute {name!r} has no scalar literal default; statix "
            "iteration 1 infers a C type from a Boolean/Integer/Real literal "
            "initializer (or a composite attribute def)."
        )

    def _scalar_init(self, value: AttributeValue, c_type: str) -> str:
        if value is None:
            if c_type == "int32_t":
                return "0"
            if c_type == "double":
                return "0.0"
            if c_type == "bool":
                return "false"
            if c_type == "const char*":
                return '""'
            if c_type in self._structs:
                return "{0}"
        if isinstance(value, float):
            return repr(value) if c_type == "double" else str(int(value))
        assert not isinstance(value, CompositeValue) and value is not None
        return self._init_gen.render_expression(value)

    def _resolve_extern_call(
        self, expr: syside.InvocationExpression, gen: CCodeGen
    ) -> str | None:
        """Recognize a bodyless calc def (a pure signature) as an extern C call.

        A calc def WITH a body (result_expression is not None) is a different,
        larger future feature (compiling an actual expression body to C) and is
        left to fall through to the existing allowlist-or-reject path.

        `gen` is the SPECIFIC CCodeGen instance currently rendering `expr` (see
        codegen.py's _emit_invocation) -- arguments are rendered through it, not
        through a fixed instance, so context-initializer call sites (where a
        different CCodeGen with allow_context=False is active) render correctly.
        """
        func = expr.function
        if not isinstance(
            func, (syside.CalculationDefinition, syside.CalculationUsage)
        ):
            return None
        if func.result_expression is not None:
            return None
        qn = str(func.qualified_name)
        if qn not in self._externs:
            c_name = _c_prefix(qn)
            param_types: list[str] = []
            param_names: list[str] = []
            for param in func.inputs.collect():
                assert param.name is not None
                param_names.append(param.name)
                param_types.append(self._resolve_extern_type(param, param.name))
            if func.result is None:
                return_type = "void"
            else:
                return_type = self._resolve_extern_type(func.result, "return")
            self._externs[qn] = CExternFunction(
                name=qn,
                c_name=c_name,
                param_types=tuple(param_types),
                param_names=tuple(param_names),
                return_type=return_type,
            )
        fn = self._externs[qn]
        args = ", ".join(gen._emit(a, 0) for a in expr.arguments.collect())
        return f"{fn.c_name}({args})"

    def _resolve_extern_type(self, param: syside.Feature, name: str) -> str:
        """Resolve a calc parameter's/result's declared type to a C type.

        Mirrors driver.py's _bind_attributes type_name derivation exactly (the
        first named attribute_definitions() entry), then reuses _scalar_c_type's
        existing "no value, just a type name" branch for scalars, or registers a
        type-only struct for a composite (attribute-def) type.
        """
        defs_iterator = getattr(
            param, "attribute_definitions", None
        ) or getattr(param, "definitions", None)
        definition = (
            next(
                (
                    d
                    for d in defs_iterator.collect()
                    if getattr(d, "name", None)
                ),
                None,
            )
            if defs_iterator is not None
            else None
        )
        if definition is None:
            raise UnsupportedConstructError(
                f"calc parameter/result {name!r} has no resolvable type; statix "
                "cannot derive an extern C signature for it.",
                node=param,
            )
        type_name = definition.name
        assert type_name is not None
        if type_name in ("Integer", "Real", "Boolean", "String"):
            return self._scalar_c_type(None, name, type_name)
        if (
            isinstance(
                definition, (syside.AttributeDefinition, syside.ItemDefinition)
            )
            and definition.owned_attributes.collect()
        ):
            return self._register_struct_from_definition(definition)
        raise UnsupportedConstructError(
            f"calc parameter/result {name!r} has type {type_name!r}, which is "
            "neither a scalar (Integer/Real/Boolean/String) nor a structured "
            "attribute or item definition; statix cannot derive an extern C "
            "signature for it.",
            node=param,
        )

    def _register_struct_from_definition(
        self, definition: syside.AttributeDefinition | syside.ItemDefinition
    ) -> str:
        """Type-only counterpart to _register_struct.

        No bound value exists for
        a calc parameter (it's a bare type reference), so this walks the
        definition's OWN declared fields (each resolved via the same
        attribute_definitions() pattern, recursively) instead of a CompositeValue.

        Uses the IDENTICAL naming formula as _register_struct so a type already
        registered via an actual attribute binding (e.g. PendulumState via
        `attribute x : PendulumState`) is found and reused here, not duplicated.
        """
        assert definition.name is not None
        c_type = f"{self._prefix}_{_c_identifier(definition.name)}_t"
        if c_type in self._structs:
            return c_type
        fields: list[CField] = []
        for field in definition.owned_attributes.collect():
            assert field.name is not None
            field_type = self._resolve_extern_type(field, field.name)
            fields.append(CField(field.name, field_type, ""))
        self._structs[c_type] = CStruct(name=c_type, fields=tuple(fields))
        return c_type

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

    def _resolve_enum_literal(
        self, literal: syside.EnumerationUsage
    ) -> tuple[str, str, bool]:
        """Resolve one enum-literal reference: (c_type, rendered, is_generated).

        The single entry point every ``CCodeGen`` instance calls back into
        (via the ``enum_resolver`` hook) and that ``_scalar_c_type`` also
        calls directly for an attribute default's own type. Classification
        of the owning definition happens at most once (cached in
        ``self._enum_cache``), the first time any of its literals is seen.
        """
        owner = literal.owner
        if not isinstance(owner, syside.EnumerationDefinition):
            raise UnsupportedConstructError(
                "enum literal is not owned by an enumeration definition",
                node=literal,
            )
        projection = self._enum_cache.get(owner)
        if projection is None:
            projection = self._classify_enum(owner)
            self._enum_cache[owner] = projection
        assert literal.name is not None
        if projection.enum is None:
            value = feature_value(literal)
            return projection.c_type, _render_native_enum_literal(value), False
        return projection.c_type, projection.constants[literal.name], True

    def _classify_enum(
        self, owner: syside.EnumerationDefinition
    ) -> _EnumProjection:
        if _enumeration_is_structured(owner):
            raise UnsupportedConstructError(
                f"enumeration {owner.name!r} is structured (its literals "
                "carry attribute values); statix does not support "
                "structured enumerations.",
                node=owner,
            )
        assert owner.name is not None
        base = f"{self._prefix}_enum_{_c_identifier(owner.name)}"
        known_owner = self._enum_names.get(base)
        if known_owner is not None and known_owner is not owner:
            raise UnsupportedConstructError(
                f"enum definitions {known_owner.name!r} and {owner.name!r} "
                f"both sanitize to {base!r} after C-identifier "
                "sanitization; rename one.",
                node=owner,
            )
        self._enum_names[base] = owner
        members = [
            m
            for m in owner.owned_members.collect()
            if isinstance(m, syside.EnumerationUsage)
        ]
        values = [(m, feature_value(m)) for m in members]
        non_none = [(m, v) for m, v in values if v is not None]
        if not non_none:
            return self._build_generated_enum(base, members)
        if len(non_none) != len(values):
            raise UnsupportedConstructError(
                f"enumeration {owner.name!r}: some literals declare a "
                "value and some do not; every literal must share one "
                "declared-value kind, or none may declare one.",
                node=owner,
            )
        for m, v in non_none:
            if not isinstance(v, _ALLOWED_ENUM_LITERAL_KINDS):
                raise UnsupportedConstructError(
                    f"enumeration {owner.name!r}, literal {m.name!r}: "
                    "declared value is not a bare Boolean/Integer/Real/"
                    "String literal (e.g. a computed expression); only "
                    "bare literal defaults are supported.",
                    node=m,
                )
        kinds = {type(v) for _, v in non_none}
        if len(kinds) != 1:
            raise UnsupportedConstructError(
                f"enumeration {owner.name!r}: declared values mix "
                "different literal kinds; every literal must share one "
                "declared-value kind.",
                node=owner,
            )
        kind = next(iter(kinds))
        if kind is syside.LiteralString:
            return self._build_generated_enum(base, members)
        return _EnumProjection(
            c_type=_NATIVE_ENUM_KINDS[kind], enum=None, constants={}
        )

    def _build_generated_enum(
        self, base: str, members: list[syside.EnumerationUsage]
    ) -> _EnumProjection:
        constants: dict[str, str] = {}
        literals: list[str] = []
        for m in members:
            assert m.name is not None
            const = f"{base.upper()}_{_c_identifier(m.name).upper()}"
            constants[m.name] = const
            literals.append(const)
        enum = CEnum(base=base, literals=tuple(literals))
        self._enums[base] = enum
        return _EnumProjection(
            c_type=f"{base}_t", enum=enum, constants=constants
        )

    # -- states / transitions --

    def _build_state(self, fact: StateFact) -> CState:
        # Display name is the driver's root-relative dotted path; the C
        # identifier is derived from it by the serializer.
        name = fact.name
        stem = _c_identifier(name)
        root_name = self._root.name if self._root is not None else None
        is_root_parallel = (
            self._root is not None and self._root.kind is StateKind.PARALLEL
        )
        parent = (
            None
            if (fact.parent == root_name and not is_root_parallel)
            else fact.parent
        )
        region_first: int | None = None
        region_count = 0
        if fact.kind is StateKind.PARALLEL:
            region_names = self._region_roots[name]
            region_first = len(self._regions_flat)
            region_count = len(region_names)
            self._regions_flat.extend(region_names)
        return CState(
            name=name,
            entry_action_id=self._entry_action_id(fact, stem),
            exit_action_id=self._action_for(fact.exit_action, f"{stem}_exit"),
            parent=parent,
            initial_child=fact.initial_substate,
            slot=self._slots[name],
            region_first=region_first,
            region_count=region_count,
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
                slot=self._slots.get(scope, 0),
            )
        return name

    def _build_transition(self, t: TransitionFact) -> tuple[CTransition, ...]:
        if isinstance(t.trigger, WhenTrigger):
            return self._build_when_transitions(t)
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
        return (CTransition(source, event, guard, action, target),)

    def _build_when_transitions(
        self, t: TransitionFact
    ) -> tuple[CTransition, ...]:
        """Lower one `accept when <cond> [if <guard>]` into 1 or 2 rows.

        The real transition's guard conjoins the armed-slot check, the
        watched condition, and (if present) the user's own `if`. A false
        `if` at delivery needs a second, internal "consumer" transition (no
        target) that disarms the slot with a *negated* copy of the user
        guard -- emitted only when a user `if` is present, since with none
        the real guard alone fully disposes of the observation.
        """
        assert isinstance(t.trigger, WhenTrigger)
        slot = self._when_slot_by_fact[id(t)]
        armed = f"runtime->when_armed[{slot}]"
        cond = self._gen.render_expression(t.trigger.condition)
        source = t.source
        if isinstance(t.target, CompletionTarget):
            target = self._final_for(t.target.scope)
        else:
            target = t.target
        action = self._action_for(
            t.effect, f"{_c_identifier(source)}_when{slot}_effect"
        )
        if t.guard is None:
            real_guard = self._register_rendered_guard(f"{armed} && ({cond})")
            real = CTransition(
                source, COMPLETION_EVENT, real_guard, action, target
            )
            return (real,)
        user_if = self._gen.render_expression(t.guard)
        real_guard = self._register_rendered_guard(
            f"{armed} && ({cond}) && ({user_if})"
        )
        real = CTransition(source, COMPLETION_EVENT, real_guard, action, target)
        consumer_guard = self._register_rendered_guard(
            f"{armed} && ({cond}) && !({user_if})"
        )
        consumer_action = self._register_action(
            (f"{armed} = false;",),
            f"{_c_identifier(source)}_when{slot}_consume",
        )
        consumer = CTransition(
            source,
            COMPLETION_EVENT,
            consumer_guard,
            consumer_action,
            INTERNAL_TARGET,
        )
        return (real, consumer)

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
        raise UnsupportedConstructError(
            f"unsupported trigger: {type(trigger).__name__}"
        )

    def _register_timeout(
        self, source: str, trigger: AfterTrigger | AtTrigger
    ) -> str:
        """Build (or reject) the CTimeout row for one after/at transition."""
        if self._state_kinds.get(source) in (
            StateKind.COMPOSITE,
            StateKind.PARALLEL,
        ):
            raise UnsupportedConstructError(
                f"state {source!r} has a time-triggered transition, but it "
                "is a composite or parallel (non-leaf) state; statix only "
                "supports after/at sourced from a leaf state."
            )
        if source in self._timeout_sources:
            raise UnsupportedConstructError(
                f"state {source!r} already has a time-triggered transition; "
                "at most one after/at is supported per state by statix yet."
            )
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

    def _register_rendered_guard(
        self,
        rendered: str,
        preamble: tuple[str, ...] = (),
        payload_c_type: str | None = None,
    ) -> str:
        """Register (deduped) a guard from an already-rendered C bool expr.

        Deduped on (payload_c_type, rendered), not rendered text alone: once
        a guard's boolean expression can be preceded by a payload-decode
        preamble tied to a specific struct type, two guards with identical
        trailing text but different payload types must never merge --
        preamble is fully determined by payload_c_type, so it need not be
        part of the key separately.
        """
        key = (payload_c_type, rendered)
        if key not in self._guard_names:
            name = f"g{len(self._guards)}"
            self._guard_names[key] = name
            self._guards.append(
                CGuard(name=name, expr=rendered, preamble=preamble)
            )
        return self._guard_names[key]

    def _guard_for(
        self, guard: syside.Expression | None, gen: CCodeGen | None = None
    ) -> str | None:
        if guard is None:
            return None
        active_gen = gen or self._gen
        rendered = active_gen.render_expression(guard)
        preamble = tuple(active_gen.payload_preamble)
        payload_c_type = active_gen._payload_c_type if preamble else None
        return self._register_rendered_guard(rendered, preamble, payload_c_type)

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
        payload_lines: tuple[str, ...] = ()
        if event_name in self._referenced_payload_events:
            payload_lines = self._marshal_payload(send, event_name, pairs)
        self._events.setdefault(event_name, None)
        self._has_send = True
        result = CSend(event=event_name, payload_lines=payload_lines)
        self._sends.append(result)
        return result

    def _marshal_payload(
        self,
        send: syside.SendActionUsage,
        event_name: str,
        pairs: list[tuple[str, syside.Expression]],
    ) -> tuple[str, ...]:
        """Render a payload-bearing send: zero-init, assign each leaf, send.

        Every payload-bearing send renders through this one path regardless
        of which subset of fields any transition actually reads (receive
        always decodes the whole struct). Each leaf gets its own assignment
        statement against a zero-initialized local -- never a single
        aggregate literal naming every field, which C does not guarantee
        zeroes padding (the "remainder is implicitly zeroed" rule applies
        only to unlisted members). Zero-init once, then one plain scalar
        assignment per leaf (which only ever touches its own member's
        bytes), keeps padding deterministic through the whole sequence.
        """
        payload = send.payload_argument
        assert isinstance(payload, syside.ConstructorExpression)
        event_type = payload.instantiated_type
        assert isinstance(event_type, syside.Definition)
        attributes = event_type.owned_attributes.collect()
        bound = dict(pairs)
        payload_c_type = self._register_whole_payload_type(
            event_type, event_name
        )
        self._whole_payload_struct_types.add(payload_c_type)
        leaf_paths = _walk_payload_fields(payload_c_type, self._structs)
        if not leaf_paths:
            raise UnsupportedConstructError(
                f"event {event_name!r} uses an empty composite payload; "
                "a payload-bearing send requires at least one leaf."
            )
        assignments = self._render_leaf_assignments(
            leaf_paths, attributes, bound
        )
        return (
            f"{payload_c_type} sc__value = {{0}};",
            *assignments,
            "sc_status_t send_status = sc_runtime_enqueue_payload(",
            "    runtime, (sc_event_id_t)__EVENT_TOKEN__,",
            "    &sc__value, sizeof(sc__value));",
            "if (send_status != SC_STATUS_OK) {",
            "    return send_status;",
            "}",
        )

    def _render_leaf_assignments(
        self,
        leaf_paths: list[tuple[str, ...]],
        attributes: list[syside.AttributeUsage],
        bound: dict[str, syside.Expression],
    ) -> tuple[str, ...]:
        """One `sc__value.<path> = <expr>;` statement per payload leaf.

        For each top-level attribute (bound by the send's constructor
        arguments, or defaulted via KerML's fewer-args-than-attributes
        rule), walks down to each of ITS OWN leaf paths and renders the
        exact matching sub-expression.
        """
        attrs_by_name = {a.name: a for a in attributes}
        lines: list[str] = []
        for path in leaf_paths:
            top_name = path[0]
            sub_path = path[1:]
            if top_name in bound:
                rhs = self._render_bound_leaf(bound[top_name], sub_path)
            else:
                attr = attrs_by_name[top_name]
                assert self._compiler is not None and self._stdlib is not None
                value = attributes_mod.bind_value(
                    attr, self._compiler, self._stdlib
                )
                rhs = self._render_default_leaf(value, sub_path)
            lines.append(f"sc__value.{'.'.join(path)} = {rhs};")
        return tuple(lines)

    def _render_bound_leaf(
        self, expr: syside.Expression, sub_path: tuple[str, ...]
    ) -> str:
        """Render the leaf value at `sub_path` within a bound constructor arg.

        `sub_path` empty means the bound expression itself IS the leaf
        (rendered exactly as any other bound scalar expression). A non-empty
        `sub_path` means the top-level attribute is composite: the bound
        expression must be a bare reference to a composite machine
        attribute, so `sub_path` can be mechanically resolved against it --
        never a vibe check, this only ever emits `ctx->` accesses the
        attribute registry can already prove exist.
        """
        if not sub_path:
            return self._gen.render_expression(expr)
        if not isinstance(expr, syside.FeatureReferenceExpression):
            raise UnsupportedConstructError(
                f"the payload leaf '.{'.'.join(sub_path)}' of a composite "
                "send argument must be a bare reference to a composite "
                "machine attribute; statix cannot resolve a leaf field of "
                "an inline constructor or computed expression."
            )
        ref = expr.referent
        if ref is None or ref.name is None:
            raise UnsupportedConstructError(
                "send argument has no resolved referent"
            )
        return "ctx->" + ref.name + "." + ".".join(sub_path)

    def _render_default_leaf(
        self, value: AttributeValue, sub_path: tuple[str, ...]
    ) -> str:
        """Render the leaf value at `sub_path` within a materialized default."""
        current: AttributeValue = value
        for name in sub_path:
            assert isinstance(current, CompositeValue)
            current = next(v for n, v in current.fields if n == name)
        if isinstance(current, CompositeValue):
            raise UnsupportedConstructError(
                "internal error: a payload leaf path resolved to a "
                "composite default value"
            )
        if isinstance(current, float):
            return repr(current)
        assert current is not None
        return self._init_gen.render_expression(current)

    def _register_whole_payload_type(
        self, event_type: syside.Definition, event_name: str
    ) -> str:
        assert event_type.name is not None
        c_type = f"{self._prefix}_{_c_identifier(event_type.name)}_t"
        if c_type not in self._structs:
            fields: list[CField] = []
            for attr in event_type.owned_attributes.collect():
                assert attr.name is not None
                field_type = self._resolve_extern_type(attr, attr.name)
                fields.append(CField(attr.name, field_type, ""))
            self._structs[c_type] = CStruct(name=c_type, fields=tuple(fields))
        return c_type

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

        Arming statements for any `when`-triggered transitions sourced at
        this state are appended last, after entry/`do` -- matching quake's
        own "armed last: durations must see the values entry/do just
        assigned" convention (quake/builder.py:379). Both orders are
        behaviorally equivalent in this runtime (guard evaluation only ever
        happens after the whole entry action returns), but arm-last keeps
        the two backends' generated order identical.
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
        statements += [
            f"runtime->when_armed[{slot}] = true;"
            for slot in self._when_arms_by_source.get(fact.name, [])
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
