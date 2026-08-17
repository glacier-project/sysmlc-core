"""Support for SysML ``TextualRepresentation`` as an external Python module."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.queries import iter_elements

_PYTHON_TAG = "python"


def _require_package_or_calc_def(element: syside.Element) -> None:
    """Reject a Python rep attached to anything but a package or calc def.

    A package rep carries module scaffolding (imports, constants, private
    helpers); a calc-def rep carries that function's body. A rep attached
    to any other element (an action, a state, ...) has no place in the
    generated module: its text would land at module top level and execute
    at import time.
    """
    if isinstance(element, syside.Package | syside.CalculationDefinition):
        return
    raise UnsupportedConstructError(
        "a Python textual representation is attached to an element that "
        "is neither a package nor a calc def; Python bodies are collected "
        "from packages (module scaffolding) and calc defs (function "
        "bodies) only.",
        node=element,
    )


def _require_valid_python(body: str, element: syside.Element) -> None:
    """Reject a rep body that does not parse as Python.

    Validating each body on its own keeps the diagnosis attached to the
    element that carries the broken rep.
    """
    try:
        ast.parse(body)
    except SyntaxError as error:
        raise UnsupportedConstructError(
            "the Python textual representation body is not valid Python: "
            f"{error.msg} (body line {error.lineno})",
            node=element,
        ) from error


def _python_rep_bodies(element: syside.Element) -> list[str]:
    """Bodies of the Python textual representations on ``element``."""
    return [
        tr.body
        for tr in element.textual_representations.collect()
        if tr.language.strip().lower() == _PYTHON_TAG
    ]


def _require_backing_def(
    bodies: list[str], calc: syside.CalculationDefinition
) -> None:
    """Require a body of the calc def to define ``def <calc.name>``.

    Callers import the calc def's name from the generated module;
    without a matching def the import would only fail at run time.
    """
    defined: list[str] = []
    for body in bodies:
        for statement in ast.parse(body).body:
            if isinstance(statement, ast.FunctionDef):
                defined.append(statement.name)
    if calc.name in defined:
        return
    found = ", ".join(repr(name) for name in defined) or "no function"
    raise UnsupportedConstructError(
        f"the Python body defines {found} but the calc def is named "
        f"{calc.name!r}; one def must match the calc def name.",
        node=calc,
    )


def _require_rep_backed_calc_defs(model: syside.Model) -> None:
    """Reject a rep-carrying calc def the generated module cannot back.

    Each rep-carrying calc def must have exactly one Python body, and
    that body must define a function named after the calc def; otherwise
    the module cannot provide the function its callers import.
    """
    for calc in iter_elements(model, syside.CalculationDefinition):
        bodies = _python_rep_bodies(calc)
        if not bodies:
            continue
        if len(bodies) > 1:
            raise UnsupportedConstructError(
                "this calc def carries more than one Python textual "
                "representation, so its function body is ambiguous; "
                "keep exactly one.",
                node=calc,
            )
        for body in bodies:
            _require_valid_python(body, calc)
        _require_backing_def(bodies, calc)


def _register_defs(
    body: str,
    element: syside.Element,
    seen: dict[str, tuple[str, str]],
) -> None:
    """Register the body's top-level defs; reject a conflicting name.

    Idempotent for identical implementations; a different body under
    the same name is a collision and fails loud.
    """
    qualified_name = str(element.qualified_name)
    for statement in ast.parse(body).body:
        if not isinstance(statement, ast.FunctionDef):
            continue
        source = ast.unparse(statement)
        known = seen.get(statement.name)
        if known is None:
            seen[statement.name] = (qualified_name, source)
            continue
        known_qualified_name, known_source = known
        if known_source == source:
            continue
        raise UnsupportedConstructError(
            f"two Python rep bodies define {statement.name!r} with "
            f"different implementations ({known_qualified_name!r} and "
            f"{qualified_name!r}); the generated module has one flat "
            "namespace, so the last definition would silently win; "
            "rename one.",
            node=element,
        )


def _require_unique_defs(model: syside.Model) -> None:
    """Reject two rep bodies defining the same function differently.

    The generated module has one flat namespace: a second ``def`` of
    the same name would silently override the first for every caller,
    whether the clash is between two calc defs, a scaffolding helper
    and a calc def, or two scaffolding helpers.
    """
    elements: list[syside.Element] = [
        *iter_elements(model, syside.Package),
        *iter_elements(model, syside.CalculationDefinition),
    ]
    seen: dict[str, tuple[str, str]] = {}
    for element in elements:
        for body in _python_rep_bodies(element):
            _require_valid_python(body, element)
            _register_defs(body, element, seen)


def _collect_lines(element: syside.Element) -> list[str]:
    code: list[str] = []

    for body in _python_rep_bodies(element):
        _require_package_or_calc_def(element)
        _require_valid_python(body, element)
        if code:
            code.extend(("", ""))
        code.extend(body.splitlines())

    for child in element.owned_elements.collect():
        child_lines = _collect_lines(child)
        if not child_lines:
            continue
        if code:
            code.extend(("", ""))
        code.extend(child_lines)

    return code


def _collect_code(model: syside.Model) -> list[str]:
    code: list[str] = []
    for element in model.elements(
        syside.Element,
        include_subtypes=True,
        considered_document_kinds=syside.DocumentKind.MODEL,
    ):
        if getattr(element, "owner", None) is not None:
            continue
        lines = _collect_lines(element)
        if not lines:
            continue
        if code:
            code.extend(("", ""))
        code.extend(lines)
    return code


def extract_text_rep(
    model: syside.Model,
    scope_qn: str,
    lang: str = "python",
    *,
    module_name: str | None = None,
) -> tuple[str, tuple[str, ...]] | None:
    """Extract the model's Python rep bodies as module source.

    Collects every Python ``TextualRepresentation`` body in the model
    (package reps first within each element, in model order) into the
    source lines of one flat Python module. The caller writes the module
    to disk and derives the backing function names from the written file,
    exactly as for a user-supplied backing module.

    Args:
        model: Loaded syside model to collect rep bodies from.
        scope_qn: Qualified name of the element being built; its simple
            name defaults the module stem to ``<name>_impl``.
        lang: language selection for textual rep
        module_name: Explicit module stem overriding the default.

    Returns:
        A ``(module_stem, source_lines)`` pair, or None when the model
        carries no Python textual representations.

    Raises:
        UnsupportedConstructError: If a rep is attached to an element
            that is neither a package nor a calc def, a body is not valid
            Python or is empty, a calc def carries more than one Python
            rep or none of its defs matches its name, or two bodies
            define the same function differently.
    """
    lines = _collect_code(model)
    if not lines:
        return None

    src_code = "\n".join(lines)
    if not src_code.strip():
        raise UnsupportedConstructError(
            "Python TextualRepresentation bodies found in the model while "
            f"processing {scope_qn!r} but all are empty."
        )
    stem = module_name or f"{scope_qn.split('::')[-1]}_impl"
    _require_rep_backed_calc_defs(model)
    _require_unique_defs(model)

    header = [
        "# Auto-generated from SysML TextualRepresentation bodies.",
        "# Do not edit — regenerate from the SysML source instead.",
        "",
    ]
    full_lines = tuple(header) + tuple(lines)

    return stem, full_lines


def write_file(
    src_lines: list[str] | tuple[str, ...],
    out_dir: Path,
    module_name: str,
    lang: str = "python",
) -> Path:
    """Write the Python file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{module_name}.py"
    path.write_text("\n".join(src_lines) + "\n")
    return path
