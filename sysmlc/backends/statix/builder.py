from __future__ import annotations

import re

import syside

from sysmlc.backends.statix.codegen import CCodeGen
from sysmlc.backends.statix.program import (
    COMPLETION_EVENT,
    CAction,
    CContext,
    CField,
    CGuard,
    CProgram,
    CState,
    CStruct,
    CTransition,
)
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

_DEFAULT_QUEUE_CAPACITY = 8


def _c_identifier(name: str) -> str:
    """Sanitize a SysML name into a lowercase C identifier."""
    ident = re.sub(r"[^0-9a-zA-Z_]", "_", name).lower()
    return ident or "machine"


def _simple(path: str) -> str:
    """The last ``::`` segment of a state path."""
    return path.rpartition("::")[2]


class StatixBuilder:
    """Assemble a flat C statechart (:class:`CProgram`) from neutral facts.

    Implements ``TargetBuilder``. Every C representational choice lives here:
    leaf states become an enum + a per-state entry/exit table; eventless
    transitions carry :data:`COMPLETION_EVENT`; signal triggers become events;
    guards/effects/attributes lower via :class:`CCodeGen` into a generated
    context struct. Hierarchy, parallel, history, timers, ``after``/``at``/
    ``when``, ``send``, ``then done``, and non-scalar/non-composite attributes
    are rejected loudly.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._prefix = _c_identifier(name)
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
        """Reject asserted constraints (unsupported in iteration 1)."""
        raise UnsupportedConstructError(
            "asserted constraints are not supported by statix yet."
        )

    def add_state(self, state: StateFact) -> None:
        """Buffer a leaf state; the root is remembered, non-leaves rejected."""
        if state.parent is None:
            self._root = state
            return
        if state.kind is not StateKind.LEAF:
            raise UnsupportedConstructError(
                f"state {state.name!r} is {state.kind.name}; statix supports "
                "flat machines with leaf states only (no hierarchy/parallel)."
            )
        self._state_facts.append(state)

    def add_transition(self, transition: TransitionFact) -> None:
        """Buffer a transition fact (emitted in :meth:`result`)."""
        self._transition_facts.append(transition)

    def result(self) -> CProgram:
        """Assemble and return the flat C statechart program."""
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
        self._gen = CCodeGen(
            attribute_names=frozenset(f.name for f in context.fields)
        )
        states = tuple(self._build_state(f) for f in self._state_facts)
        transitions = tuple(
            self._build_transition(t) for t in self._transition_facts
        )
        if root.initial_substate is None:
            raise UnsupportedConstructError(
                "the machine declares no initial state."
            )
        return CProgram(
            name=self._name,
            prefix=self._prefix,
            states=states,
            events=tuple(self._events),
            guards=tuple(self._guards),
            actions=tuple(self._actions),
            transitions=transitions,
            context=context,
            queue_capacity=_DEFAULT_QUEUE_CAPACITY,
            initial=_simple(root.initial_substate),
        )

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
        simple = _simple(fact.name)
        return CState(
            name=simple,
            entry_action_id=self._action_for(
                fact.entry_action, f"{simple}_entry"
            ),
            exit_action_id=self._action_for(fact.exit_action, f"{simple}_exit"),
        )

    def _build_transition(self, t: TransitionFact) -> CTransition:
        if isinstance(t.target, CompletionTarget):
            raise UnsupportedConstructError(
                "`then done` completion targets are not supported by statix "
                "yet."
            )
        event = self._event_of(t.trigger)
        guard = self._guard_for(t.guard)
        source = _simple(t.source)
        label = "completion" if event == COMPLETION_EVENT else event
        action = self._action_for(t.effect, f"{source}_{label}_effect")
        return CTransition(source, event, guard, action, _simple(t.target))

    def _event_of(self, trigger: object | None) -> str:
        if trigger is None:
            return COMPLETION_EVENT
        if isinstance(trigger, SignalTrigger):
            # A bound payload name is allowed; reading its data is rejected by
            # the codegen (the payload feature is not a context attribute).
            self._events.setdefault(trigger.signal_name, None)
            return trigger.signal_name
        if isinstance(trigger, (AfterTrigger, AtTrigger, WhenTrigger)):
            raise UnsupportedConstructError(
                "time/change triggers (after/at/when) are not supported by "
                "statix yet."
            )
        raise UnsupportedConstructError(
            f"unsupported trigger: {type(trigger).__name__}"
        )

    def _guard_for(self, guard: syside.Expression | None) -> str | None:
        if guard is None:
            return None
        rendered = self._gen.render_expression(guard)
        if rendered not in self._guard_names:
            name = f"g{len(self._guards)}"
            self._guard_names[rendered] = name
            self._guards.append(CGuard(name=name, expr=rendered))
        return self._guard_names[rendered]

    def _action_for(
        self, action: syside.ActionUsage | None, id_hint: str
    ) -> str | None:
        statements = tuple(
            self._gen.render_action(a) for a in actions.inline_actions(action)
        )
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


def build_statix(model: syside.Model, state_def_qn: str) -> CProgram:
    """Build a flat C statechart program from a SysML state definition."""
    name = state_def_qn.split("::")[-1]
    result = StateMachineDriver(model).run(state_def_qn, StatixBuilder(name))
    assert isinstance(result, CProgram)
    return result
