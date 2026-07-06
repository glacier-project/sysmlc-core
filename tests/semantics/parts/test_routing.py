from __future__ import annotations

from pathlib import Path

import pytest

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.parts.graph import part_graph
from sysmlc.semantics.parts.routing import validated_routes
from sysmlc.sysml.loading import load_model
from tests.backends.test_sm_examples import SM_EXAMPLES_DIR

FIX = SM_EXAMPLES_DIR / "part01-two-parts"
MUX = SM_EXAMPLES_DIR / "part-mux"
UNDECLARED_VIA = SM_EXAMPLES_DIR / "part-undeclared-via"
FANIN = Path(__file__).resolve().parents[2] / (
    "backends/rosetta/fixtures/part-fanin"
)


def test_validated_routes_match_connected_send_accept_pairs() -> None:
    model = load_model(FIX)
    graph = part_graph(model, "Part01::pingSystem")

    _faces, routes = validated_routes(model, graph, graph.parts)

    assert {
        (route.source, route.source_port, route.signal, route.target)
        for route in routes
    } == {
        ("tb", "commPort", "Ping", "plant"),
        ("plant", "commPort", "Pong", "tb"),
    }


def test_validated_routes_are_scoped_to_connected_ports() -> None:
    model = load_model(MUX)
    graph = part_graph(model, "PartMux::mux")

    _faces, routes = validated_routes(model, graph, graph.parts)
    assert {(route.source_port, route.target) for route in routes} == {
        ("a", "s1")
    }


def test_validated_routes_rejects_undeclared_part_port() -> None:
    model = load_model(UNDECLARED_VIA)
    graph = part_graph(model, "PartUV::sys")

    with pytest.raises(UnsupportedConstructError, match="does not declare"):
        validated_routes(model, graph, graph.parts)


def test_validated_routes_rejects_single_channel_fan_in() -> None:
    model = load_model(FANIN)
    graph = part_graph(model, "PartFanin::sys")

    with pytest.raises(UnsupportedConstructError, match="multiplicity"):
        validated_routes(model, graph, graph.parts)
