from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Final

import syside

from sysmlc.codegen.structured import named_fields
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine.bindings import (
    effective_value_relationship,
    is_constant,
)
from sysmlc.semantics.statemachine.facts import AttributeValue, CompositeValue
from sysmlc.sysml.foreign_artifact.base import interpret_artifacts
from sysmlc.sysml.queries import (
    definitions_of,
    is_scalar_quantity,
    structured_fields,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from sysmlc.sysml.foreign_artifact.base import ForeignArtifact

logger = logging.getLogger(__name__)

_BINARY_OPERATORS: Final[dict[syside.Operator, tuple[str, int]]] = {
    syside.Operator.Or: ("or", 1),
    syside.Operator.LogicalOr: ("or", 1),
    syside.Operator.And: ("and", 2),
    syside.Operator.LogicalAnd: ("and", 2),
    syside.Operator.Equals: ("==", 4),
    syside.Operator.NotEquals: ("!=", 4),
    syside.Operator.Less: ("<", 4),
    syside.Operator.LessEqual: ("<=", 4),
    syside.Operator.Greater: (">", 4),
    syside.Operator.GreaterEqual: (">=", 4),
    syside.Operator.Plus: ("+", 5),
    syside.Operator.Minus: ("-", 5),
    syside.Operator.Multiply: ("*", 6),
    syside.Operator.Divide: ("/", 6),
}

_UNARY_OPERATORS: Final[dict[syside.Operator, tuple[str, int]]] = {
    syside.Operator.Plus: ("+", 7),
    syside.Operator.Minus: ("-", 7),
    syside.Operator.Not: ("not ", 3),
}

_COMPARISON_OPERATORS: Final[frozenset[syside.Operator]] = frozenset(
    {
        syside.Operator.Equals,
        syside.Operator.NotEquals,
        syside.Operator.Less,
        syside.Operator.LessEqual,
        syside.Operator.Greater,
        syside.Operator.GreaterEqual,
    }
)

# Parent precedence strictly above every operator in the tables above.
ATOM_PRECEDENCE: Final[int] = (
    max(
        precedence
        for table in (_BINARY_OPERATORS, _UNARY_OPERATORS)
        for _, precedence in table.values()
    )
    + 1
)

# Maps a fully-qualified SysML function name to the Python call target.
# The single source of truth for the supported standard-library calls;
# backends that need different call targets derive their table from it.
LIBRARY_FUNCTIONS: Final[dict[str, str]] = {
    "NumericalFunctions::abs": "abs",
    "NumericalFunctions::max": "max",
    "NumericalFunctions::min": "min",
    "TrigFunctions::sin": "math.sin",
    "TrigFunctions::cos": "math.cos",
    "TrigFunctions::tan": "math.tan",
}


def join_statements(actions: list[str]) -> str:
    """Join emitted action sources in declaration order."""
    return "\n".join(action for action in actions if action)


@dataclass(frozen=True)
class PayloadField:
    """One effective field of a send's constructed payload and its value.

    Attributes:
        feature: The constructed type's effective attribute for the field;
            a redefinition stands in for the attribute it redefines.
        value: The field's value. When ``explicit``, the constructor
            argument bound to it. Otherwise the value the type gives it:
            its own or inherited default or bound value, a literal
            constant expression; for a structured field without one, other
            than a scalar quantity, a ``CompositeValue`` of its definition
            holding the values of the field's own fields, recursively,
            where the field's own redefinitions override its definition's;
            else ``None``, an unspecified value.
        explicit: Whether ``value`` is a constructor argument. An argument
            may read the sender's state, so it belongs to the send's
            evaluation, not to the payload type.
    """

    name: str
    feature: syside.AttributeUsage
    value: AttributeValue
    explicit: bool


def payload_signature(
    send: syside.SendActionUsage,
) -> tuple[str, list[tuple[str, syside.Expression]]]:
    """Return a send's payload type name and its constructor arguments.

    Each argument binds to the field that its constructor result feature
    redefines (KerML 8.3.4.8.3): a positional argument to the field at its
    position and a named argument to the named field, owned or inherited.
    A send may omit fields (KerML 8.3.4.8.7); they are not listed here,
    and :func:`payload_fields` also resolves their values from the type.

    Returns:
        The payload type's simple name, and one ``(field name, argument
        expression)`` pair per constructor argument, in argument order.

    Raises:
        ValueError: If the payload is not a ``new <Type>(...)`` constructor
            resolving to a named definition, or an argument does not bind
            exactly one named attribute.
    """
    constructor, _event_type, event_name = _payload_constructor(send)
    return event_name, [
        (_field_name(field), argument)
        for field, argument in _argument_bindings(constructor)
    ]


def payload_fields(send: syside.SendActionUsage) -> list[PayloadField]:
    """Return every effective field of a send's payload with its value.

    A constructor argument binds the field that its result feature
    redefines, as in :func:`payload_signature`. A field the constructor
    omits takes its value from the type: its own default or bound value,
    else the one it inherits through the attribute it redefines. An
    omitted structured field without such a value, other than a scalar
    quantity, is built from the values of its own fields.

    Constant eligibility is an extraction check, not a guarantee that the
    expression renderer supports the value. Literal quantity expressions,
    for example, still require quantity-operator rendering support.

    Returns:
        One entry per effective field of the constructed type: first the
        arguments, in the constructor's member order as
        :func:`payload_signature` lists them, then the omitted fields in
        the type's feature order, so emitting the entries in sequence
        evaluates the arguments in the constructor's member order. A type
        without fields yields no entries.

    Raises:
        ValueError: If the payload is not a ``new <Type>(...)`` constructor
            resolving to a named definition, or an argument does not bind
            exactly one effective field of the type.
        UnsupportedConstructError: If a structured type involved has an
            unnamed field or two distinct fields sharing a name, or the
            constructor omits a field whose value from the type is not a
            literal constant, at any depth, or whose structured definition
            is unnamed or contains itself. A non-constant value may refer
            to the payload's own features, so it cannot be evaluated with
            the send's arguments.
    """
    constructor, event_type, event_name = _payload_constructor(send)
    names = {field: name for name, field in named_fields(event_type)}
    resolved: list[PayloadField] = []
    for field, argument in _argument_bindings(constructor):
        name = names.pop(field, None)
        if name is None:
            raise ValueError(
                f"send payload argument {field.name!r} does not bind an "
                f"effective field of {event_name!r}"
            )
        resolved.append(PayloadField(name, field, argument, explicit=True))
    enclosing = frozenset({event_type})
    resolved.extend(
        PayloadField(name, field, _type_value(field, enclosing), explicit=False)
        for field, name in names.items()
    )
    return resolved


def _payload_constructor(
    send: syside.SendActionUsage,
) -> tuple[syside.ConstructorExpression, syside.Definition, str]:
    """Return a send's payload constructor, its definition and its name.

    Raises:
        ValueError: If the payload is not a ``new <Type>(...)`` constructor
            resolving to a named definition.
    """
    payload = send.payload_argument
    if not isinstance(payload, syside.ConstructorExpression):
        raise ValueError("send payload is not a `new <Type>(...)` constructor")
    event_type = payload.instantiated_type
    if not isinstance(event_type, syside.Definition):
        raise ValueError("send payload type does not resolve to a definition")
    event_name = event_type.name
    if event_name is None:
        raise ValueError("send payload type has no resolved name")
    return payload, event_type, event_name


def _argument_bindings(
    constructor: syside.ConstructorExpression,
) -> list[tuple[syside.AttributeUsage, syside.Expression]]:
    """Pair each constructor argument with the field it binds.

    Every owned feature of the constructor's result redefines the field
    its argument binds and holds the argument as its value, so arguments
    need not correspond one-to-one with the fields by position.

    Raises:
        ValueError: If a result feature does not redefine exactly one
            attribute or has no argument value.
    """
    result = constructor.result
    if result is None:
        raise ValueError("send payload constructor has no result")
    bindings: list[tuple[syside.AttributeUsage, syside.Expression]] = []
    for feature in result.owned_features.collect():
        redefined = [
            redefinition.redefined_feature
            for redefinition in feature.owned_redefinitions.collect()
        ]
        targets = [
            field
            for field in redefined
            if isinstance(field, syside.AttributeUsage)
        ]
        argument = feature.feature_value_expression
        if len(targets) != 1 or argument is None:
            raise ValueError(
                f"send payload argument {feature.name!r} does not bind "
                "exactly one attribute field of the constructed type"
            )
        bindings.append((targets[0], argument))
    return bindings


def _type_value(
    field: syside.AttributeUsage,
    enclosing: frozenset[syside.Definition],
) -> AttributeValue:
    """Return the value its type gives an omitted payload field.

    Args:
        field: The omitted effective field.
        enclosing: The structured definitions being built around
            ``field``, which a nested field must not contain again.

    Raises:
        UnsupportedConstructError: If a value is not a literal constant,
            or a nested structured definition is unnamed or recursive, or
            has an unnamed field or two distinct fields sharing a name.
    """
    relationship = effective_value_relationship(field)
    value = None if relationship is None else relationship.value
    if value is not None:
        if is_constant(value):
            return value
        raise UnsupportedConstructError(
            f"send omits field {_qualified(field)!r}, whose value from the "
            "type is not a literal constant; only Boolean, Integer, "
            "Rational and String literals, unary numeric signs, literal "
            "quantities and enumeration literals are eligible as omitted "
            "payload values. Emission also requires expression renderer "
            "support. Pass nonconstant values as constructor arguments.",
            node=field,
        )
    # A scalar quantity is one number, not a structure built from its
    # library definition's fields.
    if is_scalar_quantity(field):
        return None
    definition = next(
        (
            candidate
            for candidate in definitions_of(field)
            if isinstance(candidate, syside.AttributeDefinition)
            and structured_fields(candidate)
        ),
        None,
    )
    if definition is None:
        return None
    if definition.name is None or definition in enclosing:
        raise UnsupportedConstructError(
            f"send omits structured field {_qualified(field)!r}, whose "
            "definition is unnamed or recursive",
            node=field,
        )
    # The field's own redefinitions override its definition's fields; the
    # value keeps the definition's identity for its generated class.
    nested = enclosing | {definition}
    return CompositeValue(
        tuple(
            (name, _type_value(part, nested))
            for name, part in named_fields(field)
        ),
        definition.name,
        definition,
    )


def _field_name(field: syside.AttributeUsage) -> str:
    """Return a payload field's name.

    Raises:
        ValueError: If the field has no name.
    """
    if field.name is None:
        raise ValueError("send payload type has an unnamed field")
    return field.name


def _qualified(element: syside.Element) -> str:
    """Return an element's qualified name, or its name, for diagnostics."""
    return str(element.qualified_name or element.name)


def _target_base_features(
    expr: syside.Expression | None,
) -> list[syside.Feature]:
    """Return the resolved features an assignment's target argument reads.

    Raises:
        ValueError: If the target argument is not a resolved feature
            reference or feature chain.
    """
    if expr is None:
        return []
    if isinstance(expr, syside.FeatureReferenceExpression):
        if expr.referent is None:
            raise ValueError("assignment target base has no resolved referent")
        return [expr.referent]
    if isinstance(expr, syside.FeatureChainExpression):
        operands = expr.operands.collect()
        tail = expr.target_feature
        if not operands or tail is None:
            raise ValueError("assignment target base chain is unresolved")
        chain = tail.chaining_features.collect() or [tail]
        return [*_target_base_features(operands[0]), *chain]
    raise ValueError(
        f"unsupported assignment target base: {type(expr).__name__}"
    )


class PythonCodeGenError(UnsupportedConstructError):
    """Raised when the Python code generator does not support a construct."""


@dataclass(frozen=True)
class PythonCodeGenContext:
    """Context for the PythonCodeGen to carry through the generation process."""

    indentation_length: int = 4
    string_delimiter: str = '"'


class PythonCodeGen:
    """Generates Python source code from a SysML AST node.

    This class is designed to be extended with methods for handling specific
    node types, and to be instantiated and called from a separate driver that
    traverses the model and dispatches to the generator methods as needed.
    The generator methods should raise PythonCodeGenError when they encounter
    unsupported nodes or other issues, and may include the offending node in
    the exception for better error reporting.

    Args:
        context: A PythonCodeGenContext instance carrying information through
            the generation process, or None to use the default context.
        external: The Foreign Artifacts available to back external calc-def
            calls, or None if none were provided (e.g. no ``--python``
            module/metadata/textual representation for this model).
        definition_symbols: Frozen qualified-definition to Python-symbol map,
            or None to preserve legacy simple class names.
    """

    # The whitelist consulted by `_emit_library_invocation`. Subclasses
    # may override it to re-target renderings.
    _library_functions: ClassVar[Mapping[str, str]] = LIBRARY_FUNCTIONS

    def __init__(
        self,
        context: PythonCodeGenContext | None = None,
        external: list[ForeignArtifact] | None = None,
        *,
        definition_symbols: Mapping[str, str] | None = None,
    ) -> None:
        self.definition_symbols = dict(definition_symbols or {})
        self._context = context or PythonCodeGenContext()
        self._external: list[ForeignArtifact] = external or []
        self._used_external: dict[ForeignArtifact, set[str]] = {}
        self._external_symbols = interpret_artifacts(self._external, "python")

    @property
    def used_external(self) -> dict[ForeignArtifact, set[str]]:
        """Foreign artifacts and function names actually invoked so far.

        Populated incrementally as calc-def calls backed by an external
        artifact are emitted. Callers (typically a backend that needs to
        know which support modules to bundle) should read this only after
        generation is complete.
        """
        return self._used_external

    def render_expression(self, expr: syside.Expression) -> str:
        """Translate ``expr`` to a Python source string.

        Public entry point for the Python expression translator.

        Args:
            expr: The expression node to translate.

        Returns:
            Python source for ``expr``, with no enclosing parentheses.

        Raises:
            ValueError: If ``expr`` (or any sub-expression) is a node
                kind the emitter does not support.
        """
        return self._emit(expr)

    def render_value(
        self,
        value: AttributeValue,
        register: Callable[[syside.Definition], None] | None = None,
    ) -> str | None:
        """Translate a neutral attribute value to a Python source string.

        An expression renders through :meth:`render_expression`, a scalar
        quantity's SI magnitude as a float literal, and a structured value
        as a keyword construction of its definition's generated class,
        with its fields rendered by :meth:`render_fields`.

        Args:
            value: The value to translate.
            register: Called with a structured value's definition before
                its construction is rendered, so the caller can provide
                the generated class, or None when the caller already does.

        Returns:
            Python source for ``value``, or None when ``value`` is None.

        Raises:
            ValueError: If an expression (or any sub-expression) is a node
                kind the emitter does not support.
        """
        if value is None:
            return None
        if isinstance(value, CompositeValue):
            if register is not None:
                register(value.definition)
            fields = self.render_fields(value.fields, register)
            symbol = self.definition_symbols.get(
                str(value.definition.qualified_name), value.type_name
            )
            return f"{symbol}({fields})"
        if isinstance(value, float):
            return repr(value)
        return self.render_expression(value)

    def render_fields(
        self,
        fields: Iterable[tuple[str, AttributeValue]],
        register: Callable[[syside.Definition], None] | None = None,
    ) -> str:
        """Translate named field values to Python keyword arguments.

        Evaluating the result evaluates the values in ``fields`` order. A
        field whose value is None, unspecified, gets no argument, so a
        generated class keeps its own placeholder for it.

        Args:
            fields: ``(field name, value)`` pairs.
            register: Called with each nested structured value's
                definition, as for :meth:`render_value`.

        Returns:
            Comma-separated ``<name>=<source>`` keyword arguments; empty
            when no field has a value.

        Raises:
            ValueError: If an expression (or any sub-expression) is a node
                kind the emitter does not support.
        """
        arguments: list[str] = []
        for name, value in fields:
            rendered = self.render_value(value, register)
            if rendered is not None:
                arguments.append(f"{name}={rendered}")
        return ", ".join(arguments)

    def render_assignment(self, assign: syside.AssignmentActionUsage) -> str:
        """Translate an assignment action to a Python assignment statement.

        Emits ``<target> = <rhs>``, where ``<target>`` is the assigned
        feature path and ``<rhs>`` is the emitted value expression.

        Args:
            assign: The ``assign <target> := <expr>`` action to translate.

        Returns:
            Python source for the assignment statement.

        Raises:
            ValueError: If the assignment target has no resolved name, if the
                value expression is absent, or if the value expression is a
                node kind ``render_expression`` does not support.
        """
        target = self.render_assignment_target(assign)
        value = assign.value_expression
        if value is None:
            raise ValueError("AssignmentActionUsage has no value expression")
        return f"{target} = {self.render_expression(value)}"

    def render_assignment_target(
        self, assign: syside.AssignmentActionUsage
    ) -> str:
        """Translate an assignment target to a Python assignment target.

        Args:
            assign: The ``assign <target> := <expr>`` action to inspect.

        Returns:
            Python source for the assignment target, e.g. ``counter`` or
            ``equipment.flag``.

        Raises:
            ValueError: If the assignment target or a feature on its base
                path has no resolved name, or the base is not a feature
                reference or feature chain.
        """
        target = assign.referent
        if target is None or target.name is None:
            raise ValueError("AssignmentActionUsage has no resolved target")
        segments: list[str] = []
        for feature in _target_base_features(assign.target_argument):
            if feature.name is None:
                raise ValueError(
                    "assignment target base has an unnamed feature"
                )
            segments.append(feature.name)
        return ".".join([*segments, target.name])

    def render_action(self, action: syside.ActionUsage) -> str:
        """Translate a supported action usage to typed emitted Python."""
        if isinstance(action, syside.AssignmentActionUsage):
            return self.render_assignment(action)
        if isinstance(action, syside.SendActionUsage):
            return self.render_send(action)
        raise PythonCodeGenError("unsupported action type", node=action)

    def render_send(self, send: syside.SendActionUsage) -> str:
        """Translate a send action to the appropriate Python source.

        This method is abstract and must be implemented by subclasses to handle
        the specific translation logic for send actions, which may involve
        different patterns or libraries depending on the target Python
        environment or framework being used.

        Args:
            send: The ``send new <Type>(<args>)`` action to translate.

        Returns:
            Python source for the send action.
        """
        raise NotImplementedError(
            "render_send must be implemented by subclasses"
        )

    def _emit(self, expr: syside.Expression, parent_precedence: int = 0) -> str:
        """Dispatch ``expr`` to its node-type handler.

        Branch order respects syside's class hierarchy: more specific
        subclasses are matched before their parent classes.

        Args:
            expr: The expression node to translate.
            parent_precedence: Precedence of the enclosing operator. An
                operator handler wraps its output in parentheses when its
                own precedence is strictly less than this value.

        Returns:
            Python source for ``expr``.

        Raises:
            ValueError: If ``expr`` is a node kind the emitter does not
                support, or if any called handler raises.
        """
        logger.debug("dispatching %s", type(expr).__name__)

        if isinstance(expr, syside.LiteralBoolean):
            return self._emit_literal_boolean(expr)
        if isinstance(expr, syside.LiteralRational):
            return self._emit_literal_rational(expr)
        if isinstance(expr, syside.LiteralInteger):
            return self._emit_literal_integer(expr)
        if isinstance(expr, syside.LiteralString):
            return self._emit_literal_string(expr)
        if isinstance(expr, syside.FeatureChainExpression):
            return self._emit_feature_chain(expr)
        if isinstance(expr, syside.OperatorExpression):
            return self._emit_operator(expr, parent_precedence)
        if isinstance(expr, syside.InvocationExpression):
            return self._emit_invocation(expr)
        if isinstance(expr, syside.FeatureReferenceExpression):
            return self._emit_feature_reference(expr)

        raise ValueError(f"unsupported expression node: {type(expr).__name__}")

    def _emit_invocation(self, expr: syside.InvocationExpression) -> str:
        """Emit a supported library call; reject anything else."""
        library_call = self._emit_library_invocation(expr)
        if library_call is not None:
            return library_call[0]

        external_call = self._emit_external_calculation_invocation(
            expr, external=self._external, used_external=self._used_external
        )
        if external_call is not None:
            return external_call

        func = expr.function
        qn = None if func is None else func.qualified_name
        raise PythonCodeGenError(
            f"function {qn or '<unresolved>'!s} is not in Python codegen's "
            "supported set.",
            node=expr,
        )

    def _emit_library_invocation(
        self, expr: syside.InvocationExpression
    ) -> tuple[str, bool] | None:
        """Emit a library function call from the class's whitelist.

        Non-operator invocations are atoms, so no precedence wrapping is
        needed.

        Args:
            expr: The invocation expression to translate.

        Returns:
            ``(source, needs_math)`` for calls in the class's
            library-function whitelist, or ``None`` when the invocation
            is not in it.
        """
        func = expr.function
        qn = None if func is None else func.qualified_name
        target = None if qn is None else self._library_functions.get(str(qn))
        if target is None:
            return None
        args = ", ".join(
            self._emit(argument, 0) for argument in expr.arguments.collect()
        )
        return f"{target}({args})", target.startswith("math.")

    def _emit_external_calculation_invocation(
        self,
        expr: syside.InvocationExpression,
        *,
        external: list[ForeignArtifact],
        used_external: dict[ForeignArtifact, set[str]],
    ) -> str | None:
        """Emit a simple-name-backed external calc-def call, if applicable.

        Looks up the invoked calc-def's name against every configured
        consumer-interpreted function names and requires
        an unambiguous match. Records the match in ``used_external`` so a
        caller can later tell which artifacts/functions were actually
        exercised.

        Returns:
            Python source for the call when the invoked function resolves
            to a ``CalculationDefinition`` backed by one of the configured
            external artifacts; ``None`` when the invocation isn't a
            calc-def call at all (so the caller can try other handlers or
            report an "unsupported" error).

        Raises:
            UnsupportedConstructError: If external artifacts were
                configured but none of them declares a function matching
                the invoked calc-def's name.
        """
        func = expr.function
        if not (
            isinstance(func, syside.CalculationDefinition)
            and func.name is not None
        ):
            return None

        function_name = func.name
        for artifact in external:
            if function_name not in self._external_symbols.get(
                artifact, frozenset()
            ):
                continue

            used_external.setdefault(artifact, set()).add(function_name)

            args = ", ".join(
                self._emit(argument, 0) for argument in expr.arguments.collect()
            )
            return f"{function_name}({args})"

        if external:
            raise UnsupportedConstructError(
                f"calc def {function_name!r} has no backing function in "
                "any of the provided external Python artifacts.",
                node=expr,
            )
        return None

    def _emit_literal_boolean(self, expr: syside.LiteralBoolean) -> str:
        """Emit a boolean literal as ``"True"`` or ``"False"``.

        Args:
            expr: The literal node to translate.

        Returns:
            Python source for ``expr``.
        """
        return "True" if expr.value else "False"

    def _emit_literal_integer(self, expr: syside.LiteralInteger) -> str:
        """Emit an integer literal as its Python ``str``.

        Always non-negative; SysML wraps negatives in a unary minus.

        Args:
            expr: The literal node to translate.

        Returns:
            Python source for ``expr``.
        """
        return str(expr.value)

    def _emit_literal_rational(self, expr: syside.LiteralRational) -> str:
        """Emit a rational literal as its Python ``repr``.

        Args:
            expr: The literal node to translate.

        Returns:
            Python source for ``expr``.
        """
        return repr(expr.value)

    def _emit_literal_string(self, expr: syside.LiteralString) -> str:
        """Emit a string literal wrapped in the context's quote delimiter.

        The delimiter, backslashes, and the newline, carriage-return, and
        tab control characters are escaped so the emitted source is valid
        Python that evaluates back to the original string.

        Args:
            expr: The literal node to translate.

        Returns:
            Python source for ``expr``.
        """
        quote = self._context.string_delimiter
        value = expr.value
        value = value.replace("\\", "\\\\")
        value = value.replace(quote, "\\" + quote)
        value = value.replace("\n", "\\n")
        value = value.replace("\r", "\\r")
        value = value.replace("\t", "\\t")
        return f"{quote}{value}{quote}"

    def _emit_feature_reference(
        self, expr: syside.FeatureReferenceExpression
    ) -> str:
        """Emit a bare feature reference as the referent's name.

        The executing target resolves the bare name against its own
        evaluation context at run time, so a qualified name would be
        invalid Python here.

        Args:
            expr: The feature reference to translate.

        Returns:
            Python source for ``expr``.

        Raises:
            ValueError: If the referent has no resolved name.
        """
        ref = expr.referent
        if ref is None or ref.name is None:
            raise ValueError(
                "FeatureReferenceExpression has no resolved referent"
            )
        return ref.name

    def _emit_feature_chain(self, expr: syside.FeatureChainExpression) -> str:
        """Emit a chained reference as dotted Python attribute access.

        A chained reference ``a.b.c`` splits into a root (``operands[0]``,
        e.g. ``a``) and a tail (``target_feature``, e.g. ``b.c``): the tail is
        a single feature for one trailing segment, or a feature chain whose
        ``chaining_features`` are the segments for several.

        Args:
            expr: The feature-chain expression to translate.

        Returns:
            Python source for ``expr`` as ``<base>.<segment>[.<segment>...]``.

        Raises:
            ValueError: If the chain has no target feature, if a chain
                segment has no resolved name, or if the base operand is a
                node kind the emitter does not support.
        """
        base = self._emit(expr.operands.collect()[0], parent_precedence=0)
        target = expr.target_feature
        if target is None:
            raise ValueError("FeatureChainExpression has no target feature")
        chain = target.chaining_features.collect() or [target]
        segments = [base]
        for feature in chain:
            if feature.name is None:
                raise ValueError(
                    "FeatureChainExpression has an unnamed chain segment"
                )
            segments.append(feature.name)
        return ".".join(segments)

    def _emit_operator(
        self,
        expr: syside.OperatorExpression,
        parent_precedence: int,
    ) -> str:
        """Route ``expr`` to the binary or unary handler by operator arity.

        Args:
            expr: The operator expression to translate.
            parent_precedence: Precedence of the enclosing operator.

        Returns:
            Python source for ``expr``.

        Raises:
            ValueError: If the operator value or arity is not supported.
        """
        op = expr.operator
        operands = expr.operands.collect()
        logger.debug("operator %s with %d operand(s)", op, len(operands))

        if op in _BINARY_OPERATORS and len(operands) == 2:
            return self._emit_binary(expr, parent_precedence)
        if op in _UNARY_OPERATORS and len(operands) == 1:
            return self._emit_unary(expr, parent_precedence)

        raise ValueError(
            f"unsupported operator: {op!r} with {len(operands)} operand(s)"
        )

    def _emit_binary(
        self,
        expr: syside.OperatorExpression,
        parent_precedence: int,
    ) -> str:
        """Emit a binary operator expression as ``<lhs> <op> <rhs>``.

        Args:
            expr: The operator expression to translate.
            parent_precedence: Precedence of the enclosing operator.

        Returns:
            Python source for ``expr``, wrapped in parentheses when this
            operator's precedence is strictly less than
            ``parent_precedence``.
        """
        py_op, prec = _BINARY_OPERATORS[expr.operator]
        operands = expr.operands.collect()
        if expr.operator in _COMPARISON_OPERATORS:
            # Comparisons are non-associative in Python: 'a < b < c' is a
            # single expression, not '(a < b) < c'. So both sides get +1 to
            # force parens around equal-precedence sub-expressions.
            lhs_parent_precedence = prec + 1
            rhs_parent_precedence = prec + 1
        else:
            lhs_parent_precedence = prec
            # +1 forces parens around an equal-precedence RHS
            # (left-associativity): 'a - b - c' stays bare,
            # 'a - (b - c)' keeps its parens.
            rhs_parent_precedence = prec + 1
        lhs = self._emit(operands[0], lhs_parent_precedence)
        rhs = self._emit(operands[1], rhs_parent_precedence)
        body = f"{lhs} {py_op} {rhs}"
        return f"({body})" if prec < parent_precedence else body

    def _emit_unary(
        self,
        expr: syside.OperatorExpression,
        parent_precedence: int,
    ) -> str:
        """Emit a unary operator expression as ``<op><inner>``.

        Args:
            expr: The operator expression to translate.
            parent_precedence: Precedence of the enclosing operator.

        Returns:
            Python source for ``expr``, wrapped in parentheses when this
            operator's precedence is strictly less than
            ``parent_precedence``.
        """
        py_op, prec = _UNARY_OPERATORS[expr.operator]
        inner = self._emit(expr.operands.collect()[0], prec)
        body = f"{py_op}{inner}"
        return f"({body})" if prec < parent_precedence else body
