import pytest
import syside

from sysmlc.sysml import metadata

QUALITY_CONTROL_QN = "EquipmentInterfaces::QualityControlEquipment"
OPCUA_CONNECTION_QN = "OpcUaBinding::OpcUaConnection"


def test_model_queries_resolve_known_part_definition(
    model: syside.Model,
) -> None:
    part_definition = metadata.resolve_part_definition(
        model, QUALITY_CONTROL_QN
    )

    assert part_definition.name == "QualityControlEquipment"
    assert str(part_definition.qualified_name) == QUALITY_CONTROL_QN


def test_model_queries_resolve_known_metadata_definition(
    model: syside.Model,
) -> None:
    metadata_definition = metadata.resolve_metadata_definition(
        model, OPCUA_CONNECTION_QN
    )

    assert metadata_definition.name == "OpcUaConnection"
    assert str(metadata_definition.qualified_name) == OPCUA_CONNECTION_QN


def test_model_queries_find_applied_metadata_on_quality_control(
    model: syside.Model,
) -> None:
    connection_definition = metadata.resolve_metadata_definition(
        model, OPCUA_CONNECTION_QN
    )
    quality_control = next(
        part_usage
        for part_usage in model.elements(syside.PartUsage)
        if part_usage.name == "qualityControl"
    )

    applied = metadata.find_applied_metadata(
        quality_control,
        connection_definition,
    )

    assert applied is not None
    assert applied.metadata_definition == connection_definition


def test_model_queries_resolve_unknown_qualified_name_raises(
    model: syside.Model,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        metadata.resolve_part_definition(model, "Does::Not::Exist")
