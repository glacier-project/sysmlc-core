from __future__ import annotations

from pathlib import Path

import syside

from sysmlc import configure_logging
from sysmlc.explore import (
    SysideModelQueries,
    SysideVisitor,
    iter_model_elements,
)
from sysmlc.loader import load_syside_model

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "ice-lab"
QUALITY_CONTROL_QN = "EquipmentInterfaces::QualityControlEquipment"
OPCUA_CONNECTION_QN = "OpcUaBinding::OpcUaConnection"


class PartCountingVisitor(SysideVisitor):
    """Counts part definitions and part usages encountered in the model."""

    def __init__(self, model: syside.Model):
        super().__init__(model)
        self.definitions = 0
        self.usages = 0

    def visit_part_definition(
        self, part_definition: syside.PartDefinition
    ) -> None:
        """Increment the part-definition counter."""
        del part_definition
        self.definitions += 1

    def visit_part_usage(self, part_usage: syside.PartUsage) -> None:
        """Increment the part-usage counter."""
        del part_usage
        self.usages += 1


def main() -> None:
    """Load the ice-lab model."""
    configure_logging("INFO")

    model = load_syside_model(MODEL_DIR)

    part_definitions = iter_model_elements(model, syside.PartDefinition)
    print(f"Part definitions: {len(part_definitions)}")
    for part_definition in part_definitions:
        print(f"  - {part_definition.qualified_name}")
    print()

    queries = SysideModelQueries(model)
    quality_control = queries.resolve_part_definition(QUALITY_CONTROL_QN)
    print(f"Resolved by qualified name: {quality_control.qualified_name}")
    print()

    opcua_connection = queries.resolve_metadata_definition(OPCUA_CONNECTION_QN)
    annotated = queries.iter_elements_with_metadata(
        syside.PartUsage, opcua_connection
    )
    print(
        f"Part usages annotated with {opcua_connection.name}: {len(annotated)}"
    )
    for part_usage, _metadata in annotated:
        print(f"  - {part_usage.qualified_name}")
    print()

    visitor = PartCountingVisitor(model)
    visitor.visit()
    print(
        f"Visitor counted {visitor.definitions} part definitions "
        f"and {visitor.usages} part usages"
    )


if __name__ == "__main__":
    main()
