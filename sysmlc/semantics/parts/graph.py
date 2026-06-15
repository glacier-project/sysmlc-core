"""Extract a SysML part graph into backend-neutral data.

Walks a top-level part *usage* and records its nested parts (each typed by a
``part def`` that inlines one or more ``exhibit state`` members), the declared
ports of each part, and the explicit ``connect`` edges as port pairs. The part
assembler consumes this to emit one reactor per part def plus a ``main
reactor`` wiring them through their connected ports (see ``parts/__init__``
for the verified syside accessors).
"""

from __future__ import annotations

from dataclasses import dataclass

import syside

from sysmlc.errors import UnsupportedConstructError

# A connection end is ``(instance usage name, port name)``; a connection is a
# pair of ends.
type Endpoint = tuple[str, str]
type Connection = tuple[Endpoint, Endpoint]


@dataclass(frozen=True)
class PartNode:
    """One nested part: its usage name, its def, behaviors, and ports."""

    usage_name: str  # e.g. "plant"
    definition_name: str  # e.g. "Plant" (-> reactor class name)
    behaviors: tuple[tuple[str, str], ...]  # ((exhibit_name, behavior_qn), ...)
    ports: tuple[str, ...]  # the part def's declared port names


@dataclass(frozen=True)
class PartGraph:
    """A top-level part usage decomposed into parts + connections."""

    name: str  # top-level usage simple name (-> main reactor)
    parts: tuple[PartNode, ...]
    connections: tuple[Connection, ...]


def part_graph(model: syside.Model, usage_qn: str) -> PartGraph:
    """Extract the part graph rooted at the top-level usage ``usage_qn``."""
    system = _resolve_part_usage(model, usage_qn)
    model_defs = {
        str(sd.qualified_name)
        for sd in model.elements(
            syside.StateDefinition,
            include_subtypes=True,
            considered_document_kinds=syside.DocumentKind.MODEL,
        )
    }
    parts: list[PartNode] = []
    connections: list[Connection] = []
    for feature in system.owned_features.collect():
        # NB: transitions create ``SuccessionAsUsage`` (a sibling
        # ConnectorAsUsage); match ``ConnectionUsage`` exactly to exclude it.
        if isinstance(feature, syside.ConnectionUsage):
            connections.append(_connection(feature))
        elif isinstance(feature, syside.PartUsage):
            parts.append(_part_node(feature, model_defs))
    return PartGraph(
        name=usage_qn.split("::")[-1],
        parts=tuple(parts),
        connections=tuple(connections),
    )


def _resolve_part_usage(model: syside.Model, usage_qn: str) -> syside.PartUsage:
    for usage in model.elements(
        syside.PartUsage,
        include_subtypes=True,
        considered_document_kinds=syside.DocumentKind.MODEL,
    ):
        if usage.matches_qualified_name(usage_qn.split("::")):
            return usage
    raise ValueError(f"part usage {usage_qn!r} not found")


def _part_node(usage: syside.PartUsage, model_defs: set[str]) -> PartNode:
    usage_name = usage.name or "<anonymous>"
    typings = usage.owned_typings.collect()
    if not typings:
        raise UnsupportedConstructError(
            f"part {usage_name!r} declares no definition; type it with "
            "`: <PartDef>`"
        )
    definition = typings[0].type
    if not isinstance(definition, syside.PartDefinition):
        raise UnsupportedConstructError(
            f"part {usage_name!r} is not typed by a part definition"
        )
    members = definition.owned_members.collect()
    ports = tuple(
        m.name for m in members if isinstance(m, syside.PortUsage) and m.name
    )
    exhibits = [m for m in members if isinstance(m, syside.ExhibitStateUsage)]
    if not exhibits:
        raise UnsupportedConstructError(
            f"part def {definition.name!r} has no exhibit; pure composite "
            "parts (0 exhibits) are not supported in this increment"
        )
    multi = len(exhibits) > 1
    if multi and any(e.name is None for e in exhibits):
        raise UnsupportedConstructError(
            f"part def {definition.name!r} has {len(exhibits)} exhibits but "
            "one or more exhibits have no usage name; a multi-exhibit part "
            "def must name each exhibit (e.g. `exhibit state plant : P;`)"
        )
    def_name = definition.name or "<anonymous>"
    behaviors: tuple[tuple[str, str], ...] = tuple(
        (
            exhibit.name if exhibit.name is not None else def_name,
            _exhibited_behavior(exhibit, definition, model_defs),
        )
        for exhibit in exhibits
    )
    return PartNode(
        usage_name=usage_name,
        definition_name=definition.name or "<anonymous>",
        behaviors=behaviors,
        ports=ports,
    )


def _exhibited_behavior(
    exhibit: syside.ExhibitStateUsage,
    definition: syside.PartDefinition,
    model_defs: set[str],
) -> str:
    # state_definitions returns the bound state def PLUS library supertypes;
    # keep only model-declared StateDefinitions (expect exactly one).
    declared = [
        sd
        for sd in exhibit.state_definitions.collect()
        if isinstance(sd, syside.StateDefinition)
        and str(sd.qualified_name) in model_defs
    ]
    if len(declared) != 1:
        raise UnsupportedConstructError(
            f"exhibit in part def {definition.name!r} resolves "
            f"{len(declared)} model-declared state defs; it must be typed "
            "by exactly one"
        )
    return str(declared[0].qualified_name)


def _connection(conn: syside.ConnectionUsage) -> Connection:
    ends = conn.connector_ends.collect()
    if len(ends) != 2:
        raise UnsupportedConstructError(
            f"connection has {len(ends)} ends; exactly two are required"
        )
    return (_endpoint(ends[0]), _endpoint(ends[1]))


def _endpoint(end: syside.Feature) -> Endpoint:
    subsetting = end.owned_reference_subsetting
    if subsetting is None:
        raise UnsupportedConstructError(
            "a connection end has no reference subsetting (`<part>.<port>`)"
        )
    feature = subsetting.general
    if not isinstance(feature, syside.Feature):
        raise UnsupportedConstructError(
            "a connection end does not resolve to a chained feature"
        )
    chain = feature.chaining_features.collect()
    if len(chain) < 2:
        raise UnsupportedConstructError(
            "a connection end must chain `<part>.<port>`"
        )
    instance = chain[0].name
    port = chain[-1].name
    if instance is None or port is None:
        raise UnsupportedConstructError(
            "a connection end references an unnamed part or port"
        )
    return (instance, port)
