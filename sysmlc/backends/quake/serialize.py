from __future__ import annotations

from typing import TYPE_CHECKING

from sismic.io import export_to_plantuml, export_to_yaml

if TYPE_CHECKING:
    from sismic.model import Statechart


def to_yaml(statechart: Statechart) -> str:
    """Serialize a sismic statechart to YAML."""
    return str(export_to_yaml(statechart))


def to_plantuml(statechart: Statechart) -> str:
    """Serialize a sismic statechart to a PlantUML diagram."""
    return str(export_to_plantuml(statechart))
