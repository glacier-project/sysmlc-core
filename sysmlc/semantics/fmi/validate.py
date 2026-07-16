from __future__ import annotations

import dataclasses
import logging
import math
from typing import TYPE_CHECKING, Any

from sysmlc.errors import FmuError

if TYPE_CHECKING:
    from pathlib import Path

    from sysmlc.semantics.fmi.extract import FmuPartNode

logger = logging.getLogger(__name__)

# SysML scalar type -> the FMI variable type it binds to, per FMI major
# version (FMI 2.0 keeps the SysML-facing names; 3.0 widened them).
FMI_TYPES: dict[str, dict[str, str]] = {
    "2": {
        "Real": "Real",
        "Integer": "Integer",
        "Boolean": "Boolean",
        "String": "String",
    },
    "3": {
        "Real": "Float64",
        "Integer": "Int32",
        "Boolean": "Boolean",
        "String": "String",
    },
}

SYSML_TYPES: dict[str, dict[str, str]] = {
    version: {fmi: sysml for sysml, fmi in mapping.items()}
    for version, mapping in FMI_TYPES.items()
}


def fmi_major_version(description: Any) -> str:
    """The archive's FMI major version (``"2"`` or ``"3"``)."""
    return str(description.fmiVersion).split(".", 1)[0]


_SETTABLE_CAUSALITIES = frozenset({"parameter", "input"})


def _settable_at_startup(actual: Any) -> bool:
    """Whether a variable accepts a startup value in initialization mode.

    Beyond ``parameter``/``input``, FMI (2.0 §2.2.7, 3.0 §2.4.7.5) lets
    initialization mode set ANY variable declared ``initial="exact"`` —
    the Reference-FMU idiom for overridable initial states published as
    ``output``/``local`` (VanDerPol's ``x0``/``x1``). Only startup
    values get this widening: an exposed *knob* is re-set between
    communication points, which exact-initial outputs do not allow.
    """
    return (
        actual.causality in _SETTABLE_CAUSALITIES
        or str(actual.initial) == "exact"
    )


def validate_fmu(node: FmuPartNode, path: Path | None = None) -> FmuPartNode:
    """Check ``node``'s declaration against its FMU archive.

    Args:
        node: The extracted FMU part declaration.
        path: The archive to read; defaults to the node's resolved path.

    Returns:
        The node with ``step_size`` resolved (as declared, or from the
        archive's DefaultExperiment) and ``exposed`` filled with the
        type-resolved exposed parameters/variables.

    Raises:
        FmuError: If the archive is missing or unreadable, is not FMI 3.0
            with co-simulation support, any bound variable, startup value,
            or exposed name is absent or mismatched in causality or type,
            or neither the declaration nor the archive gives a step size.
            fmpy being uninstalled is reported the same way, with the
            install hint.
    """
    archive = node.fmu_path if path is None else path
    if not archive.is_file():
        raise FmuError(
            f"FMU archive {str(archive)!r} for part def "
            f"{node.definition_name!r} does not exist."
        )
    description = checked_model_description(archive)
    version = fmi_major_version(description)
    problems = _variable_problems(node, description, version)
    problems += _parameter_problems(node, description, version)
    problems += _exposed_problems(node, description, version)
    if problems:
        listed = "\n".join(f"- {problem}" for problem in problems)
        raise FmuError(
            f"FMU {str(archive)!r} does not match the declaration of part "
            f"def {node.definition_name!r}:\n{listed}"
        )
    resolved = _resolve_step(node, description, archive)
    return dataclasses.replace(
        resolved,
        exposed=_resolve_exposed(node, description, version),
        fmi_version=version,
    )


def checked_model_description(archive: Path) -> Any:  # fmpy is untyped
    """Read ``archive``'s model description and check FMI 2.0/3.0 CS support.

    The shared entry point for every consumer of an FMU's interface
    (declaration validation, scaffolding).

    Raises:
        FmuError: If the archive is unreadable, not FMI 2.0/3.0, or has
            no co-simulation interface.
    """
    description = _read_model_description(archive)
    version = str(description.fmiVersion)
    if fmi_major_version(description) not in FMI_TYPES:
        raise FmuError(
            f"FMU {str(archive)!r} is FMI {version}; only FMI 2.0 and "
            "3.0 co-simulation FMUs are supported."
        )
    if description.coSimulation is None:
        raise FmuError(
            f"FMU {str(archive)!r} does not support co-simulation; only "
            "FMI 2.0 and 3.0 co-simulation FMUs are supported."
        )
    return description


