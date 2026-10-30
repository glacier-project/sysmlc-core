from pathlib import Path

import pytest
import syside

from sysmlc.codegen.python import PythonCodeGen
from sysmlc.codegen.structured import DataclassRegistry, register_dataclass
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine.facts import CompositeValue, SignalTrigger
from sysmlc.semantics.statemachine.interface import machine_interface
from sysmlc.semantics.statemachine.signals import SignalCatalog
from sysmlc.sysml.queries import resolve
from tests import _load_inline_model

SOURCE = """package Signals {
    abstract item def Base { attribute value : ScalarValues::Integer; }
    item def Left :> Base;
    item def Right :> Base;
    item def Diamond :> Left, Right;
    item def External :> Diamond;
    library package Application { item def LibraryChild :> Base; }
    package Other { item def Left; }
    alias Alias for Left;
    state def Machine {
        entry; then idle;
        state idle;
        transition first idle accept payload : Base then idle;
        transition first idle accept Alias then idle;
    }
} """


def test_catalog_conformance_and_external_universe(tmp_path: Path) -> None:
    model = _load_inline_model(tmp_path, SOURCE)
    catalog = SignalCatalog(model, ["Signals::Machine"])
    base = resolve(model, syside.ItemDefinition, "Signals::Base")
    left = resolve(model, syside.ItemDefinition, "Signals::Left")
    right = resolve(model, syside.ItemDefinition, "Signals::Right")
    assert catalog.matching_channels(
        SignalTrigger("Base", accepted_type=base)
    ) == {"Left", "Right", "Diamond", "External", "LibraryChild"}
    assert catalog.matching_channels(
        SignalTrigger("Left", accepted_type=left)
    ) == {"Left", "Diamond", "External"}
    assert catalog.matching_channels(
        SignalTrigger("Both", accepted_types=(left, right))
    ) == {"Diamond", "External"}
    assert "Signals::Other::Left" not in catalog.qualified_channels
    assert not any(
        qn.startswith(("Items::", "Objects::", "Occurrences::", "Base::"))
        for qn in catalog.qualified_channels
    )
    assert catalog.resolve_external("Signals::External") == "External"
    assert catalog.definition_for("External") is resolve(
        model, syside.ItemDefinition, "Signals::External"
    )
    face = machine_interface(model, "Signals::Machine", catalog=catalog)
    assert face.accepted == {
        "Left",
        "Right",
        "Diamond",
        "External",
        "LibraryChild",
    }
    assert not face.sent
    with pytest.raises(UnsupportedConstructError, match="nonempty"):
        catalog.matching_channels(SignalTrigger("empty"))
    with pytest.raises(UnsupportedConstructError, match="payload value"):
        catalog.matching_channels(
            SignalTrigger("Base", accepted_type=base, value_bound=True)
        )


def test_qualified_channels_and_dataclass_symbols(tmp_path: Path) -> None:
    model = _load_inline_model(
        tmp_path,
        """package Names {
        package A { attribute def Data { attribute value : ScalarValues::Integer; } }
        package B { attribute def Data { attribute value : ScalarValues::Integer; } }
        package C { enum def Data { enum one; } }
        attribute def Outer { attribute nested : A::Data; }
        state def Data;
        attribute def Integer { attribute data : ScalarValues::Integer; }
        attribute def Holder { attribute typed : Integer; }
        item def Base;
        item def 'not-valid' :> Base;
        item def startup :> Base;
        item def _sysmlc_q_fake :> Base;
        state def Machine {
            entry; then idle; state idle;
            transition first idle accept A::Data then idle;
            transition first idle accept B::Data then idle;
            transition first idle accept Base then idle;
        }
    }""",
    )
    catalog = SignalCatalog(model, ["Names::Machine"])
    a = resolve(model, syside.AttributeDefinition, "Names::A::Data")
    b = resolve(model, syside.AttributeDefinition, "Names::B::Data")
    assert "Names::Data" not in catalog.definition_symbols
    assert catalog.channel_for(a) != catalog.channel_for(b)
    assert catalog.resolve_external("Names::A::Data") == catalog.channel_for(a)
    with pytest.raises(ValueError, match="ambiguous"):
        catalog.resolve_external("Data")
    assert len(set(catalog.qualified_channels.values())) == len(
        catalog.qualified_channels
    )
    assert all(
        catalog.resolve_external(n).startswith("_sysmlc_q_")
        for n in ("startup", "not-valid", "_sysmlc_q_fake")
    )
    registry = DataclassRegistry(symbols=catalog.definition_symbols)
    codegen = PythonCodeGen(definition_symbols=catalog.definition_symbols)
    for definition in (
        a,
        b,
        resolve(model, syside.AttributeDefinition, "Names::Outer"),
        resolve(model, syside.AttributeDefinition, "Names::Holder"),
    ):
        register_dataclass(definition, registry, codegen.render_expression)
    namespace = {}
    exec("\n".join(registry.module_lines()), namespace)
    symbol = registry.symbol_for(a)
    rendered = codegen.render_value(
        CompositeValue((("value", 42.0),), "Data", a)
    )
    assert rendered is not None
    value = eval(rendered, namespace)
    assert type(value).__name__ == symbol
    assert value.value == 42
    assert symbol in namespace["Outer"].__annotations__["nested"]
    integer = resolve(model, syside.AttributeDefinition, "Names::Integer")
    assert namespace["Holder"].__annotations__["typed"] == registry.symbol_for(
        integer
    )
    assert (
        namespace[registry.symbol_for(integer)].__annotations__["data"] == "int"
    )
    enum = resolve(model, syside.EnumerationDefinition, "Names::C::Data")
    assert (
        catalog.definition_symbols[str(enum.qualified_name)]
        not in registry.names()
    )


