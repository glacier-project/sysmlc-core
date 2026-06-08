import syside
from typing import override
from sysmlc.cli import Backend
from sysmlc.errors import SerializationError
from .builder import StatechartBuilder
from sismic.io import export_to_plantuml, export_to_yaml
from sismic.model import Statechart

class QuakeBackend(Backend):
    """Backend for generating Sismic statecharts from SysML state definitions."""

    def __init__(self) -> None:
        super().__init__(
            name="quake",
            description="Generate Sismic statecharts from SysML state definitions.",
            formats=(
                ("yaml", "YAML-serialized Sismic statechart"),
                ("plantuml", "PlantUML statechart diagram"),
            ),
        )

    def build(self, model: syside.Model, element_qn: str) -> object:
        """Build the Sismic statechart artifact for the given state definition."""
        builder = StatechartBuilder(model, element_qn)
        return builder.build()
    
    @override
    def serialize(self, artifact: object, fmt: str) -> str:
        """Serialize the Sismic statechart artifact to the specified format."""
        if type(artifact) is not Statechart:
            raise SerializationError("expected artifact of type Statechart")
        
        if fmt == "yaml":
            return export_to_yaml(artifact)
        elif fmt == "plantuml":
            return export_to_plantuml(artifact)
        else:
            raise SerializationError(f"unsupported format: {fmt}")