from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine.interface import MachineInterface
from sysmlc.sysml import metadata

FMU_IMPORT_QN = "FmuBinding::FmuImport"

FMU_BEHAVIOR_QN = "ModelBasedDesign::MBDSemanticMetadata::FMUBehaviorDSM"
MBD_PARAMETER_QN = "ModelBasedDesign::MBDSemanticMetadata::MBDParameterDSM"
EXECUTABLE_MODEL_QN = "ModelBasedDesign::ExecutableModelMetadata"
BEHAVIORAL_MODEL_QN = "ModelBasedDesign::BehavioralModelMetadata"

_SUPPORTED_SCALARS = frozenset({"Real", "Integer", "Boolean", "String"})

_SCALARS_TEXT = "Real, Integer, Boolean, or String"


@dataclass(frozen=True)
class FmuVariable:
    """One payload attribute bound to the FMU variable of the same name."""

    name: str
    sysml_type: str


@dataclass(frozen=True)
class FmuParameter:
    """One part-def attribute configuring the FMU variable of its name.

    The value is applied with the typed FMI setter once at startup,
    before the first communication point; the archive variable must have
    causality ``parameter`` or ``input``.
    """

    name: str
    sysml_type: str
    value: float | int | bool | str


@dataclass(frozen=True)
class FmuExposed:
    """One FMU variable published on the Frost data model without a signal.

    Resolved by :func:`sysmlc.semantics.fmi.validate_fmu` from the declared
    ``exposedParameters``/``exposedVariables`` names against the archive:
    ``sysml_type`` picks the data-model node type; ``settable`` is True
    for an exposed parameter (a knob), False for a read-only variable.
    """

    name: str
    sysml_type: str
    settable: bool


@dataclass(frozen=True)
class FmuSignal:
    """One directed signal of the FMU interface.

    ``signal_name`` is the identity the routing layer matches on: the
    payload item def's simple name, or — for a scalar ``#fmu_behavior``
    parameter — the parameter (= FMU variable) name. ``port`` is the FMU
    part's port the signal travels through. ``payload_def`` is None for
    a scalar parameter signal: its single-field payload dataclass is
    synthesized by the backend instead of rendered from an item def.
    """

    signal_name: str
    port: str
    variables: tuple[FmuVariable, ...]
    payload_def: syside.ItemDefinition | None


@dataclass(frozen=True)
class FmuPartNode:
    """One nested FMU part: its identity, archive, step, and interface.

    ``fmu_path`` is the ``.fmu`` archive resolved against the declaring
    ``.sysml`` file's directory; ``declared_path`` preserves the text as
    written. ``outputs`` are signals the FMU emits each communication
    point; ``inputs`` are signals that set FMU inputs.

    ``step_size`` is ``None`` when the declaration omits ``stepSize``;
    validation resolves it from the archive's DefaultExperiment.
    ``stop_time`` is the declared experiment length (-> the program's LF
    timeout), ``parameters`` the startup values for FMU variables.
    ``tolerance`` and ``start_time`` seed the FMU's initialization mode
    (``None`` / ``0.0`` leave the FMI defaults). ``exposed_parameters``
    and ``exposed_variables`` name FMU variables published on the Frost
    data model without a signal: settable knobs and read-only probes.
    ``exposed`` is their type-resolved form, and ``fmi_version`` the
    archive's major version (``"2"`` or ``"3"``) — both filled by
    ``validate_fmu`` (the declaration itself is version-agnostic).
    """

    usage_name: str
    definition_name: str
    fmu_path: Path
    declared_path: str
    step_size: float | None
    ports: tuple[str, ...]
    outputs: tuple[FmuSignal, ...]
    inputs: tuple[FmuSignal, ...]
    stop_time: float | None = None
    parameters: tuple[FmuParameter, ...] = ()
    tolerance: float | None = None
    start_time: float | None = None
    exposed_parameters: tuple[str, ...] = ()
    exposed_variables: tuple[str, ...] = ()
    exposed: tuple[FmuExposed, ...] = ()
    fmi_version: str | None = None

    def face(self) -> MachineInterface:
        """The FMU's signal surface, in routing's interface vocabulary.

        Unlike a machine's face (derived from its behavior), an FMU face
        derives from the declaration itself, so every via-port is a
        declared port by construction.
        """
        accepted_via: dict[str | None, set[str]] = {}
        sent_via: dict[str | None, set[str]] = {}
        for signal in self.inputs:
            accepted_via.setdefault(signal.port, set()).add(signal.signal_name)
        for signal in self.outputs:
            sent_via.setdefault(signal.port, set()).add(signal.signal_name)
        return MachineInterface(
            accepted=frozenset(s.signal_name for s in self.inputs),
            sent=frozenset(s.signal_name for s in self.outputs),
            accepted_via={
                port: frozenset(signals)
                for port, signals in accepted_via.items()
            },
            sent_via={
                port: frozenset(signals) for port, signals in sent_via.items()
            },
        )