def test_effective_subsetting_and_multiple_typing(tmp_path: Path) -> None:
    model = _load_inline_model(
        tmp_path,
        """package Effective {
        item def Base;
        item def Left :> Base;
        item def Right :> Base;
        item def Both :> Left, Right;
        item msg : Left;
        state def Machine {
            entry; then idle; state idle;
            transition first idle accept x :> msg then idle;
            transition first idle accept x : Left, Right then idle;
        }
    }""",
    )
    catalog = SignalCatalog(model, ["Effective::Machine"])
    face = machine_interface(model, "Effective::Machine", catalog=catalog)
    assert face.accepted == {"Left", "Both"}


def test_value_bound_accept_is_rejected(tmp_path: Path) -> None:
    model = _load_inline_model(
        tmp_path,
        """package Bound {
        item def Event;
        item msg : Event;
        state def Machine {
            entry; then idle; state idle;
            transition first idle accept x : Event = msg then idle;
        }
    }""",
    )
    with pytest.raises(UnsupportedConstructError, match="value-bound"):
        SignalCatalog(model, ["Bound::Machine"])


def test_typed_routes_deduplicate_conforming_accepts(tmp_path: Path) -> None:
    from dataclasses import replace

    from sysmlc.semantics.parts.graph import part_graph
    from sysmlc.semantics.parts.routing import validated_routes

    model = _load_inline_model(
        tmp_path,
        """package Routes {
        item def Base;
        item def Child :> Base;
        state def Source {
            port tx;
            entry; then s;
            state s { entry send new Child() via tx; }
        }
        state def Sink {
            port rx;
            entry; then s; state s;
            transition first s accept Base via rx then s;
            transition first s accept Child via rx then s;
        }
        part def Sender { port tx; exhibit state : Source; }
        part def Receiver { port rx; exhibit state : Sink; }
        part system {
            part sender : Sender;
            part receiver : Receiver;
            connect sender.tx to receiver.rx;
        }
    }""",
    )
    graph = part_graph(model, "Routes::system")
    catalog = SignalCatalog(model, ["Routes::Source", "Routes::Sink"])
    faces, routes = validated_routes(model, graph, graph.parts, catalog=catalog)
    assert faces["receiver"].accepted == {"Base", "Child"}
    assert [(r.signal, r.target) for r in routes] == [("Child", "receiver")]
    # Repeated identical physical connection is one delivery edge.
    repeated = replace(graph, connections=graph.connections + graph.connections)
    assert (
        validated_routes(model, repeated, graph.parts, catalog=catalog)[1]
        == routes
    )


def test_catalog_ignores_unused_action_definition_bodies(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(
        tmp_path,
        """package Reachability {
        item def Event;
        item def UnusedEvent;
        item msg : Event;
        state def Machine {
            action def Unused {
                accept x : Event = msg;
                send msg to msg;
                send new UnusedEvent() to msg;
            }
            entry; then idle; state idle;
            transition first idle accept Event then idle;
        }
    }""",
    )
    catalog = SignalCatalog(model, ["Reachability::Machine"])
    assert dict(catalog.qualified_channels) == {"Reachability::Event": "Event"}
    face = machine_interface(model, "Reachability::Machine")
    assert not face.sent_types
    assert len(face.accepted_triggers) == 1


def test_underscore_signal_names_do_not_alias_synthetic_channels(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(
        tmp_path,
        """package Synthetic {
        item def _tick_s_t1;
        state def Machine {
            entry; then s; state s;
            transition first s accept _tick_s_t1 then s;
        }
    }""",
    )
    catalog = SignalCatalog(model, ["Synthetic::Machine"])
    assert catalog.resolve_external("_tick_s_t1") != "_tick_s_t1"
    assert catalog.resolve_external("_tick_s_t1") == catalog.resolve_external(
        "Synthetic::_tick_s_t1"
    )


def test_catalog_keeps_referenced_action_slot_rejection(tmp_path: Path) -> None:
    model = _load_inline_model(
        tmp_path,
        """package Referenced {
        item def Event;
        action def Work;
        state def Machine {
            entry; then idle;
            state idle { entry action : Work; }
            transition first idle accept Event then idle;
        }
    }""",
    )
    with pytest.raises(
        UnsupportedConstructError, match="references another action"
    ):
        SignalCatalog(model, ["Referenced::Machine"])


@pytest.mark.parametrize("missing_parameter", [False, True])
def test_strict_classifier_rejects_untyped_accept_instead_of_eventless(
    missing_parameter: bool,
) -> None:
    from unittest.mock import Mock

    from sysmlc.semantics.statemachine.triggers import classify

    # Syside's textual validator rejects unresolved/untyped signal syntax.
    # Exercise the classification boundary with unresolved AST-shaped inputs.
    transition = Mock(spec=syside.TransitionUsage)
    action = Mock(spec=syside.AcceptActionUsage)
    action.qualified_name = "Unresolved::accepter"
    action.payload_argument = None
    parameter = Mock(spec=syside.Feature)
    parameter.types.collect.return_value = []
    action.payload_parameter = None if missing_parameter else parameter
    transition.trigger_actions = [action]
    compiler = Mock(spec=syside.Compiler)
    stdlib = Mock(spec=syside.Stdlib)
    assert classify(transition, compiler, stdlib) is None
    with pytest.raises(UnsupportedConstructError, match="untyped signal"):
        classify(transition, compiler, stdlib, strict_signals=True)
