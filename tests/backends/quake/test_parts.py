from __future__ import annotations

from pathlib import Path

import pytest

from sysmlc.backends.quake.coordinator import PartSystemCoordinator
from sysmlc.backends.quake.parts import QuakePartSystem, build_part_system
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.loading import load_model
from tests.backends.test_sm_examples import SM_EXAMPLES_DIR

FIX = SM_EXAMPLES_DIR / "part01-two-parts"
MUX = SM_EXAMPLES_DIR / "part-mux"
MULTI = SM_EXAMPLES_DIR / "part-multi-exhibit"
UNDECLARED_VIA = SM_EXAMPLES_DIR / "part-undeclared-via"
FANIN = Path(__file__).resolve().parents[1] / ("rosetta/fixtures/part-fanin")


def test_build_part_system_composes_two_parts() -> None:
    system = build_part_system(load_model(FIX), "Part01::pingSystem")

    assert isinstance(system, QuakePartSystem)
    assert set(system.statecharts) == {"Plant", "Tester"}
    instances = {
        (node.usage_name, node.definition_name) for node in system.graph.parts
    }
    assert instances == {("plant", "Plant"), ("tb", "Tester")}
    routes = {
        (route.source, route.source_port, route.signal, route.target)
        for route in system.routes
    }
    assert routes == {
        ("tb", "commPort", "Ping", "plant"),
        ("plant", "commPort", "Pong", "tb"),
    }


def test_routing_is_port_based_not_name_based() -> None:
    system = build_part_system(load_model(MUX), "PartMux::mux")

    routes = {
        (route.source, route.source_port, route.signal, route.target)
        for route in system.routes
    }
    assert ("hub", "a", "M", "s1") in routes
    assert ("hub", "b", "M", "s2") not in routes


def test_undeclared_via_port_is_rejected() -> None:
    model = load_model(UNDECLARED_VIA)
    with pytest.raises(UnsupportedConstructError, match="does not declare"):
        build_part_system(model, "PartUV::sys")


def test_single_channel_fan_in_is_rejected() -> None:
    model = load_model(FANIN)
    with pytest.raises(UnsupportedConstructError, match="multiplicity"):
        build_part_system(model, "PartFanin::sys")


def test_multi_exhibit_part_is_rejected() -> None:
    model = load_model(MULTI)
    with pytest.raises(UnsupportedConstructError, match="exactly one exhibit"):
        build_part_system(model, "PartMulti::sys")


def test_coordinator_routes_without_sender_self_copy() -> None:
    system = build_part_system(load_model(FIX), "Part01::pingSystem")
    coordinator = PartSystemCoordinator(system)

    trace = coordinator.run(max_steps=50)

    consumed = [
        (entry.instance, entry.step.event.name)
        for entry in trace
        if entry.step.event is not None
    ]
    assert ("plant", "Ping") in consumed
    assert ("tb", "Pong") in consumed
    assert ("tb", "Ping") not in consumed
    assert ("plant", "Pong") not in consumed
    assert coordinator.clock.time == 0.1
    assert coordinator.interpreters["tb"].final
    assert coordinator.interpreters["plant"].configuration == [
        "PlantBehavior",
        "idle",
    ]


def test_coordinator_drains_cross_machine_cascade_at_one_time() -> None:
    system = build_part_system(load_model(FIX), "Part01::pingSystem")
    coordinator = PartSystemCoordinator(system)

    trace = coordinator.run(max_steps=50)

    routed_times = [
        entry.step.time
        for entry in trace
        if entry.step.event is not None
        and entry.step.event.name in {"Ping", "Pong"}
    ]
    assert routed_times == [0.1, 0.1]
