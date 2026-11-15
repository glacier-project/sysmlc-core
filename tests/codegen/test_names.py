from __future__ import annotations

import pytest

from sysmlc.codegen.names import NameRegistry
from sysmlc.errors import UnsupportedConstructError


def candidate(preferred: str, attempt: int) -> str:
    base = preferred.replace(".", "_")
    return base if attempt == 0 else f"{base}_{attempt:02d}"


def test_distinct_symbols_keep_distinct_names_and_stable_references() -> None:
    names = NameRegistry(candidate)
    assert names.assign("state:A", "S1.1") == "S1_1"
    assert names.assign("state:B", "S1_1") == "S1_1_01"
    assert names.assign("state:A", "different") == "S1_1"
    assert names.assign("timer:A", "S1_1") == "S1_1_02"


def test_fixed_names_and_existing_suffixes_are_skipped() -> None:
    names = NameRegistry(candidate)
    names.reserve("S1_1", "S1_1_01")
    names.reserve("S1_1")
    assert names.assign("state:A", "S1.1") == "S1_1_02"


def test_registries_do_not_share_assignments_or_reservations() -> None:
    first = NameRegistry(candidate)
    second = NameRegistry(candidate)
    first.reserve("idle")
    assert first.assign("state", "idle") == "idle_01"
    assert second.assign("state", "idle") == "idle"


def test_target_comparison_rule_applies_to_assignments_and_reservations() -> (
    None
):
    names = NameRegistry(candidate, key=str.casefold)
    names.reserve("Machine")
    assert not names.available("machine")
    assert names.assign("first", "machine") == "machine_01"
    assert names.assign("second", "MACHINE") == "MACHINE_02"
    assert names.assign("first", "other") == "machine_01"


def test_availability_requires_an_unchanged_unoccupied_spelling() -> None:
    names = NameRegistry(candidate)
    assert not names.available("S1.1")
    assert names.available("S1_1")
    names.assign("state", "S1.1")
    assert not names.available("S1_1")
    assert names.available("S1_1_01")


def test_failed_reservation_is_atomic_including_comparison_aliases() -> None:
    names = NameRegistry(candidate, key=str.casefold)
    names.assign("state", "Idle")
    with pytest.raises(UnsupportedConstructError, match="reserved after"):
        names.reserve("fresh", "IDLE")
    assert names.available("fresh")
    assert names.assign("state", "different") == "Idle"


def test_readable_names_can_be_reserved_by_assigning_them_first() -> None:
    names = NameRegistry(candidate)
    assert names.assign("plain", "S1_1") == "S1_1"
    assert names.assign("suffixed", "S1_1_01") == "S1_1_01"
    assert names.assign("dotted", "S1.1") == "S1_1_02"
