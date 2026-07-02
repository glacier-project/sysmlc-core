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
    """A compiled multi-machine quake artifact."""

    name: str
    graph: PartGraph
    statecharts: dict[str, Statechart]
    routes: tuple[PortSignalRoute, ...]

    def statechart_for_usage(self, usage_name: str) -> Statechart:
        """Return the statechart backing the part usage ``usage_name``."""
        for node in self.graph.parts:
            if node.usage_name == usage_name:
                return self.statecharts[node.definition_name]
        raise KeyError(usage_name)


def build_part_system(model: syside.Model, usage_qn: str) -> QuakePartSystem:
    """Build a quake part-system artifact for a top-level part usage."""
    graph = part_graph(model, usage_qn)
    if not graph.parts:
        raise UnsupportedConstructError(
            f"part usage {usage_qn!r} composes no parts"
        )

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

    statecharts: dict[str, Statechart] = {}
    behaviors: dict[str, str] = {}
    for node in graph.parts:
        behaviors.setdefault(node.definition_name, node.behaviors[0][1])
    for definition_name, behavior_qn in behaviors.items():
        statecharts[definition_name] = build_statechart(
            model, behavior_qn, route_via_sends=True
        )

    return QuakePartSystem(
        name=graph.name,
        graph=graph,
        statecharts=statecharts,
        routes=port_signal_routes(graph, faces),
    )
