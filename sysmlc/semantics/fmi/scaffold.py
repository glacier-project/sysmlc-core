from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sysmlc.errors import FmuError
from sysmlc.semantics.fmi.validate import (
    SYSML_TYPES,
    checked_model_description,
    fmi_major_version,
)

if TYPE_CHECKING:
    from pathlib import Path

# A plain (unquoted) SysML identifier; a payload attribute name binds to
# the FMU variable name 1:1 and the binding layer has no quoting support.
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_READABLE = frozenset({"output", "local"})


@dataclass
class _Partition:
    """The FMU variables split into scaffold roles."""

    inputs: list[Any] = field(default_factory=list)
    outputs: list[Any] = field(default_factory=list)
    parameters: list[Any] = field(default_factory=list)
    exposable: list[Any] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def scaffold_sysml(archive: Path, fmu_reference: str) -> str:
    """Render the SysML declaration scaffold for ``archive``.

    Args:
        archive: The ``.fmu`` archive (FMI 2.0/3.0 co-simulation).
        fmu_reference: The ``path`` to emit in the ``FmuImport``
            metadata — relative to the ``.sysml`` file the caller will
            write, because that is how the extraction resolves it.

    Raises:
        FmuError: If the archive is missing, unreadable, or not an
            FMI 2.0/3.0 co-simulation FMU (fmpy uninstalled reports the
            same way, with the install hint).
    """
    if not archive.is_file():
        raise FmuError(f"FMU archive {str(archive)!r} does not exist.")
    description = checked_model_description(archive)
    version = fmi_major_version(description)
    types = SYSML_TYPES[version]
    name = _definition_name(str(description.modelName or archive.stem))
    # FrostFmu (FMI 3.0) enters and exits initialization mode with no
    # hook to apply startup values; only self-hosted FMI 2.0 parts get
    # startup attributes.
    partition = _partition(description, types, startup_values=version == "2")

    lines = [f"package {name}Fmu {{"]
    lines += _header_doc(archive, description, partition)
    lines += [
        "    private import ScalarValues::*;",
        "    private import FmuBinding::*;",
        "",
    ]
    lines += _item_def(f"{name}Inputs", partition.inputs, types, defaults=True)
    lines += _item_def(
        f"{name}Outputs", partition.outputs, types, defaults=False
    )
    lines += _port_def(
        name,
        has_inputs=bool(partition.inputs),
        has_outputs=bool(partition.outputs),
    )
    lines += _part_def(
        name,
        description,
        fmu_reference,
        partition,
        types,
        has_port=bool(partition.inputs or partition.outputs),
    )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _definition_name(model_name: str) -> str:
    """A SysML type name derived from the FMU's model name."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", model_name).lstrip("0123456789_")
    if not cleaned:
        cleaned = "Fmu"
    return cleaned[0].upper() + cleaned[1:]


def _doc_text(text: Any) -> str:
    """A description as a single-line SysML comment body."""
    return " ".join(str(text).split()).replace("*/", "* /")


def _is_exact_initial(variable: Any) -> bool:
    """An overridable initial state: exact initial with a start value."""
    return str(variable.initial) == "exact" and variable.start is not None


def _partition(
    description: Any, types: dict[str, str], *, startup_values: bool
) -> _Partition:
    """Split the FMU variables into scaffold roles (see module doc)."""
    supported = "/".join(sorted(types))
    parts = _Partition()
    for variable in description.modelVariables:
        if variable.causality == "independent":
            continue  # the time variable: published as the `time` node
        if variable.causality not in {"input", "output", "parameter", "local"}:
            parts.skipped.append(
                f"{variable.name} ({variable.causality}: not bindable)"
            )
            continue
        if getattr(variable, "dimensions", None):
            # FMI 3.0 arrays (vectors, matrices) have no binding surface;
            # validation rejects them the same way.
            parts.skipped.append(
                f"{variable.name} ({variable.causality}: array variables "
                "are not supported)"
            )
            continue
        if variable.type not in types:
            parts.skipped.append(
                f"{variable.name} ({variable.causality} {variable.type}: "
                f"only {supported} bind)"
            )
            continue
        if _IDENTIFIER.fullmatch(variable.name) is None:
            if variable.causality in _READABLE:
                parts.exposable.append(variable)
            else:
                parts.skipped.append(
                    f"{variable.name} ({variable.causality}: not a plain "
                    "SysML identifier)"
                )
            continue
        if variable.causality == "input":
            parts.inputs.append(variable)
        elif variable.causality in _READABLE:
            parts.outputs.append(variable)
            if startup_values and _is_exact_initial(variable):
                parts.parameters.append(variable)
        elif variable.start is None:
            parts.skipped.append(
                f"{variable.name} (parameter without a start value)"
            )
        elif startup_values:
            parts.parameters.append(variable)
        else:
            parts.skipped.append(
                f"{variable.name} (parameter: startup values are not "
                "supported on FMI 3.0 — FrostFmu applies none)"
            )
    return parts


def _header_doc(
    archive: Path, description: Any, partition: _Partition
) -> list[str]:
    lines = ["    doc /*"]
    model_doc = getattr(description, "description", None)
    if model_doc:
        lines += [f"         * {_doc_text(model_doc)}", "         *"]
    lines += [
        "         * Scaffolded by `sysmlc frostifier extract-fmu` from",
        f"         * {archive.name}. Attribute names bind to FMU variable",
        "         * names 1:1 — rename items, ports, and defs freely, but",
        "         * keep the attribute names. Split the single in/out items",
        "         * into semantically named signals as needed; readable",
        "         * `local` variables are scaffolded as outputs — prune",
        "         * the ones you don't need.",
    ]
    if partition.skipped:
        lines.append(
            "         * Not scaffolded (unbindable by the sysmlc pipeline):"
        )
        lines += [f"         *   - {note}" for note in partition.skipped]
    lines += ["         */", ""]
    return lines


def _attribute_lines(
    variable: Any,
    scalar: str,
    *,
    indent: str,
    default: str = "",
) -> list[str]:
    """One attribute declaration, with its description as a ``doc``."""
    head = f"{indent}attribute {variable.name} : {scalar}{default}"
    doc = getattr(variable, "description", None)
    if not doc:
        return [f"{head};"]
    return [f"{head} {{ doc /* {_doc_text(doc)} */ }}"]


def _item_def(
    item_name: str,
    variables: list[Any],
    types: dict[str, str],
    *,
    defaults: bool,
) -> list[str]:
    """One payload item def; inputs carry the FMU start values as defaults."""
    if not variables:
        return []
    lines = [f"    item def {item_name} {{"]
    for variable in variables:
        scalar = types[variable.type]
        default = ""
        if defaults and variable.start is not None:
            default = f" = {_literal(scalar, variable.start)}"
        lines += _attribute_lines(
            variable, scalar, indent="        ", default=default
        )
    lines += ["    }", ""]
    return lines


def _port_def(name: str, *, has_inputs: bool, has_outputs: bool) -> list[str]:
    """The FMU's signal surface; omitted when nothing binds."""
    if not (has_inputs or has_outputs):
        return []
    lines = [f"    port def {name}Port {{"]
    if has_outputs:
        lines.append(f"        out item outputs : {name}Outputs;")
    if has_inputs:
        lines.append(f"        in item inputs : {name}Inputs;")
    lines += ["    }", ""]
    return lines


