"""Build quake artifacts for connected SysML part systems."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sysmlc.backends.quake.builder import (
    attach_types_module,
    build_statechart,
)
from sysmlc.backends.quake.codegen import QuakeRenderNeeds
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.parts.graph import PartGraph, part_graph
from sysmlc.semantics.parts.routing import PortSignalRoute, validated_routes

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
    types_module_name: str | None = None
    types_module_lines: tuple[str, ...] = ()


def _module_stem(qualified_name: str) -> str:
    """A process-unique module stem: the full qualified name, sanitized."""
    return qualified_name.replace("::", "_")


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

    _, routes = validated_routes(model, graph, graph.parts)

    needs = QuakeRenderNeeds()
    needs.types_module = f"{_module_stem(usage_qn)}_types"
    if external is not None:
        needs.register_external(module=external[0], names=external[1])

    built_behaviors: dict[str, Statechart] = {}
    statecharts: dict[str, Statechart] = {}
    for node in graph.parts:
        behavior_qn = node.behaviors[0][1]
        if behavior_qn not in built_behaviors:
            needs.reset_call_tracking()
            built_behaviors[behavior_qn] = build_statechart(
                model,
                behavior_qn,
                external=external,
                part_system_mode=True,
                needs=needs,
            )
        statecharts[node.usage_name] = built_behaviors[behavior_qn]

    for statechart in built_behaviors.values():
        attach_types_module(statechart, needs)

    return QuakePartSystem(
        name=graph.name,
        graph=graph,
        statecharts=statecharts,
        routes=routes,
        types_module_name=needs.types_module if needs.has_types else None,
        types_module_lines=tuple(needs.companion_module_lines()),
    )
