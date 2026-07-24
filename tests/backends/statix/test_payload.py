"""Tests for the shared payload-schema walker.

See docs/superpowers/specs/2026-07-23-statix-canonical-payload-encoding-design.md.
"""

from __future__ import annotations

import pytest

from sysmlc.backends.statix.payload import _walk_payload_fields
from sysmlc.backends.statix.program import CField, CStruct
from sysmlc.errors import UnsupportedConstructError


def test_walk_payload_fields_two_level_nesting() -> None:
    structs = {
        "sample_t": CStruct(
            name="sample_t", fields=(CField("value", "double", ""),)
        ),
        "measurement_t": CStruct(
            name="measurement_t",
            fields=(
                CField("value", "double", ""),
                CField("sample", "sample_t", ""),
            ),
        ),
    }
    assert _walk_payload_fields("measurement_t", structs) == [
        ("value",),
        ("sample", "value"),
    ]


def test_walk_payload_fields_three_level_nesting() -> None:
    structs = {
        "inner_t": CStruct(name="inner_t", fields=(CField("z", "double", ""),)),
        "middle_t": CStruct(
            name="middle_t",
            fields=(CField("y", "double", ""), CField("inner", "inner_t", "")),
        ),
        "outer_t": CStruct(
            name="outer_t",
            fields=(
                CField("x", "double", ""),
                CField("middle", "middle_t", ""),
            ),
        ),
    }
    assert _walk_payload_fields("outer_t", structs) == [
        ("x",),
        ("middle", "y"),
        ("middle", "inner", "z"),
    ]


def test_walk_payload_fields_accepts_integer_leaf() -> None:
    structs = {
        "counter_t": CStruct(
            name="counter_t",
            fields=(
                CField("count", "int32_t", ""),
                CField("value", "double", ""),
            ),
        ),
    }
    assert _walk_payload_fields("counter_t", structs) == [
        ("count",),
        ("value",),
    ]


def test_walk_payload_fields_accepts_boolean_leaf() -> None:
    structs = {
        "flag_t": CStruct(
            name="flag_t",
            fields=(CField("armed", "bool", ""), CField("value", "double", "")),
        ),
    }
    assert _walk_payload_fields("flag_t", structs) == [
        ("armed",),
        ("value",),
    ]


def test_walk_payload_fields_accepts_mixed_primitive_and_padding_order() -> (
    None
):
    # Proves the walker's ORDER handling, independent of sizing: declaration
    # order is preserved regardless of leaf type mix (bool, int32_t, double).
    structs = {
        "mixed_t": CStruct(
            name="mixed_t",
            fields=(
                CField("armed", "bool", ""),
                CField("count", "int32_t", ""),
                CField("value", "double", ""),
            ),
        ),
    }
    assert _walk_payload_fields("mixed_t", structs) == [
        ("armed",),
        ("count",),
        ("value",),
    ]


def test_walk_payload_fields_rejects_non_representable_leaf() -> None:
    structs = {
        "bad_t": CStruct(
            name="bad_t",
            fields=(
                CField("text", "const char*", ""),
                CField("value", "double", ""),
            ),
        ),
    }
    with pytest.raises(UnsupportedConstructError, match="text"):
        _walk_payload_fields("bad_t", structs)


def test_walk_payload_fields_rejects_recursive_definition() -> None:
    structs = {
        "cyclic_t": CStruct(
            name="cyclic_t", fields=(CField("self", "cyclic_t", ""),)
        ),
    }
    with pytest.raises(UnsupportedConstructError, match="recursive"):
        _walk_payload_fields("cyclic_t", structs)