def _read_model_description(archive: Path) -> Any:
    """Read the archive's model description via fmpy.

    Schema validation is off: the goal is interface conformance against
    the SysML declaration, not certifying the archive; fmpy's XSD pass
    also varies across FMU exporters.
    """
    try:
        from fmpy import read_model_description
    except ImportError as error:
        raise FmuError(
            "reading an FMU needs fmpy; install the extra: "
            "`uv sync --extra fmi` (or `pip install 'sysmlc[fmi]'`)."
        ) from error
    try:
        return read_model_description(str(archive), validate=False)
    except Exception as error:
        raise FmuError(
            f"cannot read the model description of {str(archive)!r}: {error}"
        ) from error


def _rank(variable: Any) -> int:
    """The variable's number of declared dimensions (0 = scalar).

    FMI 3.0 arrays have no SysML binding surface (payload attributes,
    startup values, and exposed nodes are all scalar); every consumer
    rejects them loudly rather than silently reading one element.
    """
    return len(getattr(variable, "dimensions", None) or [])


def _variable_problems(
    node: FmuPartNode, description: Any, version: str
) -> list[str]:
    """Collect every mismatch between the declaration and the FMU."""
    variables = {
        variable.name: variable for variable in description.modelVariables
    }
    problems: list[str] = []
    bound = [(signal, "input") for signal in node.inputs]
    bound += [(signal, "output") for signal in node.outputs]
    for signal, causality in bound:
        for var in signal.variables:
            actual = variables.get(var.name)
            if actual is None:
                problems.append(
                    f"variable {var.name!r} (payload of "
                    f"{signal.signal_name!r}) is not in the FMU"
                )
                continue
            problem = _causality_problem(var.name, actual, causality)
            if problem is not None:
                problems.append(problem)
            expected_type = FMI_TYPES[version][var.sysml_type]
            if actual.type != expected_type:
                problems.append(
                    f"variable {var.name!r} is {actual.type!r} in the FMU; "
                    f"SysML {var.sysml_type} binds to {expected_type!r}"
                )
            if _rank(actual) > 0:
                problems.append(
                    f"variable {var.name!r} is an array in the FMU; "
                    "array variables are not supported"
                )
    return problems


def _causality_problem(name: str, actual: Any, needed: str) -> str | None:
    """Check a bound variable's causality, or None if it fits.

    An ``input`` binding also accepts a ``tunable parameter``: FMI lets
    such a parameter be re-set between communication points, exactly
    what an in-signal does. An ``output`` binding also accepts a
    ``local``: exporters (Modelica tools, the Reference FMUs) routinely
    expose states as readable locals instead of declared outputs, and
    the typed getters read them all the same.
    """
    if actual.causality == needed:
        return None
    if (
        needed == "input"
        and actual.causality == "parameter"
        and actual.variability == "tunable"
    ):
        return None
    if needed == "output" and actual.causality == "local":
        return None
    if needed == "input":
        return (
            f"variable {name!r} has causality {actual.causality!r} "
            f"(variability {actual.variability!r}); an in-signal binds an "
            "FMU `input` or a `tunable` `parameter`"
        )
    return (
        f"variable {name!r} has causality {actual.causality!r}; an "
        "out-signal binds an FMU `output` or a readable `local`"
    )


