from __future__ import annotations

import ast
import keyword
import re
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Final

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.foreign_artifact.text_rep import write_file
from sysmlc.sysml.queries import feature_value, is_scalar_quantity

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

_SCALAR_PY: Final[dict[str, str]] = {
    "Real": "float",
    "Rational": "float",
    "Integer": "int",
    "Natural": "int",
    "Boolean": "bool",
    "String": "str",
}

# Marker attribute stamped on installed generated modules; carries the
# exact source so reinstalling can distinguish "same module again"
# (idempotent) from "different module wants this name" (refused).
_SOURCE_KEY = "__sysmlc_generated_source__"


def types_module_name(qualified_name: str) -> str:
    """Return a Python-safe generated-types module name for a SysML name.

    Args:
        qualified_name: The qualified name of the element the module is
            generated for.

    Returns:
        The sanitized name suffixed with ``_types``, e.g.
        ``FurutaPendulum_furutaSystem_types``.

    Raises:
        ValueError: If the name contains no identifier characters.
    """
    stem = re.sub(r"\W+", "_", qualified_name).strip("_")
    if not stem:
        raise ValueError("qualified name has no identifier characters")
    if stem[0].isdigit():
        stem = f"_{stem}"
    return f"{stem}_types"


@dataclass(frozen=True)
class GeneratedPythonModule:
    """A generated Python support module owned by a build artifact."""

    name: str
    lines: tuple[str, ...]

    @property
    def source(self) -> str:
        """Return the complete newline-terminated module source."""
        return "\n".join(self.lines) + "\n"

    def install(self) -> ModuleType:
        """Install the module in ``sys.modules`` for in-process execution.

        Reinstalling identical generated source is idempotent. Reusing the
        same module name for different source fails rather than silently
        replacing classes that installed consumers may still reference.

        Returns:
            The installed module.

        Raises:
            UnsupportedConstructError: If the module name is already
                occupied by different source.
        """
        existing = sys.modules.get(self.name)
        if existing is not None:
            if existing.__dict__.get(_SOURCE_KEY) == self.source:
                return existing
            raise UnsupportedConstructError(
                f"generated types module {self.name!r} is already installed "
                "with different content"
            )

        code = compile(self.source, f"<generated {self.name}>", "exec")
        module = ModuleType(self.name)
        module.__dict__[_SOURCE_KEY] = self.source
        sys.modules[self.name] = module
        try:
            exec(code, module.__dict__)
        except Exception:
            if sys.modules.get(self.name) is module:
                del sys.modules[self.name]
            raise
        return module

    def write(self, directory: Path) -> Path:
        """Write the module into ``directory`` and return its path."""
        return write_file(self.lines, directory, self.name)

    @classmethod
    def from_registry(
        cls, name: str, registry: DataclassRegistry
    ) -> GeneratedPythonModule | None:
        """Create the companion module for ``registry``'s dataclasses.

        Returns:
            The rendered module, or ``None`` when no dataclass was
            registered and no companion is needed.
        """
        lines = registry.module_lines()
        if not lines:
            return None
        return cls(name, tuple(lines))


def _resolve_field_type(
    attribute: syside.AttributeUsage,
) -> tuple[str, syside.Definition | None]:
    """Return an attribute's Python annotation and structured definition.

    A scalar quantity value collapses to ``float`` (its SI magnitude);
    SysML scalars map to Python builtins; a structured definition maps to
    its generated dataclass name and is returned alongside; anything
    unmapped falls back to ``object`` deliberately: an untyped or
    unrecognized attribute is valid SysML, and the annotation is only a
    hint on a working field, unlike the unnamed/keyword cases below that
    could not emit importable code and therefore raise.

    Raises:
        ValueError: If a structured attribute definition has no name.
    """
    if is_scalar_quantity(attribute):
        return "float", None
    for definition in attribute.attribute_definitions.collect():
        if definition.name in _SCALAR_PY:
            return _SCALAR_PY[definition.name], None
        if (
            isinstance(definition, syside.Definition)
            and definition.owned_attributes.collect()
        ):
            if definition.name is None:
                raise ValueError("structured attribute definition has no name")
            return definition.name, definition
    return "object", None


def constructed_payload_definition(
    action: syside.SendActionUsage,
) -> syside.Definition | None:
    """Return the definition a send's ``new <Type>(...)`` payload constructs.

    Returns:
        The constructed definition, or ``None`` when the payload is not a
        constructor expression or does not resolve to a definition.
    """
    payload = action.payload_argument
    if not isinstance(payload, syside.ConstructorExpression):
        return None
    definition = payload.instantiated_type
    if not isinstance(definition, syside.Definition):
        return None
    return definition


