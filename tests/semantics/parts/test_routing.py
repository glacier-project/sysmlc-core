from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.parts.graph import PartGraph, part_graph
from sysmlc.semantics.parts.routing import (
    port_signal_routes,
    validate_via_ports,
)
from sysmlc.semantics.statemachine.interface import (
    MachineInterface,
    machine_interface,
)
from sysmlc.sysml.loading import load_model
from tests.backends.test_sm_examples import SM_EXAMPLES_DIR

if TYPE_CHECKING:
    import syside

FIX = SM_EXAMPLES_DIR / "part01-two-parts"
MUX = SM_EXAMPLES_DIR / "part-mux"
UNDECLARED_VIA = SM_EXAMPLES_DIR / "part-undeclared-via"
FANIN = Path(__file__).resolve().parents[2] / (
    "backends/rosetta/fixtures/part-fanin"
)


def _faces(
    model: syside.Model, graph: PartGraph
) -> dict[str, MachineInterface]:
    return {
        node.usage_name: machine_interface(model, node.behaviors[0][1])
        for node in graph.parts
    }


def test_port_signal_routes_match_connected_send_accept_pairs() -> None:
    model = load_model(FIX)
    graph = part_graph(model, "Part01::pingSystem")

    routes = port_signal_routes(graph, _faces(model, graph))

    assert {
        (route.source, route.source_port, route.signal, route.target)
        for route in routes
    } == {
        ("tb", "commPort", "Ping", "plant"),
        ("plant", "commPort", "Pong", "tb"),
    }


def test_port_signal_routes_are_scoped_to_connected_ports() -> None:
    model = load_model(MUX)
    graph = part_graph(model, "PartMux::mux")

    routes = port_signal_routes(graph, _faces(model, graph))
    assert {(route.source_port, route.target) for route in routes} == {
        ("a", "s1")
    }


def test_validate_via_ports_rejects_undeclared_part_port() -> None:
    model = load_model(UNDECLARED_VIA)
    graph = part_graph(model, "PartUV::sys")

    with pytest.raises(UnsupportedConstructError, match="does not declare"):
        validate_via_ports(graph.parts, _faces(model, graph))


def test_port_signal_routes_rejects_single_channel_fan_in() -> None:
    model = load_model(FANIN)
    graph = part_graph(model, "PartFanin::sys")

    with pytest.raises(UnsupportedConstructError, match="multiplicity"):
        port_signal_routes(graph, _faces(model, graph))