def _parameter_problems(
    node: FmuPartNode, description: Any, version: str
) -> list[str]:
    """Collect every mismatch between startup values and the FMU."""
    variables = {
        variable.name: variable for variable in description.modelVariables
    }
    problems: list[str] = []
    for parameter in node.parameters:
        actual = variables.get(parameter.name)
        if actual is None:
            problems.append(
                f"startup value {parameter.name!r} is not in the FMU"
            )
            continue
        if not _settable_at_startup(actual):
            problems.append(
                f"startup value {parameter.name!r} has causality "
                f"{actual.causality!r} (initial {str(actual.initial)!r}) in "
                "the FMU; only `parameter`/`input` variables and variables "
                'declared initial="exact" can be set at startup'
            )
        if _rank(actual) > 0:
            problems.append(
                f"startup value {parameter.name!r} is an array in the FMU; "
                "array variables are not supported"
            )
        expected_type = FMI_TYPES[version][parameter.sysml_type]
        if actual.type != expected_type:
            problems.append(
                f"startup value {parameter.name!r} is {actual.type!r} in "
                f"the FMU; SysML {parameter.sysml_type} binds to "
                f"{expected_type!r}"
            )
    return problems


def _exposed_problems(
    node: FmuPartNode, description: Any, version: str
) -> list[str]:
    """Collect every mismatch between exposed names and the FMU.

    An exposed **parameter** must exist and be settable (causality
    ``parameter`` or ``input``); an exposed **variable** must exist (any
    causality). Both must carry a data-model-renderable scalar type.
    """
    variables = {
        variable.name: variable for variable in description.modelVariables
    }
    supported = ", ".join(sorted(SYSML_TYPES[version]))
    problems: list[str] = []

    def _exposed_shape_problems(kind: str, name: str, actual: Any) -> None:
        if actual.type not in SYSML_TYPES[version]:
            problems.append(
                f"{kind} {name!r} is {actual.type!r} in the FMU; "
                f"only {supported} variables can be exposed"
            )
        if _rank(actual) > 0:
            problems.append(
                f"{kind} {name!r} is an array in the FMU; "
                "array variables are not supported"
            )

    for name in node.exposed_parameters:
        actual = variables.get(name)
        if actual is None:
            problems.append(f"exposed parameter {name!r} is not in the FMU")
            continue
        if actual.causality not in _SETTABLE_CAUSALITIES:
            problems.append(
                f"exposed parameter {name!r} has causality "
                f"{actual.causality!r}; only `parameter` and `input` "
                "variables are settable"
            )
        _exposed_shape_problems("exposed parameter", name, actual)
    for name in node.exposed_variables:
        actual = variables.get(name)
        if actual is None:
            problems.append(f"exposed variable {name!r} is not in the FMU")
            continue
        _exposed_shape_problems("exposed variable", name, actual)
    return problems


def _resolve_exposed(
    node: FmuPartNode, description: Any, version: str
) -> tuple[Any, ...]:
    """Resolve exposed names to typed :class:`FmuExposed` entries.

    Called only after ``_exposed_problems`` passes, so every name exists
    with a supported type.
    """
    from sysmlc.semantics.fmi.extract import FmuExposed

    variables = {
        variable.name: variable for variable in description.modelVariables
    }
    types = SYSML_TYPES[version]
    resolved = [
        FmuExposed(name, types[variables[name].type], settable=True)
        for name in node.exposed_parameters
    ]
    resolved += [
        FmuExposed(name, types[variables[name].type], settable=False)
        for name in node.exposed_variables
    ]
    return tuple(resolved)


def _resolve_step(
    node: FmuPartNode, description: Any, archive: Path
) -> FmuPartNode:
    """Fill an omitted ``stepSize`` from the archive's DefaultExperiment."""
    if node.step_size is not None:
        return node
    experiment = description.defaultExperiment
    step = getattr(experiment, "stepSize", None)
    if step is None:
        raise FmuError(
            f"part def {node.definition_name!r} declares no stepSize and "
            f"FMU {str(archive)!r} has no DefaultExperiment stepSize to "
            "fall back to; declare the communication interval in the "
            "FmuImport metadata."
        )
    step = float(step)
    if not math.isfinite(step) or step <= 0:
        raise FmuError(
            f"FMU {str(archive)!r} declares DefaultExperiment stepSize "
            f"{step!r}; the communication interval must be a positive "
            "finite number of seconds. Override it with `stepSize` in "
            "the FmuImport metadata."
        )
    logger.info(
        "part def %s: stepSize %s taken from the FMU's DefaultExperiment",
        node.definition_name,
        step,
    )
    return dataclasses.replace(node, step_size=step)
