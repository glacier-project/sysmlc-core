from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sysmlc.backends.quake import build_statechart
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.loading import load_model

if TYPE_CHECKING:
    import syside

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "rejections"


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(FIXTURES_DIR)


def test_eventless_self_loop_is_rejected(model: syside.Model) -> None:
    """An eventless self-loop transition would never stabilize."""
    with pytest.raises(UnsupportedConstructError, match=r"never stabilize"):
        build_statechart(model, "Rejections::MachineSelfLoop")


def test_send_to_peer_is_rejected(model: syside.Model) -> None:
    """A `to` receiver naming another occurrence is cross-machine
    addressing, which a single statechart cannot deliver."""
    with pytest.raises(UnsupportedConstructError, match="own port"):
        build_statechart(model, "Rejections::MachineSendToPeer")


def test_send_to_peer_port_is_rejected(model: syside.Model) -> None:
    """A chained `to` receiver (another machine's port) is rejected too."""
    with pytest.raises(UnsupportedConstructError, match="own port"):
        build_statechart(model, "Rejections::MachineSendToPeerPort")


def test_negative_after_duration_is_rejected(model: syside.Model) -> None:
    """An `accept after` duration must be finite and non-negative."""
    with pytest.raises(ValueError, match=r"finite, non-negative"):
        build_statechart(model, "Rejections::MachineNegDuration")


def test_missing_initial_state_is_rejected(model: syside.Model) -> None:
    """A state definition without an initial substate fails loudly."""
    with pytest.raises(ValueError, match="No initial state for"):
        build_statechart(model, "Rejections::MachineNoInitial")


@pytest.mark.parametrize(
    "machine_qn",
    [
        "Rejections::MachineDeepInitialQualifiedName",
        "Rejections::MachineDeepInitialFeatureChain",
        "Rejections::MachineDeepInitialConflict",
    ],
)
def test_deep_initial_targets_are_rejected(
    model: syside.Model,
    machine_qn: str,
) -> None:
    """Initial targets must resolve to direct substates."""
    with pytest.raises(UnsupportedConstructError, match="direct substate"):
        build_statechart(model, machine_qn)


def test_structured_enum_literal_is_rejected(model: syside.Model) -> None:
    """A structured enum literal has no single primitive projection."""
    with pytest.raises(UnsupportedConstructError, match="is structured"):
        build_statechart(model, "Rejections::MachineStructuredEnum")