def _part_def(
    name: str,
    description: Any,
    fmu_reference: str,
    partition: _Partition,
    types: dict[str, str],
    *,
    has_port: bool,
) -> list[str]:
    lines = [
        f"    part def {name} {{",
        "        metadata FmuImport {",
        f'            path = "{fmu_reference}";',
    ]
    experiment = description.defaultExperiment
    step = getattr(experiment, "stepSize", None)
    if step is not None:
        lines.append(f"            stepSize = {float(step)!r};")
    else:
        # Without a stepSize here or in the archive, validation rejects
        # the build; surface the gap where the modeler will edit.
        lines.append(
            "            // TODO stepSize = ...; (seconds — the archive "
            "has no DefaultExperiment stepSize to fall back to)"
        )
    start_time = getattr(experiment, "startTime", None)
    if start_time is not None and float(start_time) != 0.0:
        lines.append(f"            startTime = {float(start_time)!r};")
    stop = getattr(experiment, "stopTime", None)
    if stop is not None:
        lines.append(f"            stopTime = {float(stop)!r};")
    tolerance = getattr(experiment, "tolerance", None)
    if tolerance is not None:
        lines.append(f"            tolerance = {float(tolerance)!r};")
    if partition.exposable:
        listed = ", ".join(
            f'"{variable.name}"' for variable in partition.exposable
        )
        lines += [
            "            // Readable non-identifier variables: published",
            "            // on the Frost data model (Exposed/), no signal.",
            f"            exposedVariables = ({listed});",
        ]
    lines.append("        }")
    if partition.parameters:
        lines += [
            "        // FMU parameters and exact-initial states; the",
            "        // literal values are applied as startup values",
            "        // inside initialization mode.",
        ]
    for variable in partition.parameters:
        scalar = types[variable.type]
        default = f" = {_literal(scalar, variable.start)}"
        lines += _attribute_lines(
            variable, scalar, indent="        ", default=default
        )
    if has_port:
        lines.append(f"        port fmuPort : {name}Port;")
    lines.append("    }")
    return lines


def _literal(scalar: str, start: Any) -> str:
    """Render an FMU start value as the SysML literal of ``scalar``.

    fmpy surfaces start values as strings; booleans arrive as
    ``true``/``false``/``0``/``1``.
    """
    if scalar == "Boolean":
        return "true" if str(start).lower() in {"true", "1"} else "false"
    if scalar == "Integer":
        return str(int(str(start)))
    if scalar == "String":
        escaped = str(start).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return repr(float(str(start)))
