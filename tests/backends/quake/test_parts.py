from __future__ import annotations

from pathlib import Path

import pytest

from sysmlc.backends.quake.coordinator import PartSystemCoordinator
from sysmlc.backends.quake.parts import QuakePartSystem, build_part_system
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.loading import load_model
from tests import _load_inline_model
from tests.backends.test_sm_examples import SM_EXAMPLES_DIR

FIX = SM_EXAMPLES_DIR / "part01-two-parts"
MUX = SM_EXAMPLES_DIR / "part-mux"
MULTI = SM_EXAMPLES_DIR / "part-multi-exhibit"
UNDECLARED_VIA = SM_EXAMPLES_DIR / "part-undeclared-via"
EXTERNAL = SM_EXAMPLES_DIR / "part-external"
FANIN = Path(__file__).resolve().parents[1] / ("rosetta/fixtures/part-fanin")


def test_build_part_system_composes_two_parts() -> None:
    system = build_part_system(load_model(FIX), "Part01::pingSystem")

    assert isinstance(system, QuakePartSystem)
    assert set(system.statecharts) == {"plant", "tb"}
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


def test_build_part_system_threads_external_functions() -> None:
    system = build_part_system(
        load_model(EXTERNAL),
        "PartExt::counterSystem",
        external=("ext", frozenset({"bump"})),
    )

    counter = system.statecharts["c"]
    assert "from ext import bump" in counter.preamble.splitlines()
    ticking = [t for t in counter.transitions if t.source == "ticking"]
    assert [t.action for t in ticking] == ["x = bump(x)"]


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

    trace, _ = coordinator.run(max_steps=50)

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

    trace, _ = coordinator.run(max_steps=50)

    routed_times = [
        entry.step.time
        for entry in trace
        if entry.step.event is not None
        and entry.step.event.name in {"Ping", "Pong"}
    ]
    assert routed_times == [0.1, 0.1]


TWINS_MODEL = """
package PkgA {
    state def MotorBehavior {
        entry; then spinning;
        state spinning;
    }
    part def Motor { exhibit state : MotorBehavior; }
}
package PkgB {
    state def MotorBehavior {
        entry; then humming;
        state humming;
    }
    part def Motor { exhibit state : MotorBehavior; }
}
package PartTwins {
    part sys {
        part a : PkgA::Motor;
        part b : PkgB::Motor;
    }
}
"""

SHARED_DEF_MODEL = """
package PartShared {
    state def CounterBehavior {
        entry; then idle;
        state idle;
    }
    part def Counter { exhibit state : CounterBehavior; }
    part sys {
        part a : Counter;
        part b : Counter;
    }
}
"""

ANONYMOUS_MODEL = """
package PartAnon {
    state def Behavior {
        entry; then idle;
        state idle;
    }
    part def A { exhibit state : Behavior; }
    part sys {
        part : A;
        part : A;
    }
}
"""


def test_same_named_defs_get_distinct_statecharts(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, TWINS_MODEL)

    system = build_part_system(model, "PartTwins::sys")

    assert system.statecharts["a"] is not system.statecharts["b"]
    assert "spinning" in system.statecharts["a"].states
    assert "humming" not in system.statecharts["a"].states
    assert "humming" in system.statecharts["b"].states


def test_usages_sharing_a_definition_share_one_statechart(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, SHARED_DEF_MODEL)

    system = build_part_system(model, "PartShared::sys")

    assert system.statecharts["a"] is system.statecharts["b"]


def test_duplicate_usage_names_are_rejected(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, ANONYMOUS_MODEL)

    with pytest.raises(UnsupportedConstructError, match="uniquely named"):
        build_part_system(model, "PartAnon::sys")
