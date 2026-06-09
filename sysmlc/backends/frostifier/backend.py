from __future__ import annotations


from __future__ import annotations
from typing import TYPE_CHECKING
from ..base import Backend, OutputOptions

if TYPE_CHECKING:
    from pathlib import Path
    import syside

class FrostifierBackend(Backend):
    """Reserved backend for generating Frost simulations from SysML."""

    def __init__(self) -> None:
        super().__init__(
            name="frostifier",
            description=(
                "Generate Frost simulations from SysML "
                "(reserved; not yet implemented)."
            ),
        )

    def build(self, model: syside.Model, element_qn: str) -> object:
        """Raise: this backend's target is not implemented yet."""
        raise NotImplementedError(
            f"the {self.name!r} backend is not implemented yet"
        )

    def write(self, artifact: object, options: OutputOptions) -> list[Path]:
        """Raise: this backend's target is not implemented yet."""
        raise NotImplementedError(
            f"the {self.name!r} backend is not implemented yet"
        )

    def summary(self, artifact: object) -> str:
        """Raise: this backend's target is not implemented yet."""
        raise NotImplementedError(
            f"the {self.name!r} backend is not implemented yet"
        )

