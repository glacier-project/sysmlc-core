"""Extract a SysML part graph into backend-neutral data.

Walks a top-level part usage and records its nested behavioral parts, ports,
and resolved interfaces as port pairs. Generic structural connections are
ignored; they never establish signal routes.
"""

from __future__ import annotations

from dataclasses import dataclass

import syside

from sysmlc.errors import UnsupportedConstructError

# An interface endpoint is ``(instance usage name, port name)``.
type Endpoint = tuple[str, str]
type InterfacePair = tuple[Endpoint, Endpoint]


@dataclass(frozen=True)
class PartNode:
    """One nested part: its usage name, its def, behaviors, and ports."""

    usage_name: str  # e.g. "plant"
    definition_name: str  # e.g. "Plant" (-> reactor class name)
    behaviors: tuple[tuple[str, str], ...]  # ((exhibit_name, behavior_qn), ...)
    ports: tuple[str, ...]  # the part def's declared port names


@dataclass(frozen=True)
class PartGraph:
    """A top-level part usage decomposed into behavioral parts and links.

    Attributes:
        interfaces: Resolved interface endpoint pairs for signal routing.
    """

    name: str  # top-level usage simple name (-> main reactor)
    parts: tuple[PartNode, ...]
    interfaces: tuple[InterfacePair, ...]


def part_graph(model: syside.Model, usage_qn: str) -> PartGraph:
    """Extract the part graph rooted at the top-level usage ``usage_qn``.

    Raises:
        ValueError: If ``usage_qn`` does not name a part usage in the model.
        UnsupportedConstructError: If the usage composes no parts, or a
            composed part or interface has a shape the extractor does
            not support.
    """
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
    interfaces: list[InterfacePair] = []
    for feature in system.owned_features.collect():
        # NB: transitions create ``SuccessionAsUsage`` (a sibling
        # ConnectorAsUsage); match ``ConnectionUsage`` exactly to exclude it.
        if isinstance(feature, syside.ConnectionUsage):
            pair = _interface_pair(feature)
            if pair is not None:
                interfaces.append(pair)
        elif isinstance(feature, syside.PartUsage):
            parts.append(_part_node(feature, model_defs))
    if not parts:
        raise UnsupportedConstructError(
            f"part usage {usage_qn!r} composes no parts"
        )
    return PartGraph(
        name=usage_qn.split("::")[-1],
        parts=tuple(parts),
        interfaces=tuple(interfaces),
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


def _interface_pair(conn: syside.ConnectionUsage) -> InterfacePair | None:
    """Extract a port pair only for a resolved interface relationship.

    Args:
        conn: Resolved connection or interface usage to classify.

    Returns:
        The interface endpoint pair, or None for a generic connection.

    Raises:
        UnsupportedConstructError: If an interface does not have exactly two
            named part-port endpoints.
    """
    if not isinstance(conn, syside.InterfaceUsage) and not any(
        definition.specializes(("Interfaces", "Interface"))
        for definition in conn.connection_definitions.collect()
    ):
        return None
    ends = conn.related_features.collect()
    if len(ends) != 2:
        raise UnsupportedConstructError(
            f"interface has {len(ends)} ends; exactly two are required"
        )
    first, second = (_port_endpoint(end) for end in ends)
    if first is None or second is None:
        raise UnsupportedConstructError(
            "an interface end must reference exactly a named `<part>.<port>` "
            "whose endpoint is a port"
        )
    return (first, second)


def _port_endpoint(feature: syside.Feature) -> Endpoint | None:
    chain = feature.chaining_features.collect()
    if (
        len(chain) != 2
        or not isinstance(chain[0], syside.PartUsage)
        or not isinstance(chain[-1], syside.PortUsage)
    ):
        return None
    instance = chain[0].name
    port = chain[-1].name
    if instance is None or port is None:
        return None
    return (instance, port)
