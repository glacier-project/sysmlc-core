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


def test_after_combined_with_guard_is_rejected(model: syside.Model) -> None:
    """`accept after` plus an `if` guard is rejected (sismic `after` is
    monotonic, so the combination would be unsound)."""
    with pytest.raises(
        UnsupportedConstructError, match=r"combined with an `if` guard"
    ):
        build_statechart(model, "Rejections::MachineAfterGuard")


def test_eventless_self_loop_is_rejected(model: syside.Model) -> None:
    """An eventless self-loop transition would never stabilize."""
    with pytest.raises(UnsupportedConstructError, match=r"never stabilize"):
        build_statechart(model, "Rejections::MachineSelfLoop")


def test_negative_after_duration_is_rejected(model: syside.Model) -> None:
    """An `accept after` duration must be finite and non-negative."""
    with pytest.raises(ValueError, match=r"finite, non-negative"):
        build_statechart(model, "Rejections::MachineNegDuration")
