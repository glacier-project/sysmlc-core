"""Build quake artifacts for connected SysML part systems."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sysmlc.backends.quake.builder import build_statechart
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.parts.graph import PartGraph, part_graph
from sysmlc.semantics.parts.routing import (
    PortSignalRoute,
    port_signal_routes,
    validate_connections,
    validate_via_ports,
)
from sysmlc.semantics.statemachine.interface import machine_interface

if TYPE_CHECKING:
    import syside
    from sismic.model import Statechart


@dataclass(frozen=True)
class QuakePartSystem:
    """A compiled multi-machine quake artifact.

    Attributes:
        statecharts: The executable statechart of each part instance, keyed
            by usage name. Usages exhibiting the same behavior share one
            statechart object.
    """

    name: str
    graph: PartGraph
    statecharts: dict[str, Statechart]
    routes: tuple[PortSignalRoute, ...]


def build_part_system(
    model: syside.Model,
    usage_qn: str,
    *,
    external: tuple[str, frozenset[str]] | None = None,
) -> QuakePartSystem:
    """Build a quake part-system artifact for a top-level part usage.

    Args:
        model: Loaded syside model containing the part usage.
        usage_qn: Qualified name of the top-level part usage to build.
        external: Optional ``(module_stem, function_names)`` pair for
            external calc-def backing.

    Returns:
        A quake part-system artifact ready to feed into a coordinator.

    Raises:
        UnsupportedConstructError: If the usage composes no parts, two
            parts share a usage name, a part def does not exhibit exactly
            one state, or a connection fails routing validation.
    """
    graph = part_graph(model, usage_qn)
    if not graph.parts:
        raise UnsupportedConstructError(
            f"part usage {usage_qn!r} composes no parts"
        )

    # Keyed by usage name, so a repeated name would silently drop a machine.
    seen_usage_names: set[str] = set()
    for node in graph.parts:
        if node.usage_name in seen_usage_names:
            raise UnsupportedConstructError(
                f"part usage {usage_qn!r} composes two parts named "
                f"{node.usage_name!r}; quake part systems require uniquely "
                "named part usages"
            )
        seen_usage_names.add(node.usage_name)

    for node in graph.parts:
        if len(node.behaviors) != 1:
            raise UnsupportedConstructError(
                f"part def {node.definition_name!r} has "
                f"{len(node.behaviors)} exhibits; quake part systems require "
                "exactly one exhibit per part"
            )

    parts = {node.usage_name: node for node in graph.parts}
    faces = {
        node.usage_name: machine_interface(model, node.behaviors[0][1])
        for node in graph.parts
    }
    validate_via_ports(graph.parts, faces)
    validate_connections(graph, parts)

    built_behaviors: dict[str, Statechart] = {}
    statecharts: dict[str, Statechart] = {}
    for node in graph.parts:
        behavior_qn = node.behaviors[0][1]
        if behavior_qn not in built_behaviors:
            built_behaviors[behavior_qn] = build_statechart(
                model, behavior_qn, external=external, route_via_sends=True
            )
        statecharts[node.usage_name] = built_behaviors[behavior_qn]

    return QuakePartSystem(
        name=graph.name,
        graph=graph,
        statecharts=statecharts,
        routes=port_signal_routes(graph, faces),
    )
