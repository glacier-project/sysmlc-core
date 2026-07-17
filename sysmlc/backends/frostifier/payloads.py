from __future__ import annotations

from typing import TYPE_CHECKING

from sysmlc.backends.rosetta.codegen import py_type
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.queries import feature_value

if TYPE_CHECKING:
    import syside

    from sysmlc.codegen.python import PythonCodeGen

__all__ = ["dataclass_lines", "py_type"]


def dataclass_lines(
    definition: syside.Definition, init_codegen: PythonCodeGen
) -> tuple[str, ...]:
    """Render ``definition`` (item def / composite attr def) as a dataclass.

    Fields are typed via :func:`py_type` and default to the model's declared
    default, else ``None``.
    """
    assert definition.name is not None
    lines: list[str] = ["@dataclass", f"class {definition.name}:"]
    attrs = definition.owned_attributes.collect()
    if not attrs:
        lines.append("    pass")
    for attr in attrs:
        assert attr.name is not None
        default_expr = feature_value(attr)
        if default_expr is None:
            default = "None"
        else:
            try:
                default = init_codegen.render_expression(default_expr)
            except (ValueError, UnsupportedConstructError):
                default = "None"
        lines.append(f"    {attr.name}: {py_type(attr)} = {default}")
    return tuple(lines)
