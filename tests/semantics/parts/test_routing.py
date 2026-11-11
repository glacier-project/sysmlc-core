from __future__ import annotations

from pathlib import Path

import pytest
from sysmlc_models.sm_examples import SM_EXAMPLES_DIR

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.parts.graph import part_graph
from sysmlc.semantics.parts.routing import validated_routes
from sysmlc.sysml.loading import load_model

FIX = SM_EXAMPLES_DIR / "part01-two-parts"
MUX = SM_EXAMPLES_DIR / "part-mux"
UNDECLARED_VIA = SM_EXAMPLES_DIR / "part-undeclared-via"
FANIN = Path(__file__).resolve().parent / "fixtures" / "part-fanin"


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


TRANSPORT = """package Transport {
    item def Event;
    port def EventPort;
    interface def Link { end a : EventPort; end b : EventPort; }
    interface def DerivedLink :> Link;
    state def Source {
        port tx;
        entry; then s;
        state s { entry send new Event() via tx; }
    }
    state def Sink {
        port rx;
        entry; then s; state s;
        transition first s accept Event via rx then s;
    }
    part def Sender {
        port tx : EventPort;
        port spare : EventPort;
        exhibit state : Source;
    }
    part def Receiver {
        port rx : EventPort;
        port spare : EventPort;
        exhibit state : Sink;
    }
    part system {
        part sender : Sender;
        part receiver : Receiver;
        RELATIONSHIPS
    }
}"""


@pytest.mark.parametrize(
    "relationship",
    [
        "interface sender.tx to receiver.rx;",
        "interface c : Link connect sender.tx to receiver.rx;",
        "connection c : Link connect sender.tx to receiver.rx;",
        "connection c : DerivedLink connect sender.tx to receiver.rx;",
    ],
)
def test_resolved_interface_forms_deliver(
    tmp_path: Path, relationship: str
) -> None:
    from tests import _load_inline_model

    model = _load_inline_model(
        tmp_path, TRANSPORT.replace("RELATIONSHIPS", relationship)
    )
    graph = part_graph(model, "Transport::system")
    assert graph.interfaces == ((("sender", "tx"), ("receiver", "rx")),)
    _, routes = validated_routes(model, graph, graph.parts)
    assert [
        (r.source, r.source_port, r.signal, r.target, r.target_port)
        for r in routes
    ] == [("sender", "tx", "Event", "receiver", "rx")]


@pytest.mark.parametrize(
    "relationship",
    [
        "connect sender.tx to receiver.rx;",
        "connect sender to receiver;",
        "connect sender.tx to receiver;",
        "connect sender.spare to receiver.spare;",
    ],
)
def test_generic_connections_do_not_route(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, relationship: str
) -> None:
    from tests import _load_inline_model

    model = _load_inline_model(
        tmp_path, TRANSPORT.replace("RELATIONSHIPS", relationship)
    )
    graph = part_graph(model, "Transport::system")
    assert graph.interfaces == ()
    assert validated_routes(model, graph, graph.parts)[1] == ()
    assert (
        "part 'sender' sends 'Event' via 'tx' but no connected peer "
        "accepts it; the signal is never delivered"
    ) in caplog.text


def test_structural_link_alongside_interface_is_legal(tmp_path: Path) -> None:
    from tests import _load_inline_model

    model = _load_inline_model(
        tmp_path,
        TRANSPORT.replace(
            "RELATIONSHIPS",
            """connect sender to receiver;
            connect sender.tx to receiver;
            connect receiver.rx to sender.tx;
            interface sender.tx to receiver.rx;""",
        ),
    )
    graph = part_graph(model, "Transport::system")
    assert len(graph.interfaces) == 1
    _, routes = validated_routes(model, graph, graph.parts)
    assert [(r.signal, r.target) for r in routes] == [("Event", "receiver")]