def fmu_import_definition(
    model: syside.Model,
) -> syside.MetadataDefinition | None:
    """Resolve the bundled ``FmuImport`` metadata def, or None if absent.

    The definition ships as a bundled library, so it is present in every
    model loaded through :func:`sysmlc.sysml.loading.load_model`; ``None``
    covers models assembled through other paths.
    """
    try:
        return metadata.resolve_metadata_definition(model, FMU_IMPORT_QN)
    except ValueError:
        return None


def applied_fmu_metadata(
    definition: syside.PartDefinition,
    fmu_import: syside.MetadataDefinition,
) -> syside.MetadataUsage | None:
    """Return the part def's ``FmuImport`` application, if any."""
    return metadata.find_applied_metadata(definition, fmu_import)


def fmu_part_node(
    usage: syside.PartUsage,
    definition: syside.PartDefinition,
    applied: syside.MetadataUsage,
) -> FmuPartNode:
    """Extract one FMU part node; reject malformed declarations loudly.

    Raises:
        UnsupportedConstructError: If the metadata misses ``path``, gives
            a non-positive ``stepSize``/``stopTime``, the part def also
            exhibits a state, a port is untyped, an item is undirected, a
            payload attribute has an unsupported type, a parameter
            attribute is unvalued or shadows an in-signal variable (an
            out-signal overlap is the exact-initial idiom and is legal),
            an exposed name collides with a signal/startup/other list, or
            the declaration has no directed items at all.
    """
    def_name = definition.name or "<anonymous>"
    declared_path, step_size, stop_time, tolerance, start_time = (
        _metadata_values(applied, def_name)
    )
    _reject_exhibits(definition, def_name)
    ports, outputs, inputs = _interface(definition, def_name)
    if not outputs and not inputs:
        raise UnsupportedConstructError(
            f"FMU part def {def_name!r} declares no directed items on its "
            "ports; an FMU needs at least one `in item` or `out item` to "
            "exchange."
        )
    parameters = _parameters(definition, def_name)
    signal_variables = {
        variable.name
        for signal in (*outputs, *inputs)
        for variable in signal.variables
    }
    input_variables = {
        variable.name for signal in inputs for variable in signal.variables
    }
    for parameter in parameters:
        if parameter.name in input_variables:
            raise UnsupportedConstructError(
                f"attribute {parameter.name!r} of FMU part def "
                f"{def_name!r} names a variable already bound by an `in` "
                "port item; a variable is set by its in-signal or by a "
                "startup value, not both."
            )
    exposed_parameters = _string_list(applied, "exposedParameters")
    exposed_variables = _string_list(applied, "exposedVariables")
    _reject_exposed_collisions(
        exposed_parameters,
        exposed_variables,
        signal_variables,
        {p.name for p in parameters},
        def_name,
    )
    return FmuPartNode(
        usage_name=usage.name or "<anonymous>",
        definition_name=def_name,
        fmu_path=_resolve_path(definition, declared_path, def_name),
        declared_path=declared_path,
        step_size=step_size,
        ports=ports,
        outputs=outputs,
        inputs=inputs,
        stop_time=stop_time,
        parameters=parameters,
        tolerance=tolerance,
        start_time=start_time,
        exposed_parameters=exposed_parameters,
        exposed_variables=exposed_variables,
    )


def _string_list(
    applied: syside.MetadataUsage, attribute_name: str
) -> tuple[str, ...]:
    """Read a ``String[0..*]`` metadata attribute as a tuple of strings.

    syside renders a multi-element list ``("a", "b")`` as an
    ``OperatorExpression`` over ``LiteralString`` operands, but a single
    element ``("a")`` as a bare ``LiteralString`` — both are handled. An
    absent attribute yields ``()``.
    """
    for member in applied.owned_members.collect():
        if not isinstance(member, syside.Feature):
            continue
        if member.name != attribute_name:
            continue
        for rel in member.owned_relationships.collect():
            if not isinstance(rel, syside.FeatureValue) or rel.value is None:
                continue
            value = rel.value
            if isinstance(value, syside.LiteralString):
                return (value.value,)
            if isinstance(value, syside.OperatorExpression):
                return tuple(
                    operand.value
                    for operand in value.operands.collect()
                    if isinstance(operand, syside.LiteralString)
                )
    return ()


