from pathlib import Path

import pytest
import syside

from sysmlc.semantics.statemachine.bindings import effective_value_relationship
from sysmlc.sysml.editing import revalidate, set_value
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import (
    feature_value,
    feature_value_relationship,
    resolve,
)


@pytest.fixture
def value_model(tmp_path: Path) -> syside.Model:
    (tmp_path / "model.sysml").write_text(
        """package Values {
            private import ScalarValues::*;
            state def Base {
                attribute inherited : Integer = 1;
                attribute replaced : Integer default = 2;
            }
            state def Machine :> Base {
                attribute bound : Integer = 3;
                attribute initial : Integer := 4;
                attribute boundDefault : Integer default = 5;
                attribute initialDefault : Integer default := 6;
                attribute bare : Integer;
                attribute redefines inherited;
                attribute redefines replaced = 7;
                entry; then idle;
                state idle;
            }
            attribute def Structured { attribute bare : Integer; }
        }"""
    )
    return load_model(tmp_path)


@pytest.mark.parametrize(
    ("name", "initial", "default", "expected"),
    [
        ("bound", False, False, 3),
        ("initial", True, False, 4),
        ("boundDefault", False, True, 5),
        ("initialDefault", True, True, 6),
        ("replaced", False, False, 7),
    ],
)
def test_parsed_value_kind_and_owned_expression(
    value_model: syside.Model,
    name: str,
    initial: bool,
    default: bool,
    expected: int,
) -> None:
    attr = resolve(
        value_model, syside.AttributeUsage, f"Values::Machine::{name}"
    )
    rel = feature_value_relationship(attr)
    assert rel is not None
    assert (rel.is_initial, rel.is_default) == (initial, default)
    assert feature_value(attr) == rel.value
    assert isinstance(rel.value, syside.LiteralInteger)
    assert rel.value.value == expected
    assert effective_value_relationship(attr) == rel


def test_owned_value_does_not_include_inherited_value(
    value_model: syside.Model,
) -> None:
    attr = resolve(
        value_model, syside.AttributeUsage, "Values::Machine::inherited"
    )
    assert feature_value_relationship(attr) is None
    assert feature_value(attr) is None
    inherited = effective_value_relationship(attr)
    assert inherited is not None
    assert isinstance(inherited.value, syside.LiteralInteger)
    assert inherited.value.value == 1


@pytest.mark.parametrize(
    ("qn", "initial"),
    [("Values::Machine::bare", True), ("Values::Structured::bare", False)],
)
def test_created_value_accessors_before_and_after_validation(
    value_model: syside.Model, qn: str, initial: bool
) -> None:
    attr = resolve(value_model, syside.AttributeUsage, qn)
    assert feature_value_relationship(attr) is None
    set_value(attr, qn, 9)
    rel = feature_value_relationship(attr)
    assert rel is not None
    assert rel.is_initial is initial
    assert not rel.is_default
    assert feature_value(attr) == rel.value
    assert isinstance(rel.value, syside.LiteralInteger)
    assert rel.value.value == 9
    revalidate(value_model)
    assert feature_value_relationship(attr) == rel
    assert feature_value(attr) == rel.value
