from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sismic.interpreter import Interpreter

from sysml2frost.generator.sismic import build_statechart
from sysml2frost.loader import load_syside_model

if TYPE_CHECKING:
    import syside

FIXTURES_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "sm03-nested-preamble"
)


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_syside_model(FIXTURES_DIR)


def test_nested_attr_seeded_into_preamble(model: syside.Model) -> None:
    """An attribute declared in a nested composite is seeded."""
    sc = build_statechart(
        model, "NestedAttributePreamble::MachineNestedAttrSelfScope"
    )
    assert sc.preamble == "innerDur = 3.0"


def test_nested_attr_visible_in_deep_substate(model: syside.Model) -> None:
    """A nested attribute is visible to deeper substates' transitions."""
    sc = build_statechart(
        model, "NestedAttributePreamble::MachineNestedAttrDeepScope"
    )
    assert sc.preamble == "innerDur = 4.0"
    interp = Interpreter(sc)
    interp.execute()
    assert "outer::mid::alpha" in interp.configuration
    interp.clock.time = 3.9
    interp.execute()
    assert "outer::mid::alpha" in interp.configuration
    interp.clock.time = 4.0
    interp.execute()
    assert "outer::mid::beta" in interp.configuration


def test_root_and_nested_attrs_coexist(model: syside.Model) -> None:
    """Root and nested attributes with distinct names are both seeded."""
    sc = build_statechart(
        model, "NestedAttributePreamble::MachineRootAndNestedDistinctNames"
    )
    assert sc.preamble == "speed = 1.5\ninnerDur = 2.0"


def test_root_nested_collision_raises(model: syside.Model) -> None:
    """Root and nested attributes with the same name raise."""
    with pytest.raises(
        ValueError, match=r"declares attribute 'x' in two scopes"
    ):
        build_statechart(
            model, "NestedAttributePreamble::MachineCollisionRootNested"
        )


def test_sibling_collision_raises(model: syside.Model) -> None:
    """Sibling composites declaring the same name raise."""
    with pytest.raises(
        ValueError, match=r"declares attribute 'count' in two scopes"
    ):
        build_statechart(
            model, "NestedAttributePreamble::MachineCollisionSiblings"
        )
