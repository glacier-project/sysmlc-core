from __future__ import annotations

import sys
from typing import TYPE_CHECKING, override

import pytest
import syside

from sysmlc.codegen.python import PythonCodeGen
from sysmlc.codegen.structured import (
    DataclassRegistry,
    GeneratedPythonModule,
    register_dataclass,
)
from sysmlc.semantics.statemachine.facts import CompositeValue
from sysmlc.sysml.queries import resolve
from tests import _load_inline_model

if TYPE_CHECKING:
    from pathlib import Path

_MODEL = """
package Render {
    private import ScalarValues::*;

    attribute def Inner {
        attribute b : Integer default 2;
        attribute c : Integer;
    }
    attribute def Outer {
        attribute a : Integer default 1;
        attribute inner : Inner;
    }

    state def Machine {
        attribute counter : Integer := 0;
        attribute next : Integer := counter + 1;
    }
}
"""


class _ContextCodeGen(PythonCodeGen):
    """Renders feature references against a target's runtime context."""

    @override
    def _emit_feature_reference(
        self, expr: syside.FeatureReferenceExpression
    ) -> str:
        return f"ctx.{super()._emit_feature_reference(expr)}"


@pytest.fixture
def model(tmp_path: Path) -> syside.Model:
    return _load_inline_model(tmp_path, _MODEL)


def _value(model: syside.Model, qualified_name: str) -> syside.Expression:
    attribute = resolve(model, syside.AttributeUsage, qualified_name)
    expression = attribute.feature_value_expression
    assert expression is not None
    return expression


def _definition(
    model: syside.Model, qualified_name: str
) -> syside.AttributeDefinition:
    return resolve(model, syside.AttributeDefinition, qualified_name)


def _outer(model: syside.Model) -> CompositeValue:
    # Outer(a=1, inner=Inner(b=2, c unspecified)), as the shared payload
    # and attribute semantics report a structured value.
    inner = CompositeValue(
        (("b", _value(model, "Render::Inner::b")), ("c", None)),
        "Inner",
        _definition(model, "Render::Inner"),
    )
    return CompositeValue(
        (("a", _value(model, "Render::Outer::a")), ("inner", inner)),
        "Outer",
        _definition(model, "Render::Outer"),
    )


def test_expression_renders_through_the_target_expression_renderer(
    model: syside.Model,
) -> None:
    next_value = _value(model, "Render::Machine::next")

    assert PythonCodeGen().render_value(next_value) == "counter + 1"
    assert _ContextCodeGen().render_value(next_value) == "ctx.counter + 1"


def test_scalar_quantity_magnitude_renders_as_float_literal() -> None:
    assert PythonCodeGen().render_value(0.25) == "0.25"


def test_absent_value_has_no_source() -> None:
    assert PythonCodeGen().render_value(None) is None


def test_structured_value_registers_each_definition_before_its_fields(
    model: syside.Model,
) -> None:
    registered: list[str | None] = []

    rendered = PythonCodeGen().render_value(
        _outer(model), lambda definition: registered.append(definition.name)
    )

    assert rendered == "Outer(a=1, inner=Inner(b=2))"
    assert registered == ["Outer", "Inner"]
    assert PythonCodeGen().render_value(_outer(model)) == rendered


def test_fields_render_in_order_and_omit_unspecified_values(
    model: syside.Model,
) -> None:
    fields = [
        ("y", _value(model, "Render::Machine::next")),
        ("x", None),
        ("z", _value(model, "Render::Inner::b")),
    ]

    assert PythonCodeGen().render_fields(fields) == "y=counter + 1, z=2"
    assert PythonCodeGen().render_fields([("x", None)]) == ""
    assert PythonCodeGen().render_fields([]) == ""


def test_unspecified_field_keeps_the_generated_class_placeholder(
    model: syside.Model,
) -> None:
    codegen = PythonCodeGen()
    registry = DataclassRegistry()
    source = codegen.render_value(
        _outer(model),
        lambda definition: register_dataclass(
            definition, registry, codegen.render_expression
        ),
    )
    assert source is not None
    name = "sysmlc_test_render_value_types"
    module = GeneratedPythonModule.from_registry(name, registry)
    assert module is not None
    try:
        value = eval(source, vars(module.install()))
    finally:
        sys.modules.pop(name, None)

    assert (value.a, value.inner.b, value.inner.c) == (1, 2, None)