def _reject_exposed_collisions(
    exposed_parameters: tuple[str, ...],
    exposed_variables: tuple[str, ...],
    signal_variables: set[str],
    startup_parameters: set[str],
    def_name: str,
) -> None:
    """Reject exposed names that clash with a signal, startup, or list.

    An exposed name is a standalone data-model node; it may not also be a
    port-item variable (already published as a signal), a startup value,
    or appear in both exposed lists.
    """
    both = set(exposed_parameters) & set(exposed_variables)
    if both:
        raise UnsupportedConstructError(
            f"FMU part def {def_name!r} names {sorted(both)!r} as both an "
            "exposed parameter and an exposed variable; a name is one or "
            "the other."
        )
    for name in (*exposed_parameters, *exposed_variables):
        if name in signal_variables:
            raise UnsupportedConstructError(
                f"exposed name {name!r} of FMU part def {def_name!r} is "
                "already a port-item variable; it is published as its "
                "signal, not as a standalone exposed node."
            )
        if name in startup_parameters:
            raise UnsupportedConstructError(
                f"exposed name {name!r} of FMU part def {def_name!r} is "
                "already a startup value attribute; drop one."
            )


@dataclass(frozen=True)
class MbdDefinitions:
    """The resolved ODE4HERA Model-Based Design metadata definitions."""

    fmu_behavior: syside.MetadataDefinition
    mbd_parameter: syside.MetadataDefinition
    executable_model: syside.MetadataDefinition
    behavioral_model: syside.MetadataDefinition


def mbd_definitions(model: syside.Model) -> MbdDefinitions | None:
    """Resolve the bundled MBD metadata defs, or None if the lib is absent."""
    try:
        return MbdDefinitions(
            fmu_behavior=metadata.resolve_metadata_definition(
                model, FMU_BEHAVIOR_QN
            ),
            mbd_parameter=metadata.resolve_metadata_definition(
                model, MBD_PARAMETER_QN
            ),
            executable_model=metadata.resolve_metadata_definition(
                model, EXECUTABLE_MODEL_QN
            ),
            behavioral_model=metadata.resolve_metadata_definition(
                model, BEHAVIORAL_MODEL_QN
            ),
        )
    except ValueError:
        return None


def fmu_behavior_action(
    definition: syside.PartDefinition, mbd: MbdDefinitions
) -> syside.PerformActionUsage | None:
    """The part def's ``#fmu_behavior`` performed action, if any.

    Raises:
        UnsupportedConstructError: If several actions carry the
            annotation; one part is one FMU.
    """
    found: list[syside.PerformActionUsage] = []
    for member in definition.owned_members.collect():
        if not isinstance(member, syside.PerformActionUsage):
            continue
        if metadata.find_applied_metadata(member, mbd.fmu_behavior):
            found.append(member)
    if len(found) > 1:
        raise UnsupportedConstructError(
            f"part def {definition.name!r} declares "
            f"{len(found)} #fmu_behavior actions; a part is realized by "
            "exactly one FMU."
        )
    return found[0] if found else None


