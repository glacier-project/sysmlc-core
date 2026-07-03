"""Backend-neutral port routing for SysML part systems."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sysmlc.errors import UnsupportedConstructError

if TYPE_CHECKING:
    from sysmlc.semantics.parts.graph import PartGraph, PartNode
    from sysmlc.semantics.statemachine.interface import MachineInterface

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PortSignalRoute:
    """One port-addressed signal delivery edge."""

    source: str
    source_port: str
    signal: str
    target: str
    target_port: str


def validate_via_ports(
    nodes: tuple[PartNode, ...],
    faces: dict[str, MachineInterface],
) -> None:
    """Reject a behavior whose ``send/accept via P`` port is undeclared."""
    for node in nodes:
        face = faces[node.usage_name]
        declared = set(node.ports)
        used = (set(face.sent_via) | set(face.accepted_via)) - {None}
        for port in sorted(p for p in used if p is not None):
            if port not in declared:
                raise UnsupportedConstructError(
                    f"part def {node.definition_name!r} sends/accepts via "
                    f"port {port!r}, which it does not declare; declared "
                    f"ports: {sorted(declared)!r}"
                )


def validate_connections(graph: PartGraph, parts: dict[str, PartNode]) -> None:
    """Reject a ``connect`` naming an unknown part or undeclared port."""
    for (ia, pa), (ib, pb) in graph.connections:
        for inst, port in ((ia, pa), (ib, pb)):
            node = parts.get(inst)
            if node is None:
                raise UnsupportedConstructError(
                    f"connection references part {inst!r}, which is not a "
                    f"part of {graph.name!r}"
                )
            if port not in node.ports:
                raise UnsupportedConstructError(
                    f"connection references port {port!r}, which is not a "
                    f"declared port of part def {node.definition_name!r}"
                )


def port_signal_routes(
    graph: PartGraph, faces: dict[str, MachineInterface]
) -> tuple[PortSignalRoute, ...]:
    """Build port-addressed routing edges for matched send/accept signals."""
    routes: list[PortSignalRoute] = []
    destinations: dict[tuple[str, str], str] = {}

    def wire(
        source_inst: str,
        source_port: str,
        target_inst: str,
        target_port: str,
        signal: str,
    ) -> None:
        key = (target_inst, signal)
        if key in destinations:
            raise UnsupportedConstructError(
                f"signal {signal!r} has two sources "
                f"({destinations[key]!r} and {source_inst!r}) into "
                f"{target_inst!r}; single-channel fan-in is forbidden "
                "- model it with multiplicity (a bank into a multiport), "
                "which is deferred to a later increment."
            )
        destinations[key] = source_inst
        routes.append(
            PortSignalRoute(
                source=source_inst,
                source_port=source_port,
                signal=signal,
                target=target_inst,
                target_port=target_port,
            )
        )

    for (ia, pa), (ib, pb) in graph.connections:
        fa, fb = faces[ia], faces[ib]
        a_to_b = fa.sent_via.get(pa, frozenset()) & fb.accepted_via.get(
            pb, frozenset()
        )
        b_to_a = fb.sent_via.get(pb, frozenset()) & fa.accepted_via.get(
            pa, frozenset()
        )
        both = a_to_b & b_to_a
        if both:
            raise UnsupportedConstructError(
                f"signal(s) {sorted(both)!r} travel both ways over the "
                f"connection {ia}.{pa} <-> {ib}.{pb}; bidirectional "
                "same-name signals are not supported"
            )
        for signal in sorted(a_to_b):
            wire(ia, pa, ib, pb, signal)
        for signal in sorted(b_to_a):
            wire(ib, pb, ia, pa, signal)
        _warn_unwired(ia, pa, fa, fb, pb)
        _warn_unwired(ib, pb, fb, fa, pa)
    _warn_unrouted_sends(faces, routes)
    return tuple(routes)


def _warn_unwired(
    inst: str,
    port: str,
    face: MachineInterface,
    peer: MachineInterface,
    peer_port: str,
) -> None:
    """Warn when a part accepts a signal via a port the peer never sends."""
    accepted = face.accepted_via.get(port, frozenset())
    delivered = peer.sent_via.get(peer_port, frozenset())
    for signal in sorted(accepted - delivered):
        logger.warning(
            "part %r accepts %r via %r but its peer never sends it; the "
            "input port stays unwired",
            inst,
            signal,
            port,
        )


def _warn_unrouted_sends(
    faces: dict[str, MachineInterface],
    routes: list[PortSignalRoute],
) -> None:
    """Warn when a part's port-addressed send matches no route.

    Covers both an unconnected sender port and a connected peer that never
    accepts the signal; a bare ``send`` (no ``via`` port) stays local to its
    machine and is not checked.
    """
    routed = {
        (route.source, route.source_port, route.signal) for route in routes
    }
    for inst in sorted(faces):
        sent_via = faces[inst].sent_via
        for port in sorted(p for p in sent_via if p is not None):
            for signal in sorted(sent_via[port]):
                if (inst, port, signal) not in routed:
                    logger.warning(
                        "part %r sends %r via %r but no connected peer "
                        "accepts it; the signal is never delivered",
                        inst,
                        signal,
                        port,
                    )
