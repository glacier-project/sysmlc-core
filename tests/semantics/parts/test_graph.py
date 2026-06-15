from pathlib import Path

import pytest

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.parts.graph import part_graph
from sysmlc.sysml.loading import load_model

FIX = Path("models/sm-examples/part01-two-parts")


def test_part_graph_extracts_system() -> None:
    g = part_graph(load_model(FIX), "Part01::pingSystem")
    assert g.name == "pingSystem"
    assert [p.usage_name for p in g.parts] == ["plant", "tb"]
    assert g.parts[0].definition_name == "Plant"
    assert g.parts[0].behavior_qn == "Part01::PlantBehavior"
    assert g.parts[1].definition_name == "Tester"
    assert g.parts[1].behavior_qn == "Part01::TesterBehavior"
    assert g.connections == ((("plant", "commPort"), ("tb", "commPort")),)


def test_part_graph_captures_declared_ports() -> None:
    g = part_graph(load_model(FIX), "Part01::pingSystem")
    assert g.parts[0].ports == ("commPort",)
    assert g.parts[1].ports == ("commPort",)


def test_part_graph_rejects_zero_exhibit_part() -> None:
    # A part def with no exhibit is a pure composite (not supported in 2a).
    g = load_model(Path("models/sm-examples/part-zero-exhibit"))
    with pytest.raises(UnsupportedConstructError, match="no exhibit"):
        part_graph(g, "PartZero::sys")