class DataclassRegistry:
    """Rendered dataclass blocks keyed by simple name, collision-checked.

    Registration is idempotent for the same qualified origin and fails
    loud when two different structured definitions want the same simple
    Python name, since a generated companion module has one flat
    namespace.
    """

    def __init__(self) -> None:
        # One entry per generated class name: (origin qualified name, block).
        self._entries: dict[str, tuple[str, tuple[str, ...]]] = {}

    def __bool__(self) -> bool:
        """Whether any dataclass was registered."""
        return bool(self._entries)

    def register(self, name: str, origin: str, lines: tuple[str, ...]) -> None:
        """Register one rendered dataclass block.

        Args:
            name: The generated class's simple Python name.
            origin: The qualified name of the structured definition the
                block was rendered from.
            lines: The rendered ``@dataclass`` block.

        Raises:
            UnsupportedConstructError: If ``name`` is already taken by a
                different origin, or the same origin produced a different
                block.
        """
        known = self._entries.get(name)
        if known is not None:
            known_origin, known_lines = known
            if known_origin != origin:
                raise UnsupportedConstructError(
                    f"two structured types share the simple name {name!r}: "
                    f"{known_origin!r} and {origin!r}; rename one"
                )
            if known_lines != lines:
                raise UnsupportedConstructError(
                    f"structured type {origin!r} produced conflicting "
                    "Python definitions"
                )
            return
        self._entries[name] = (origin, lines)

    def is_registered(self, name: str, origin: str) -> bool:
        """Whether this exact structured definition is already registered.

        A same-named registration from a different origin reports False;
        :meth:`register` is the single authority that rejects it.
        """
        known = self._entries.get(name)
        return known is not None and known[0] == origin

    def names(self) -> list[str]:
        """Return the registered class names, sorted."""
        return sorted(self._entries)

    def class_blocks(self) -> list[str]:
        """Return every block, sorted by name, blank-line separated."""
        lines: list[str] = []
        for name in self.names():
            lines.extend(self._entries[name][1])
            lines.append("")
        if lines:
            lines.pop()
        return lines

    def module_lines(self, *, preceding_lines: Sequence[str] = ()) -> list[str]:
        """Render a complete generated-types module around the blocks.

        Deferred annotations open the module: blocks are emitted sorted by
        name, so a field typed by another generated class may precede that
        class's definition.

        Args:
            preceding_lines: Lines placed between the deferred-annotations
                header and the dataclass section, for a backend's extra
                type definitions (e.g. enum classes).

        Returns:
            The full module body, or just ``preceding_lines`` when no
            dataclass is registered, or no lines at all when there is
            nothing to render.
        """
        if not self._entries:
            return list(preceding_lines)
        lines = ["from __future__ import annotations", ""]
        lines.extend(preceding_lines)
        if preceding_lines:
            lines.append("")
        lines.append("from dataclasses import dataclass")
        lines.append("")
        lines.extend(self.class_blocks())
        return lines


def types_import_lines(
    module_name: str | None, names: Sequence[str]
) -> list[str]:
    """Render the ``from <module> import <names>`` line for generated types.

    Args:
        module_name: The generated module's name.
        names: The type names to import, in the order to emit.

    Returns:
        One import line, or no lines when ``names`` is empty.

    Raises:
        ValueError: If ``names`` is non-empty but ``module_name`` is None.
    """
    if not names:
        return []
    if module_name is None:
        raise ValueError(
            "types module name must be set before preamble assembly"
        )
    return [f"from {module_name} import {', '.join(names)}"]


def register_dataclass(
    definition: syside.Definition,
    registry: DataclassRegistry,
    render_default: Callable[[syside.Expression], str],
) -> None:
    """Render ``definition`` as a dataclass and register it, recursively.

    A field typed by another structured definition registers that
    definition first, so the companion module is self-contained. A field
    default comes from the model's declared default when it renders to a
    Python literal (``bool``, ``int``, ``float``, or ``str``); any other
    default, and any field without one, falls back to ``None`` so the
    emitted class never embeds expressions that reference names outside
    the companion module.

    Args:
        definition: The structured (item or composite attribute)
            definition to render.
        registry: The registry the rendered block lands in.
        render_default: Renders a default-value expression to Python
            source; typically the owning backend's expression renderer.

    Raises:
        UnsupportedConstructError: If the definition or one of its fields
            is unnamed or not a Python identifier, the definition is
            recursive, or its simple name collides with a different
            definition already registered.
    """
    _register_dataclass(definition, registry, render_default, set())


def _register_dataclass(
    definition: syside.Definition,
    registry: DataclassRegistry,
    render_default: Callable[[syside.Expression], str],
    in_progress: set[str],
) -> None:
    """Recursive worker for :func:`register_dataclass`."""
    name = definition.name
    if name is None:
        raise UnsupportedConstructError(
            "structured type has no resolved name", node=definition
        )
    if not name.isidentifier() or keyword.iskeyword(name):
        raise UnsupportedConstructError(
            f"structured type name {name!r} is not a valid Python identifier",
            node=definition,
        )
    origin = str(definition.qualified_name or name)
    if registry.is_registered(name, origin):
        return
    if origin in in_progress:
        raise UnsupportedConstructError(
            f"structured type {origin!r} is recursive; generated Python "
            "dataclasses do not support recursive SysML value types",
            node=definition,
        )
    in_progress.add(origin)
    try:
        fields = definition.owned_attributes.collect()
        lines = ["@dataclass", f"class {name}:"]
        if not fields:
            lines.append("    pass")
        for attribute in fields:
            field_name = attribute.name
            if field_name is None:
                raise UnsupportedConstructError(
                    f"structured type {name!r} has an unnamed field",
                    node=attribute,
                )
            if not field_name.isidentifier() or keyword.iskeyword(field_name):
                raise UnsupportedConstructError(
                    f"structured field name {field_name!r} is not a "
                    "valid Python identifier",
                    node=attribute,
                )
            annotation, nested = _resolve_field_type(attribute)
            if nested is not None:
                _register_dataclass(
                    nested, registry, render_default, in_progress
                )
            default = _field_default(attribute, render_default)
            lines.append(f"    {field_name}: {annotation} = {default}")
        registry.register(name, origin, tuple(lines))
    finally:
        in_progress.remove(origin)


def _field_default(
    attribute: syside.AttributeUsage,
    render_default: Callable[[syside.Expression], str],
) -> str:
    """Render a field's default, or ``None`` when it is not a literal."""
    default_expression = feature_value(attribute)
    if default_expression is None:
        return "None"
    try:
        rendered = render_default(default_expression)
        literal = ast.literal_eval(rendered)
    except (SyntaxError, ValueError, UnsupportedConstructError):
        return "None"
    if isinstance(literal, (bool, int, float, str)):
        return rendered
    return "None"