def mbd_fmu_part_node(
    usage: syside.PartUsage,
    definition: syside.PartDefinition,
    action: syside.PerformActionUsage,
    mbd: MbdDefinitions,
) -> FmuPartNode:
    """Extract one ODE4HERA-declared FMU part node; reject loudly.

    Raises:
        UnsupportedConstructError: If no ``externalModelLink`` names the
            archive, the part def does not declare exactly one port, the
            part def also exhibits a state, a parameter of the behavior
            has an unsupported type, an attribute lacks the
            ``#mbd_parameter`` annotation or a literal value, or the
            behavior declares no directed parameters at all.
    """
    def_name = definition.name or "<anonymous>"
    _reject_exhibits(definition, def_name)
    declared_path = _external_model_link(definition, action, mbd, def_name)
    step_size = _max_time_step(action, mbd, def_name)
    port = _single_port(definition, def_name)
    outputs, inputs = _behavior_signals(action, port, def_name)
    if not outputs and not inputs:
        raise UnsupportedConstructError(
            f"FMU part def {def_name!r} declares no `in`/`out` parameters "
            "on its #fmu_behavior action; an FMU needs at least one "
            "variable to exchange."
        )
    parameters = _mbd_parameters(definition, action, mbd, def_name)
    signal_variables = {
        variable.name
        for signal in (*outputs, *inputs)
        for variable in signal.variables
    }
    for parameter in parameters:
        if parameter.name in signal_variables:
            raise UnsupportedConstructError(
                f"#mbd_parameter {parameter.name!r} of FMU part def "
                f"{def_name!r} names a variable already bound by a "
                "behavior parameter; a variable is set by its signal or "
                "by a startup value, not both."
            )
    return FmuPartNode(
        usage_name=usage.name or "<anonymous>",
        definition_name=def_name,
        fmu_path=_resolve_path(definition, declared_path, def_name),
        declared_path=declared_path,
        step_size=step_size,
        ports=(port,),
        outputs=outputs,
        inputs=inputs,
        stop_time=None,
        parameters=parameters,
    )


def _metadata_literals(applied: syside.MetadataUsage) -> dict[str, object]:
    """All literal-valued members of a metadata application, by name."""
    values: dict[str, object] = {}
    for member in applied.owned_members.collect():
        if not isinstance(member, syside.Feature) or member.name is None:
            continue
        value = _literal_value(member)
        if value is not None:
            values[member.name] = value
    return values


def _external_model_link(
    definition: syside.PartDefinition,
    action: syside.PerformActionUsage,
    mbd: MbdDefinitions,
    def_name: str,
) -> str:
    """The declared archive path; the part def's metadata wins.

    ``externalModelLink`` lives on the part def's
    ``@ExecutableModelMetadata`` (the ODE4HERA idiom) or, inherited, on
    the action's ``@BehavioralModelMetadata``.
    """
    for element, meta_def in (
        (definition, mbd.executable_model),
        (action, mbd.behavioral_model),
    ):
        applied = metadata.find_applied_metadata(element, meta_def)
        if applied is None:
            continue
        link = _metadata_literals(applied).get("externalModelLink")
        if isinstance(link, str) and link:
            return link
    raise UnsupportedConstructError(
        f"FMU part def {def_name!r} gives no `externalModelLink` in its "
        "@ExecutableModelMetadata; name the .fmu archive."
    )


def _max_time_step(
    action: syside.PerformActionUsage,
    mbd: MbdDefinitions,
    def_name: str,
) -> float | None:
    """The action's ``maxTimeStep`` (the communication interval), if any."""
    applied = metadata.find_applied_metadata(action, mbd.behavioral_model)
    if applied is None:
        return None
    step = _metadata_literals(applied).get("maxTimeStep")
    if step is None:
        return None
    if not isinstance(step, (int, float)) or isinstance(step, bool):
        raise UnsupportedConstructError(
            f"FMU part def {def_name!r} declares maxTimeStep {step!r}; "
            "the communication interval must be a number of seconds."
        )
    step = float(step)
    if not math.isfinite(step) or step <= 0:
        raise UnsupportedConstructError(
            f"FMU part def {def_name!r} declares maxTimeStep {step!r}; "
            "the communication interval must be a positive finite number "
            "of seconds."
        )
    return step


def _single_port(definition: syside.PartDefinition, def_name: str) -> str:
    """The part def's one declared port (all signals travel through it)."""
    ports = [
        member.name
        for member in definition.owned_members.collect()
        if isinstance(member, syside.PortUsage) and member.name is not None
    ]
    if len(ports) != 1:
        raise UnsupportedConstructError(
            f"FMU part def {def_name!r} declares {len(ports)} ports; an "
            "ODE4HERA-declared FMU declares exactly one, through which "
            "every behavior parameter travels."
        )
    return ports[0]


