from __future__ import annotations

from typing import TYPE_CHECKING

from sismic.model import Statechart

from sysml2frost.sismic import build_statechart

if TYPE_CHECKING:
    import syside

    from tests.sismic.conftest import SmExample


def test_build_statechart_returns_statechart_instance(
    sm_example: SmExample,
    sm_example_model: syside.Model,
) -> None:
    """The builder returns a sismic ``Statechart`` for every sm-example."""
    sc = build_statechart(sm_example_model, sm_example.state_def_qn)
    assert isinstance(sc, Statechart)
