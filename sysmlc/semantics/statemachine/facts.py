from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import syside


class StateKind(Enum):
    """Structural classification of a SysML state node."""

    COMPOSITE = auto()
    PARALLEL = auto()
    LEAF = auto()
    FINAL = auto()


class AttributeDirection(Enum):
    """SysML feature direction of a declared attribute.

    ``NONE`` means no direction keyword was written; ``IN``/``OUT``/
    ``INOUT`` mirror the SysML ``in``/``out``/``inout`` keywords.
    """

    NONE = auto()
    IN = auto()
    OUT = auto()
    INOUT = auto()


class TriggerKind(Enum):
    """Semantic classification of a transition trigger."""

    SIGNAL = auto()
    AFTER = auto()
    AT = auto()
    WHEN = auto()


@dataclass(frozen=True)
class Trigger:
    """A transition accepter, classified by kind.

    For SIGNAL, ``signal_name`` is the accepted payload type's simple name,
    ``payload_name`` is the declared payload parameter name (``accept
    reading : Tick`` -> ``"reading"``), and ``via_port`` is the receiver
    port's simple name (``via commPort`` -> ``"commPort"``); each is ``None``
    when absent. For AFTER, ``after`` is the duration in SI seconds (float)
    or a syside attribute-reference expression node to be rendered by the
    backend.
    """

    kind: TriggerKind
    signal_name: str | None = None
    after: syside.Expression | float | None = None
    payload_name: str | None = None
    via_port: str | None = None


@dataclass(frozen=True)
class CompositeValue:
    """A structured attribute value: ordered ``(name, value)`` fields.

    ``type_name`` is the structured attribute definition's simple name and
    ``definition`` is that definition node, so the backend can render a
    named dataclass (instead of an anonymous ``SimpleNamespace``).
    """

    fields: tuple[tuple[str, AttributeValue], ...]
    type_name: str
    definition: syside.AttributeDefinition


# A neutral attribute value: a scalar expression node, an SI number, a
# structured value, or None (left unseeded).
type AttributeValue = syside.Expression | float | CompositeValue | None


@dataclass(frozen=True)
class CompletionTarget:
    """A ``then done`` target: the scope whose completion is reached.

    ``scope`` is the owning scope's state path, or ``""`` for the root state
    definition.
    """

    scope: str


@dataclass(frozen=True)
class AttributeBinding:
    """One attribute seeded into a scope, with its neutral value and direction.

    ``direction`` reflects the SysML ``in``/``out``/``inout`` keyword;
    ``AttributeDirection.NONE`` means the attribute is undirected.
    """

    scope: str
    name: str
    value: AttributeValue
    direction: AttributeDirection = AttributeDirection.NONE


@dataclass(frozen=True)
class ConstraintFact:
    """One asserted constraint, with its neutral boolean expression.

    ``scope`` is the owning scope's state path (``""`` = the root state
    def); ``name`` is the declared constraint name, or ``None`` when
    anonymous. Only ASSERTED constraints become facts: a plain
    ``constraint`` is not required to hold.
    """

    scope: str
    name: str | None
    expression: syside.Expression


@dataclass(frozen=True)
class StateFact:
    """A state, with its SysML slots delivered separately (never pre-fused)."""

    name: str
    kind: StateKind
    parent: str | None
    initial_substate: str | None
    entry_action: syside.ActionUsage | None
    do_action: syside.ActionUsage | None
    exit_action: syside.ActionUsage | None


@dataclass(frozen=True)
class TransitionFact:
    """A transition between two states (or to a scope's completion)."""

    source: str
    target: str | CompletionTarget
    trigger: Trigger | None
    guard: syside.Expression | None
    effect: syside.ActionUsage | None