def _behavior_signals(
    action: syside.PerformActionUsage, port: str, def_name: str
) -> tuple[tuple[FmuSignal, ...], tuple[FmuSignal, ...]]:
    """The action's directed parameters as FMU signals.

    A scalar parameter is one FMU variable travelling as its own
    single-attribute signal named after the parameter; a parameter typed
    by an item def groups that payload's attributes (the FmuBinding
    semantics). Undirected references are the library's own machinery
    and are skipped.
    """
    outputs: list[FmuSignal] = []
    inputs: list[FmuSignal] = []
    for member in action.owned_members.collect():
        if isinstance(member, syside.MetadataUsage):
            continue
        if not isinstance(member, syside.ReferenceUsage):
            continue
        if member.direction not in (
            syside.FeatureDirectionKind.In,
            syside.FeatureDirectionKind.Out,
        ):
            continue
        name = member.name
        if name is None:
            raise UnsupportedConstructError(
                f"a directed parameter of FMU part def {def_name!r}'s "
                "#fmu_behavior action has no name; parameters bind to "
                "FMU variables by name."
            )
        signal = _parameter_signal(member, name, port, def_name)
        if member.direction is syside.FeatureDirectionKind.Out:
            outputs.append(signal)
        else:
            inputs.append(signal)
    return tuple(outputs), tuple(inputs)


def _parameter_signal(
    member: syside.ReferenceUsage, name: str, port: str, def_name: str
) -> FmuSignal:
    """One directed behavior parameter as an FMU signal."""
    typings = member.owned_typings.collect()
    typed = typings[0].type if typings else None
    if isinstance(typed, syside.ItemDefinition) and typed.name is not None:
        return FmuSignal(
            signal_name=typed.name,
            port=port,
            variables=_variables(typed, def_name),
            payload_def=typed,
        )
    type_name = getattr(typed, "name", None)
    if type_name in _SUPPORTED_SCALARS:
        assert type_name is not None
        return FmuSignal(
            signal_name=name,
            port=port,
            variables=(FmuVariable(name=name, sysml_type=type_name),),
            payload_def=None,
        )
    raise UnsupportedConstructError(
        f"parameter {name!r} of FMU part def {def_name!r}'s #fmu_behavior "
        f"action is not typed by a supported scalar ({_SCALARS_TEXT}) "
        "or a named item def."
    )


def _mbd_parameters(
    definition: syside.PartDefinition,
    action: syside.PerformActionUsage,
    mbd: MbdDefinitions,
    def_name: str,
) -> tuple[FmuParameter, ...]:
    """``#mbd_parameter`` attributes (action or part def) = startup values.

    Any other attribute on either element is rejected — it has no
    meaning on an FMU part.
    """
    parameters: list[FmuParameter] = []
    for owner in (action, definition):
        for member in owner.owned_members.collect():
            if not isinstance(member, syside.AttributeUsage):
                continue
            name = member.name or "<anonymous>"
            if not metadata.find_applied_metadata(member, mbd.mbd_parameter):
                raise UnsupportedConstructError(
                    f"attribute {name!r} of FMU part def {def_name!r} "
                    "lacks the #mbd_parameter annotation; on an FMU part "
                    "only #mbd_parameter startup values are meaningful."
                )
            scalar = _scalar_type(member)
            if scalar is None:
                raise UnsupportedConstructError(
                    f"#mbd_parameter {name!r} of FMU part def {def_name!r} "
                    "has no supported scalar type; FMU startup values "
                    f"must be {_SCALARS_TEXT}."
                )
            expression = member.feature_value_expression
            value = (
                _expression_value(expression)
                if expression is not None
                else None
            )
            if value is None:
                raise UnsupportedConstructError(
                    f"#mbd_parameter {name!r} of FMU part def {def_name!r} "
                    "has no literal value; a startup value sets the FMU "
                    "variable of its name (`= <literal>`)."
                )
            parameters.append(
                FmuParameter(
                    name=name,
                    sysml_type=scalar,
                    value=_typed_value(value, scalar, name, def_name),
                )
            )
    return tuple(parameters)


