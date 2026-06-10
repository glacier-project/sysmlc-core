import syside

from sysmlc.sysml.visitor import ModelVisitor


def test_model_visitor_dispatches_part_definitions_and_part_usages(
    model: syside.Model,
) -> None:
    class RecordingVisitor(ModelVisitor):
        def __init__(self, model: syside.Model):
            super().__init__(model)
            self.started = False
            self.ended = False
            self.part_definitions: list[str] = []
            self.part_usages: list[str] = []

        def start(self) -> None:
            self.started = True

        def end(self) -> None:
            self.ended = True

        def visit_part_definition(
            self,
            part_definition: syside.PartDefinition,
        ) -> None:
            if part_definition.name is not None:
                self.part_definitions.append(part_definition.name)

        def visit_part_usage(self, part_usage: syside.PartUsage) -> None:
            if part_usage.name is not None:
                self.part_usages.append(part_usage.name)

    visitor = RecordingVisitor(model)
    visitor.visit()

    assert visitor.started
    assert visitor.ended
    assert "QualityControlEquipment" in visitor.part_definitions
    assert "qualityControl" in visitor.part_usages
