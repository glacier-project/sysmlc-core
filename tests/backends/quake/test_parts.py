from __future__ import annotations

from pathlib import Path

import pytest

from sysmlc.backends.quake.coordinator import (
    PartSystemCoordinator,
    StopReason,
)
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


PAYLOAD_COLLISION_MODEL = """
package PartPayload {
    private import ScalarValues::*;

    item def Data {
        attribute signal : Integer;
    }

    state def SenderBehavior {
        attribute current : Integer := 7;
        port outPort;
        entry; then ready;
        state ready;
        transition first ready
            do send new Data(current) via outPort
            then done;
    }
    state def ReceiverBehavior {
        port rxPort;
        entry; then waiting;
        state waiting;
        transition first waiting accept Data via rxPort then done;
    }

    part def Sender { port outPort; exhibit state : SenderBehavior; }
    part def Receiver { port rxPort; exhibit state : ReceiverBehavior; }

    part sys {
        part tx : Sender;
        part rx : Receiver;
        connect tx.outPort to rx.rxPort;
    }
}
"""


def test_route_delivers_payload_named_like_router_params(
    tmp_path: Path,
) -> None:
    # The Data payload attribute is named "signal", clashing with the
    # router closure's own first parameter name.
    model = _load_inline_model(tmp_path, PAYLOAD_COLLISION_MODEL)
    coordinator = PartSystemCoordinator(
        build_part_system(model, "PartPayload::sys")
    )

    trace, stop_reason = coordinator.run(max_steps=20)

    consumed = [
        (entry.instance, entry.step.event.name)
        for entry in trace
        if entry.step.event is not None
    ]
    assert ("rx", "Data") in consumed
    assert stop_reason is StopReason.FINAL


STALE_TIMER_MODEL = """
package PartStale {
    private import SI::*;

    item def Go;

    state def DriverBehavior {
        port outPort;
        entry; then kick;
        state kick;
        state running;
        transition first kick
            do send new Go() via outPort
            then running;
        transition first running accept after 6 [s] then done;
    }
    state def SleeperBehavior {
        port rxPort;
        entry; then armed;
        state armed;
        state stopped;
        transition first armed accept after 5 [s] then stopped;
        transition first armed accept Go via rxPort then done;
    }

    part def Driver { port outPort; exhibit state : DriverBehavior; }
    part def Sleeper { port rxPort; exhibit state : SleeperBehavior; }

    part sys {
        part driver : Driver;
        part sleeper : Sleeper;
        connect driver.outPort to sleeper.rxPort;
    }
}
"""


def test_final_machine_is_not_polled_again(tmp_path: Path) -> None:
    # The sleeper terminates at t=0 with its 5s timer still queued (sismic
    # never cancels delayed events); the driver keeps the system running
    # until t=6, past that stale timer.
    model = _load_inline_model(tmp_path, STALE_TIMER_MODEL)
    coordinator = PartSystemCoordinator(
        build_part_system(model, "PartStale::sys")
    )

    trace, stop_reason = coordinator.run(max_steps=50)

    assert stop_reason is StopReason.FINAL
    assert coordinator.clock.time == 6.0
    sleeper_steps_after_zero = [
        entry
        for entry in trace
        if entry.instance == "sleeper" and entry.step.time > 0
    ]
    assert sleeper_steps_after_zero == []