def _metadata_values(
    applied: syside.MetadataUsage, def_name: str
) -> tuple[str, float | None, float | None, float | None, float | None]:
    """Read the ``FmuImport`` literals off the metadata.

    Returns ``(path, stepSize, stopTime, tolerance, startTime)``.
    ``stepSize`` may be omitted (validation falls back to the archive's
    DefaultExperiment); the rest are optional. ``stepSize``/``stopTime``/
    ``tolerance`` must be positive finite seconds when present;
    ``startTime`` must be finite and non-negative.
    """
    path: str | None = None
    numbers: dict[str, float] = {}
    for member in applied.owned_members.collect():
        if not isinstance(member, syside.Feature):
            continue
        value = _literal_value(member)
        if member.name == "path" and isinstance(value, str):
            path = value
        elif (
            member.name in ("stepSize", "stopTime", "tolerance", "startTime")
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            numbers[member.name] = float(value)
    if not path:
        raise UnsupportedConstructError(
            f"FMU part def {def_name!r} gives no `path` in its FmuImport "
            "metadata; name the .fmu archive."
        )
    for name, kind in (
        ("stepSize", "communication interval"),
        ("stopTime", "experiment length"),
        ("tolerance", "tolerance"),
    ):
        value = numbers.get(name)
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise UnsupportedConstructError(
                f"FMU part def {def_name!r} declares {name} {value!r}; the "
                f"{kind} must be a positive finite number of seconds."
            )
    start = numbers.get("startTime")
    if start is not None and (not math.isfinite(start) or start < 0):
        raise UnsupportedConstructError(
            f"FMU part def {def_name!r} declares startTime {start!r}; the "
            "FMI start time must be a finite non-negative number of seconds."
        )
    return (
        path,
        numbers.get("stepSize"),
        numbers.get("stopTime"),
        numbers.get("tolerance"),
        start,
    )


def _literal_value(member: syside.Feature) -> object | None:
    """The literal value bound to a metadata body member, if any."""
    for rel in member.owned_relationships.collect():
        if isinstance(rel, syside.FeatureValue) and rel.value is not None:
            return _expression_value(rel.value)
    return None


def _expression_value(expression: syside.Element) -> object | None:
    """A literal expression's Python value; handles the unary minus."""
    if isinstance(
        expression,
        (
            syside.LiteralString,
            syside.LiteralRational,
            syside.LiteralInteger,
            syside.LiteralBoolean,
        ),
    ):
        return expression.value
    if (
        isinstance(expression, syside.OperatorExpression)
        and expression.operator is syside.Operator.Minus
    ):
        operands = expression.operands.collect()
        if len(operands) == 1:
            value = _expression_value(operands[0])
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return -value
    return None


def _parameters(
    definition: syside.PartDefinition, def_name: str
) -> tuple[FmuParameter, ...]:
    """Collect the part def's attributes as FMU startup values.

    Every owned attribute must carry a supported scalar type and a
    literal value whose kind matches it; anything else is rejected — an
    attribute on an FMU part def has no other meaning.
    """
    from sysmlc.sysml.queries import fixed_multiplicity

    parameters: list[FmuParameter] = []
    for member in definition.owned_members.collect():
        if not isinstance(member, syside.AttributeUsage):
            continue
        name = member.name or "<anonymous>"
        scalar = _scalar_type(member)
        if scalar is None:
            raise UnsupportedConstructError(
                f"attribute {name!r} of FMU part def {def_name!r} has no "
                "supported scalar type; FMU startup values must be "
                f"{_SCALARS_TEXT}."
            )
        if fixed_multiplicity(member) != 1:
            raise UnsupportedConstructError(
                f"attribute {name!r} of FMU part def {def_name!r} declares "
                "a multiplicity; FMU array variables are not supported — "
                "startup values are scalars (the archive defaults stay)."
            )
        expression = member.feature_value_expression
        value = (
            _expression_value(expression) if expression is not None else None
        )
        if value is None:
            raise UnsupportedConstructError(
                f"attribute {name!r} of FMU part def {def_name!r} has no "
                "literal value; an FMU part attribute sets the FMU "
                "variable of its name at startup (`= <literal>`)."
            )
        parameters.append(
            FmuParameter(
                name=name,
                sysml_type=scalar,
                value=_typed_value(value, scalar, name, def_name),
            )
        )
    return tuple(parameters)


def _typed_value(
    value: object, scalar: str, name: str, def_name: str
) -> float | int | bool | str:
    """Coerce a literal to its declared scalar type, or reject."""
    if scalar == "Boolean" and isinstance(value, bool):
        return value
    if scalar == "String" and isinstance(value, str):
        return value
    if (
        scalar == "Integer"
        and isinstance(value, int)
        and not isinstance(value, bool)
    ):
        return value
    if (
        scalar == "Real"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        return float(value)
    raise UnsupportedConstructError(
        f"attribute {name!r} of FMU part def {def_name!r} is typed "
        f"{scalar} but valued {value!r}; the literal must match the "
        "declared scalar type."
    )


def _reject_exhibits(definition: syside.PartDefinition, def_name: str) -> None:
    for member in definition.owned_members.collect():
        if isinstance(member, syside.ExhibitStateUsage):
            raise UnsupportedConstructError(
                f"part def {def_name!r} both imports an FMU and exhibits a "
                "state; a part is either an FMU or a state machine, not "
                "both."
            )


def _interface(
    definition: syside.PartDefinition, def_name: str
) -> tuple[tuple[str, ...], tuple[FmuSignal, ...], tuple[FmuSignal, ...]]:
    """Collect the FMU part def's ports and directed signals."""
    ports: list[str] = []
    outputs: list[FmuSignal] = []
    inputs: list[FmuSignal] = []
    for member in definition.owned_members.collect():
        if not isinstance(member, syside.PortUsage) or member.name is None:
            continue
        ports.append(member.name)
        port_def = _port_definition(member, def_name)
        for item in port_def.owned_members.collect():
            if not isinstance(item, syside.ItemUsage):
                continue  # skips the ConjugatedPortDefinition member
            signal = _signal(item, member.name, def_name)
            if item.direction is syside.FeatureDirectionKind.Out:
                outputs.append(signal)
            else:
                inputs.append(signal)
    return tuple(ports), tuple(outputs), tuple(inputs)


def _port_definition(
    port: syside.PortUsage, def_name: str
) -> syside.PortDefinition:
    typings = port.owned_typings.collect()
    port_def = typings[0].type if typings else None
    if not isinstance(port_def, syside.PortDefinition):
        raise UnsupportedConstructError(
            f"port {port.name!r} of FMU part def {def_name!r} is untyped; "
            "type it with a port def declaring the FMU's `in`/`out` items."
        )
    return port_def


def _signal(item: syside.ItemUsage, port_name: str, def_name: str) -> FmuSignal:
    if item.direction not in (
        syside.FeatureDirectionKind.In,
        syside.FeatureDirectionKind.Out,
    ):
        raise UnsupportedConstructError(
            f"item {item.name!r} on FMU part def {def_name!r} has no "
            "`in`/`out` direction; an FMU port item must be directed."
        )
    typings = item.owned_typings.collect()
    payload = typings[0].type if typings else None
    if not isinstance(payload, syside.ItemDefinition) or payload.name is None:
        raise UnsupportedConstructError(
            f"item {item.name!r} on FMU part def {def_name!r} is not typed "
            "by a named item def; the item def carries the FMU variables."
        )
    return FmuSignal(
        signal_name=payload.name,
        port=port_name,
        variables=_variables(payload, def_name),
        payload_def=payload,
    )


def _variables(
    payload: syside.ItemDefinition, def_name: str
) -> tuple[FmuVariable, ...]:
    from sysmlc.sysml.queries import fixed_multiplicity

    variables: list[FmuVariable] = []
    for attr in payload.owned_attributes.collect():
        if attr.name is None:
            continue
        scalar = _scalar_type(attr)
        if scalar is None:
            raise UnsupportedConstructError(
                f"attribute {attr.name!r} of {payload.name!r} (FMU part "
                f"def {def_name!r}) has no supported scalar type; FMU "
                f"variables must be {_SCALARS_TEXT}."
            )
        if fixed_multiplicity(attr) != 1:
            raise UnsupportedConstructError(
                f"attribute {attr.name!r} of {payload.name!r} (FMU part "
                f"def {def_name!r}) declares a multiplicity; FMU array "
                "variables are not supported — bind scalars only."
            )
        variables.append(FmuVariable(name=attr.name, sysml_type=scalar))
    return tuple(variables)


def _scalar_type(attr: syside.AttributeUsage) -> str | None:
    for definition in attr.attribute_definitions.collect():
        if definition.name in _SUPPORTED_SCALARS:
            return definition.name
    return None


def _resolve_path(
    definition: syside.PartDefinition, declared: str, def_name: str
) -> Path:
    """Resolve the ``.fmu`` path against the declaring file's directory."""
    declared_path = Path(declared)
    if declared_path.is_absolute():
        return declared_path
    url = str(definition.document.url)
    parsed = urlparse(url)
    if parsed.scheme != "file":
        raise UnsupportedConstructError(
            f"cannot resolve FMU path {declared!r} for part def "
            f"{def_name!r}: the declaring document has no file URL "
            f"({url!r})."
        )
    return (Path(url2pathname(parsed.path)).parent / declared_path).resolve()
