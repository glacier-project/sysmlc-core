from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Python-side marker for the runtime's SC_EVENT_COMPLETION sentinel. A
# transition carrying this as its ``event`` is an eventless (completion)
# transition; the serializer emits SC_EVENT_COMPLETION for it.
COMPLETION_EVENT: Final = "__completion__"


@dataclass(frozen=True)
class CField:
    """One context-struct field: a C type and a rendered C initializer."""

    name: str
    c_type: str
    init: str


@dataclass(frozen=True)
class CStruct:
    """A named C struct generated from a composite attribute definition."""

    name: str
    fields: tuple[CField, ...]


@dataclass(frozen=True)
class CContext:
    """The generated application context: struct fields plus nested structs."""

    fields: tuple[CField, ...]
    structs: tuple[CStruct, ...]


@dataclass(frozen=True)
class CGuard:
    """A guard id backed by a rendered C boolean expression."""

    name: str
    expr: str


@dataclass(frozen=True)
class CInvariant:
    """An asserted invariant: a guard checked while its scope state is active.

    ``scope`` is the owning state's display name, or ``None`` for a root/always
    invariant. ``guard`` is a guard name into :attr:`CProgram.guards`.
    """

    scope: str | None
    guard: str


@dataclass(frozen=True)
class CAction:
    """An action id backed by rendered C statements (each ends in ';')."""

    name: str
    statements: tuple[str, ...]


@dataclass(frozen=True)
class CState:
    """A state row with optional entry/exit actions and tree links.

    ``name`` is the root-relative dotted display path (``"running::hot"``);
    ``parent``/``initial_child`` are other states' display names, or ``None``
    for a top-level state / a leaf (serialized as ``SC_STATE_INVALID``).
    ``is_final`` marks a synthesized ``then done`` final state.
    """

    name: str
    entry_action_id: str | None
    exit_action_id: str | None
    parent: str | None = None
    initial_child: str | None = None
    is_final: bool = False


@dataclass(frozen=True)
class CTransition:
    """A transition row: source/target state names, event, guard, action.

    ``event`` is a signal event name, or :data:`COMPLETION_EVENT` for an
    eventless (completion) transition. ``guard``/``action`` are guard/action
    names, or ``None`` for SC_GUARD_NONE/SC_ACTION_NONE.
    """

    source: str
    event: str
    guard: str | None
    action: str | None
    target: str


@dataclass(frozen=True)
class CProgram:
    """A complete flat C statechart artifact, before serialization."""

    name: str
    qualified_name: str
    prefix: str
    states: tuple[CState, ...]
    events: tuple[str, ...]
    guards: tuple[CGuard, ...]
    actions: tuple[CAction, ...]
    transitions: tuple[CTransition, ...]
    context: CContext
    queue_capacity: int
    initial: str
    max_depth: int = 1
    invariants: tuple[CInvariant, ...] = ()


@dataclass(frozen=True)
class CProject:
    """One generated statix project containing one or more statecharts."""

    programs: tuple[CProgram, ...]
