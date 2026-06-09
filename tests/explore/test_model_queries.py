import pytest
import syside

from sysmlc.explore import SysideModelQueries

QUALITY_CONTROL_QN = "EquipmentInterfaces::QualityControlEquipment"
OPCUA_CONNECTION_QN = "OpcUaBinding::OpcUaConnection"


def test_model_queries_resolve_known_part_definition(
    model_queries: SysideModelQueries,
) -> None:
    part_definition = model_queries.resolve_part_definition(QUALITY_CONTROL_QN)

    assert part_definition.name == "QualityControlEquipment"
    assert str(part_definition.qualified_name) == QUALITY_CONTROL_QN


def test_model_queries_resolve_known_metadata_definition(
    model_queries: SysideModelQueries,
) -> None:
    metadata_definition = model_queries.resolve_metadata_definition(
        OPCUA_CONNECTION_QN
    )

    assert metadata_definition.name == "OpcUaConnection"
    assert str(metadata_definition.qualified_name) == OPCUA_CONNECTION_QN


def test_model_queries_find_applied_metadata_on_quality_control(
    model: syside.Model,
    model_queries: SysideModelQueries,
) -> None:
    connection_definition = model_queries.resolve_metadata_definition(
        OPCUA_CONNECTION_QN
    )
    quality_control = next(
        part_usage
        for part_usage in model.elements(syside.PartUsage)
        if part_usage.name == "qualityControl"
    )

    metadata = model_queries.find_applied_metadata(
        quality_control,
        connection_definition,
    )

    assert metadata is not None
    assert metadata.metadata_definition == connection_definition


def test_model_queries_resolve_unknown_qualified_name_raises(
    model_queries: SysideModelQueries,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        model_queries.resolve_part_definition("Does::Not::Exist")
