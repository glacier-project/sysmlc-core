from pathlib import Path

import pytest
import syside

from sysmlc.sysml.queries import item_payload_features, resolve
from tests import _load_inline_model


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        ("item def Event;", []),
        ("item def Event :> Items::Item;", []),
        ("item def Base; item def Event :> Base;", []),
        (
            "item def Payload; item def Event { item value : Payload; }",
            ["value"],
        ),
        (
            "item def Payload; item def Event { ref value : Payload; }",
            ["value"],
        ),
        (
            "item def Payload; item def Base { item value : Payload; } "
            "item def Event :> Base;",
            ["value"],
        ),
        (
            "library package Messages { item def Payload; "
            "item def Base { ref value : Payload; } } "
            "item def Event :> Messages::Base;",
            ["value"],
        ),
        (
            "item def Event { attribute :>> isSolid; }",
            ["isSolid"],
        ),
        (
            "item def Payload; item def Base { item value : Payload; } "
            "item def Event :> Base { item :>> value; }",
            ["value"],
        ),
    ],
)
def test_retains_features_beyond_standard_item(
    tmp_path: Path, declaration: str, expected: list[str]
) -> None:
    model = _load_inline_model(
        tmp_path, f"package PayloadShape {{ {declaration} }}"
    )
    item = resolve(model, syside.ItemDefinition, "PayloadShape::Event")
    features = item_payload_features(item, syside.Stdlib(model.index))
    assert [feature.name for feature in features] == expected
    if expected:
        assert str(features[0].qualified_name).startswith("PayloadShape::")
