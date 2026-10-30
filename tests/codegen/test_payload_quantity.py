from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import syside

from sysmlc.codegen.python import PythonCodeGen, payload_fields
from sysmlc.codegen.structured import DataclassRegistry, register_dataclass
from sysmlc.sysml.queries import is_scalar_quantity, resolve
from tests import _load_inline_model, _single_element

if TYPE_CHECKING:
    from pathlib import Path

# An omitted scalar quantity without a value is one unspecified number,
# like an unvalued Integer field; its library definition's own features
# (`num`, `mRef`, ...) are not payload fields.
_MODEL = """
package QuantityPayload {
    private import ScalarValues::*;
    private import SI::*;

    item def Timed {
        attribute n : Integer default 1;
        attribute dt : ISQBase::DurationValue;
    }

    state def Sender {
        port q;
        entry;
            then s0;
        state s0;
        transition first s0 do send new Timed() to q then s0;
    }
}
"""


def test_omitted_unvalued_scalar_quantity_is_unspecified(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, _MODEL)
    send = _single_element(model, syside.SendActionUsage)

    n, dt = payload_fields(send)

    assert (n.name, n.explicit) == ("n", False)
    assert isinstance(n.value, syside.LiteralInteger)
    assert n.value.value == 1
    assert (dt.name, dt.value, dt.explicit) == ("dt", None, False)
    assert is_scalar_quantity(dt.feature)
    fields = [(field.name, field.value) for field in (n, dt)]
    assert PythonCodeGen().render_fields(fields) == "n=1"


def test_unvalued_scalar_quantity_field_is_a_float_placeholder(
    tmp_path: Path,
) -> None:
    model = _load_inline_model(tmp_path, _MODEL)
    registry = DataclassRegistry()

    register_dataclass(
        resolve(model, syside.ItemDefinition, "QuantityPayload::Timed"),
        registry,
        PythonCodeGen().render_expression,
    )

    assert registry.class_blocks() == [
        "@dataclass",
        "class Timed:",
        "    n: int = 1",
        "    dt: float = None",
    ]


def test_omitted_quantity_default_requires_quantity_expression_support(
    tmp_path: Path,
) -> None:
    source = _MODEL.replace(
        "attribute dt : ISQBase::DurationValue;",
        "attribute dt : ISQBase::DurationValue default 0.5 [s];",
    )
    model = _load_inline_model(tmp_path, source)
    send = _single_element(model, syside.SendActionUsage)

    fields = payload_fields(send)

    # A literal quantity is eligible for extraction as a constant. Send
    # emission still requires expression support and must reject it
    # explicitly rather than omit its meaningful value or use None.
    assert isinstance(fields[1].value, syside.OperatorExpression)
    with pytest.raises(ValueError, match=r"unsupported operator: .*Quantity"):
        PythonCodeGen().render_fields(
            (field.name, field.value) for field in fields
        )
