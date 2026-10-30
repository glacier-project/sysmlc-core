"""Compile-scoped concrete signal identities and deterministic target names."""

from __future__ import annotations

import keyword
from collections import Counter
from types import MappingProxyType
from typing import TYPE_CHECKING

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine.interface import machine_interface
from sysmlc.sysml.queries import (
    definitions_of,
    iter_elements,
    structured_fields,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sysmlc.semantics.statemachine.facts import SignalTrigger

# Hex-encoded qualified identities cannot collide with preserved simple names.
_PREFIX = "_sysmlc_q_"
_RESERVED = frozenset(
    {
        "self",
        "time",
        "startup",
        "shutdown",
        "reset",
        "actions",
        "dataclass",
        "object",
        "int",
        "float",
        "str",
        "bool",
        "Enum",
        "IntEnum",
        "auto",
        "input",
        "output",
        "reaction",
        "timer",
        "state",
        "mode",
        "initial",
        "reactor",
        "method",
        "mutable",
        "physical",
        "logical",
        "preamble",
        "target",
        "const",
        "port",
        "deadline",
    }
)


def qualified_type(type_: syside.Type) -> str:
    """Return the resolved qualified identity of a named type.

    Raises:
        UnsupportedConstructError: If the type has no qualified name.
    """
    if type_.qualified_name is None:
        raise UnsupportedConstructError(
            "signal type has no qualified name", node=type_
        )
    return str(type_.qualified_name)


def _symbols(types: Iterable[syside.Type]) -> Mapping[str, str]:
    definitions = {qualified_type(t): t for t in types}
    counts = Counter(t.name for t in definitions.values())
    result = {}
    for qn, type_ in sorted(definitions.items()):
        name = type_.name
        if (
            name
            and name.isascii()
            and name.isidentifier()
            and not keyword.iskeyword(name)
            and name not in _RESERVED
            and not name.startswith("_")
            and counts[name] == 1
        ):
            result[qn] = name
        else:
            result[qn] = _PREFIX + qn.encode("utf-8").hex()
    return MappingProxyType(result)


class SignalCatalog:
    """Freeze concrete signal channels and generated definition symbols.

    Accept constraints are conjunctive and use Syside conformance. The universe
    includes concrete application definitions, including library packages, and
    explicitly referenced definitions. Standard-library types are included only
    when referenced explicitly. Class symbols have their own frozen namespace,
    shared with enumeration definitions, independently of event channel names.
    """

    def __init__(
        self, model: syside.Model, state_def_qns: Sequence[str]
    ) -> None:
        accepts: list[tuple[syside.Type, ...]] = []
        referenced: set[syside.Type] = set()
        for qn in dict.fromkeys(state_def_qns):
            face = machine_interface(model, qn, strict_signals=True)
            for trigger in face.accepted_triggers:
                if trigger.value_bound:
                    raise UnsupportedConstructError(
                        "value-bound signal accepts are not supported in typed dispatch"
                    )
                constraints = trigger.accepted_types
                if not constraints:
                    raise UnsupportedConstructError(
                        "untyped signal accepts are not supported in typed dispatch"
                    )
                accepts.append(constraints)
                # Subsetting-only accepts have no local explicit typing. Keep
                # their most restrictive effective types as references, without
                # turning implicit universal ancestors into concrete channels.
                declared = trigger.declared_types or tuple(
                    constraint
                    for constraint in constraints
                    if not any(
                        other.conforms(constraint)
                        and not constraint.conforms(other)
                        for other in constraints
                    )
                )
                referenced.update(declared)
            referenced.update(face.sent_types)
        application = [
            t
            for t in iter_elements(model, syside.Definition)
            if isinstance(
                t, (syside.ItemDefinition, syside.AttributeDefinition)
            )
        ]
        candidates = set(application) | referenced
        concrete = [
            t
            for t in candidates
            if not t.is_abstract
            and isinstance(
                t, (syside.ItemDefinition, syside.AttributeDefinition)
            )
            and (
                t in referenced
                or any(
                    all(t.conforms(c) for c in constraints)
                    for constraints in accepts
                )
            )
        ]
        self._types = {
            qualified_type(t): t for t in sorted(concrete, key=qualified_type)
        }
        self.qualified_channels = _symbols(concrete)
        # Walk only value definitions and their nested value-field types.
        # Unrelated state/action definitions do not occupy the Python namespace.
        symbol_types = set(application) | referenced
        pending = list(symbol_types)
        while pending:
            definition = pending.pop()
            for attribute in structured_fields(definition):
                for nested in definitions_of(attribute):
                    if (
                        isinstance(
                            nested,
                            (syside.ItemDefinition, syside.AttributeDefinition),
                        )
                        and nested not in symbol_types
                    ):
                        symbol_types.add(nested)
                        pending.append(nested)
        self.definition_symbols = _symbols(symbol_types)

    def channel_for(self, type_: syside.Type) -> str:
        """Return the concrete type's channel.

        Raises:
            UnsupportedConstructError: If the type is outside the catalog.
        """
        qn = qualified_type(type_)
        try:
            return self.qualified_channels[qn]
        except KeyError as error:
            raise UnsupportedConstructError(
                f"signal type {qn!r} is outside the concrete catalog",
                node=type_,
            ) from error

    def definition_for(self, channel: str) -> syside.Definition:
        """Return the concrete definition identified by a catalog channel.

        Raises:
            ValueError: If the channel is not in this catalog.
        """
        for qn, known in self.qualified_channels.items():
            if known == channel:
                return self._types[qn]
        raise ValueError(f"unknown concrete signal channel {channel!r}")

    def matching_channels(self, trigger: SignalTrigger) -> frozenset[str]:
        """Return concrete channels satisfying every effective accept type.

        Raises:
            UnsupportedConstructError: If the accept is untyped/value-bound.
        """
        constraints = trigger.accepted_types or (
            (trigger.accepted_type,)
            if trigger.accepted_type is not None
            else ()
        )
        if trigger.value_bound or not constraints:
            raise UnsupportedConstructError(
                "typed dispatch requires nonempty type constraints and no payload value binding"
            )
        return frozenset(
            self.qualified_channels[qn]
            for qn, t in self._types.items()
            if all(t.conforms(c) for c in constraints)
        )

    def resolve_external(self, name: str) -> str:
        """Resolve a qualified identity or unambiguous simple external name.

        Raises:
            ValueError: If the name is unknown or ambiguous.
        """
        if name in self.qualified_channels:
            return self.qualified_channels[name]
        matches = [
            self.qualified_channels[qn]
            for qn, t in self._types.items()
            if t.name == name
        ]
        if len(matches) != 1:
            raise ValueError(
                f"external signal name {name!r} is unknown or ambiguous; use a qualified type name"
            )
        return matches[0]
