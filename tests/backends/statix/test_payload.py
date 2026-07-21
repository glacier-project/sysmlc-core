"""Tests for the shared whole-payload struct flattener.

See docs/superpowers/specs/2026-07-16-statix-payload-marshalling-design.md.
"""

from __future__ import annotations

import pytest

from sysmlc.backends.statix.payload import _flatten_leaf_paths
from sysmlc.backends.statix.program import CField, CStruct
from sysmlc.errors import UnsupportedConstructError


def test_flatten_leaf_paths_two_level_nesting() -> None:
    structs = {
        "sample_t": CStruct(name="sample_t", fields=(CField("value", "double", ""),)),
        "measurement_t": CStruct(
            name="measurement_t",
            fields=(
                CField("value", "double", ""),
                CField("sample", "sample_t", ""),
            ),
        ),
    }
    assert _flatten_leaf_paths("measurement_t", structs) == [
        ("value",),
        ("sample", "value"),
    ]


def test_flatten_leaf_paths_three_level_nesting() -> None:
    structs = {
        "inner_t": CStruct(name="inner_t", fields=(CField("z", "double", ""),)),
        "middle_t": CStruct(
            name="middle_t",
            fields=(CField("y", "double", ""), CField("inner", "inner_t", "")),
        ),
        "outer_t": CStruct(
            name="outer_t",
            fields=(CField("x", "double", ""), CField("middle", "middle_t", "")),
        ),
    }
    assert _flatten_leaf_paths("outer_t", structs) == [
        ("x",),
        ("middle", "y"),
        ("middle", "inner", "z"),
    ]


def test_flatten_leaf_paths_rejects_non_double_leaf() -> None:
    structs = {
        "bad_t": CStruct(
            name="bad_t",
            fields=(CField("flag", "bool", ""), CField("value", "double", "")),
        ),
    }
    with pytest.raises(UnsupportedConstructError, match="flag"):
        _flatten_leaf_paths("bad_t", structs)


def test_flatten_leaf_paths_rejects_recursive_definition() -> None:
    structs = {
        "cyclic_t": CStruct(
            name="cyclic_t", fields=(CField("self", "cyclic_t", ""),)
        ),
    }
    with pytest.raises(UnsupportedConstructError, match="recursive"):
        _flatten_leaf_paths("cyclic_t", structs)
