from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final, override

import syside

from sysmlc.codegen.python import (
    ATOM_PRECEDENCE,
    LIBRARY_FUNCTIONS,
    PythonCodeGen,
    PythonCodeGenContext,
    payload_signature,
)
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine.interface import (
    send_receiver_is_own_port,
    send_via_port,
)
from sysmlc.sysml.queries import feature_value

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def _aliased_library_functions() -> dict[str, str]:
    """Alias every shared ``math.<name>`` rendering to ``_<name>``.

    Sismic copies the preamble context while checking contracts and
    Python modules are not copyable, so quake cannot ``import math``.
    The ``_`` namespace is reserved for generated machinery, so no
    model attribute can shadow the aliases.
    """
    aliased: dict[str, str] = {}
    for qualified_name, target in LIBRARY_FUNCTIONS.items():
        if target.startswith("math."):
            aliased[qualified_name] = "_" + target.removeprefix("math.")
        else:
            aliased[qualified_name] = target
    return aliased


def math_import_lines() -> list[str]:
    """Render the aliased ``from math import ...`` preamble line.

    Returns:
        One import line covering every ``math.``-backed rendering in the
        shared library table, or no lines when the table has none.
    """
    names = sorted(
        target.removeprefix("math.")
        for target in LIBRARY_FUNCTIONS.values()
        if target.startswith("math.")
    )
    if not names:
        return []
    aliases = ", ".join(f"{name} as _{name}" for name in names)
    return [f"from math import {aliases}"]


# The reserved runtime names shared across quake modules. Names with a
# single owner stay with that owner (the builder's `_tick_*`/`_n_*`/
# `_w_*`/`_d_*` families, the `_`-aliased math imports above).

# Context name of the injected part-system router: render_send emits
# calls to it, the coordinator binds one per interpreter.
ROUTER_CONTEXT_KEY = "_sysmlc_route"

# Kwarg on a time trigger's reminder event carrying the (source state,
# counter variable) pair its guard checks: the builder emits it, the
# coordinator reads it to purge stale reminders.
TICK_METADATA_KEY = "_sysmlc_tick"

_SCALAR_PY: Final[dict[str, str]] = {
    "Real": "float",
    "Rational": "float",
    "Integer": "int",
    "Natural": "int",
    "Boolean": "bool",
    "String": "str",
}


def py_type(attr: syside.AttributeUsage) -> str:
    """Map a declared attribute's type to a Python annotation.

    Mirrors ``sysmlc.backends.rosetta.codegen.py_type``: SysML scalars map
    to Python builtins, a nested composite maps to its own dataclass name,
    anything unmapped falls back to ``object``.
    """
    for definition in attr.attribute_definitions.collect():
        if definition.name in _SCALAR_PY:
            return _SCALAR_PY[definition.name]
        if (
            isinstance(definition, syside.AttributeDefinition)
            and definition.owned_attributes.collect()
        ):
            assert definition.name is not None
            return definition.name
    return "object"


class QuakeRenderNeeds:
    """Data the code generator fills and the builder reads back.

    Passed to every ``SismicCodeGen`` so snippets share it. It holds the
    external-import configuration, and collects two facts as snippets are
    rendered: the external names actually called, so only used imports are
    emitted, and the ``via`` sends dropped for lack of a system context.
    """

    def __init__(self) -> None:
        self.external_module: str | None = None
        self.external_names: frozenset[str] = frozenset()
        self.used_external: set[str] = set()
        self.undeliverable_sends: set[tuple[str, str]] = set()
        self.types_module: str | None = None
        self.dataclass_blocks: dict[str, tuple[str, ...]] = {}

    def register_external(self, *, module: str, names: frozenset[str]) -> None:
        """Record the --python module and the function names it provides."""
        self.external_module = module
        self.external_names = names

    def external_import_lines(self) -> list[str]:
        """Render sorted imports for the external functions actually called.

        A name that no rendered snippet invokes is not imported: the emitted
        statechart must not depend on the --python module on behalf of code
        that never uses it.
        """
        if self.external_module is None:
            return []
        return [
            f"from {self.external_module} import {name}"
            for name in sorted(self.used_external)
        ]

    def register_dataclass(self, name: str, lines: tuple[str, ...]) -> None:
        """Register a fully-rendered dataclass block by type name.

        Idempotent for identical blocks; a different block under the same
        name is a name collision and fails loud — same policy as rosetta's
        ``PreambleNeeds.register_dataclass``.
        """
        known = self.dataclass_blocks.get(name)
        if known is not None and known != lines:
            raise UnsupportedConstructError(
                f"two types share the simple name {name!r}; rename one."
            )
        self.dataclass_blocks[name] = lines

    @property
    def has_types(self) -> bool:
        """Whether any composite/item-def type was registered."""
        return bool(self.dataclass_blocks)

    def companion_module_lines(self) -> list[str]:
        """Render the companion ``<types_module>.py`` body, sorted by name.

        Returns:
            Lines of Python source, empty when no type was registered — no
            companion module is written or materialized in that case (see
            ``QuakeBackend.write`` and
            ``sysmlc.backends.quake.builder.attach_types_module``).
        """
        if not self.dataclass_blocks:
            return []
        lines = ["from dataclasses import dataclass", ""]
        for name in sorted(self.dataclass_blocks):
            lines.extend(self.dataclass_blocks[name])
            lines.append("")
        return lines

    def types_import_lines(self) -> list[str]:
        """Render the preamble-side ``from <types_module> import ...`` line."""
        if not self.dataclass_blocks:
            return []
        assert self.types_module is not None, (
            "types_module must be set before preamble assembly"
        )
        names = ", ".join(sorted(self.dataclass_blocks))
        return [f"from {self.types_module} import {names}"]

    def reset_call_tracking(self) -> None:
        """Clear the build call-tracking sets before building another machine.

        ``used_external`` and ``undeliverable_sends`` describe one machine's
        calls and drops, unlike ``dataclass_blocks``/``enum_defs``/
        ``types_module``, which accumulate across every machine sharing this
        instance (e.g. a part system's companion types module). Call this
        between builds that share one ``QuakeRenderNeeds`` so one machine's
        calls don't leak an import into another that never makes them.
        """
        self.used_external = set()
        self.undeliverable_sends = set()


def _enumeration_is_structured(
    definition: syside.EnumerationDefinition,
) -> bool:
    """Whether an enumeration definition carries attribute features.

    A plain or value-typed enumeration inherits only its implicit ``self``
    feature; a structured enumeration (one that specializes an attribute
    definition, like the official ``ClassificationKind``) inherits named
    attribute usages, whose per-literal ``:>>`` redefinitions cannot be
    projected to a single primitive value.

    Args:
        definition: The enumeration definition owning a referenced literal.

    Returns:
        True when the definition inherits any attribute usage feature.
    """
    for feature in definition.features.collect():
        if isinstance(feature, syside.AttributeUsage):
            return True
    return False


class SismicCodeGen(PythonCodeGen):
    """Python code generator for Sismic statecharts."""

    _library_functions: ClassVar[Mapping[str, str]] = (
        _aliased_library_functions()
    )

    def __init__(
        self,
        context: PythonCodeGenContext | None = None,
        *,
        needs: QuakeRenderNeeds | None = None,
        part_system_mode: bool = False,
        feature_aliases: Sequence[tuple[syside.Feature, str]] = (),
    ) -> None:
        """Initialize the generator.

        Args:
            context: General Python rendering context.
            needs: External import configuration shared by generated snippets.
            part_system_mode: True when the machine is built inside a part
                system, where ``send ... via <port>`` renders as a call to
                the injected router; false for a standalone statechart,
                where such a send is dropped.
            feature_aliases: Transition-local feature identities that should
                render as target runtime names. The comparison is by object
                identity so same-named SysML features in other scopes do not
                alias accidentally.
        """
        super().__init__(context)
        self._needs = needs if needs is not None else QuakeRenderNeeds()
        self._part_system_mode = part_system_mode
        self._feature_aliases = tuple(feature_aliases)

    @override
    def render_send(self, send: syside.SendActionUsage) -> str:
        """Translate a send action by its receiver semantics.

        The receiver decides the outcome: a ``via`` send routes over the
        port's connections in part-system mode, or is dropped (and recorded
        for a warning) when there is no part system to route it; a send
        directed ``to`` the machine's own port becomes sismic
        ``send('<Event>'[, <field>=<expr>, ...])``, which dispatches the
        signal to the machine itself as an internal event. Each positional
        constructor argument becomes a kwarg named by the payload attribute
        it binds to, in declaration order. The payload must be a typed
        ``new <Sig>(...)`` constructor; ``payload_signature`` rejects bare
        values.

        Args:
            send: The ``send new <Type>(<args>)`` action to translate.

        Returns:
            Python source for the resulting statement, or the empty string
            for a dropped ``via`` send.

        Raises:
            UnsupportedConstructError: If the send's ``to`` receiver is
                anything but the machine's own port; a single statechart
                cannot deliver cross-machine addressing.
            ValueError: If the payload is not a ``new <Type>(...)`` constructor
                resolving to a named definition, if an argument has no
                corresponding named attribute, or if an argument uses an
                expression shape the emitter rejects.
        """
        event_name, pairs = payload_signature(send)
        if send.receiver_argument is not None and not send_receiver_is_own_port(
            send
        ):
            raise UnsupportedConstructError(
                f"send {event_name!r} addresses a receiver that is not the "
                "machine's own port; cross-machine 'to' addressing is not "
                "supported. Route the signal with 'via <port>' and a "
                "connect instead.",
                node=send,
            )
        kwargs = ", ".join(
            f"{name}={self.render_expression(argument)}"
            for name, argument in pairs
        )
        delimiter = self._context.string_delimiter
        via_port = send_via_port(send)
        if via_port is not None:
            if not self._part_system_mode:
                self._needs.undeliverable_sends.add((event_name, via_port))
                return ""
            event = f"{delimiter}{event_name}{delimiter}"
            port = f"{delimiter}{via_port}{delimiter}"
            if kwargs:
                return f"{ROUTER_CONTEXT_KEY}({event}, {port}, {kwargs})"
            return f"{ROUTER_CONTEXT_KEY}({event}, {port})"
        if kwargs:
            return f"send({delimiter}{event_name}{delimiter}, {kwargs})"
        return f"send({delimiter}{event_name}{delimiter})"

    @override
    def _emit_feature_reference(
        self, expr: syside.FeatureReferenceExpression
    ) -> str:
        """Emit a bare reference, applying aliases and enum projection.

        A reference to the whole payload binding (``accept r : Reading`` then
        an effect using ``r`` on its own) renders as sismic's runtime
        ``event``, mirroring the field-access rewrite ``r.value`` ->
        ``event.value``.

        A reference to an enumeration literal renders as the literal's
        projected primitive value, never as a generated enum member; the
        projection rules live on ``_emit_enum_literal``.

        Raises:
            UnsupportedConstructError: If the literal belongs to a structured
                enumeration, whose per-literal attribute state has no single
                primitive projection.
            ValueError: If the referent has no resolved name.
        """
        ref = expr.referent
        alias = None if ref is None else self._feature_alias(ref)
        if alias is not None:
            return alias
        if isinstance(ref, syside.EnumerationUsage):
            return self._emit_enum_literal(ref)
        return super()._emit_feature_reference(expr)

    def _emit_enum_literal(self, literal: syside.EnumerationUsage) -> str:
        """Emit an enumeration literal as its projected primitive value.

        A literal with a declared value projects to that value's source
        (``LightColor::red`` -> ``"red"``, ``GradePoints::A`` -> ``4.0``);
        a plain symbolic literal (one whose enumeration declares no
        attributes) projects to its own name as a Python string
        (``Mode::idle`` -> ``"idle"``). Because plain literals project by
        name, two enumerations with same-named plain literals project to
        equal strings.

        Args:
            literal: The enumeration literal referenced in an expression.

        Returns:
            Python source for the literal's projected value.

        Raises:
            UnsupportedConstructError: If the literal belongs to a structured
                enumeration, whose per-literal attribute state has no single
                primitive projection.
            ValueError: If a plain literal has no resolved name.
        """
        value_expression = feature_value(literal)
        if value_expression is not None:
            # A literal with a declared value projects to that value's
            # source, emitted through the general expression grammar.
            return self._emit(
                value_expression, parent_precedence=ATOM_PRECEDENCE
            )
        owner = literal.owner
        if isinstance(
            owner, syside.EnumerationDefinition
        ) and _enumeration_is_structured(owner):
            name = owner.name or "<anonymous>"
            raise UnsupportedConstructError(
                f"enumeration {name!r} is structured (its literals carry "
                "attribute values); structured enumeration literals have no "
                "single primitive projection and are not supported.",
                node=literal,
            )
        # A plain symbolic literal projects to its own name as a string.
        if literal.name is None:
            raise ValueError("enumeration literal has no resolved name")
        delimiter = self._context.string_delimiter
        return f"{delimiter}{literal.name}{delimiter}"

    @override
    def _emit_feature_chain(self, expr: syside.FeatureChainExpression) -> str:
        """Emit a chained reference, applying transition-local aliases."""
        operands = expr.operands.collect()
        if operands and isinstance(
            operands[0], syside.FeatureReferenceExpression
        ):
            ref = operands[0].referent
            alias = None if ref is None else self._feature_alias(ref)
            if alias is not None:
                return self._emit_aliased_chain(expr, alias)
        return super()._emit_feature_chain(expr)

    def _emit_aliased_chain(
        self, expr: syside.FeatureChainExpression, alias: str
    ) -> str:
        """Emit ``alias.<chain>`` for a feature chain with an aliased root."""
        target = expr.target_feature
        if target is None:
            raise ValueError("FeatureChainExpression has no target feature")
        chain = target.chaining_features.collect() or [target]
        segments = [alias]
        for feature in chain:
            if feature.name is None:
                raise ValueError(
                    "FeatureChainExpression has an unnamed chain segment"
                )
            segments.append(feature.name)
        return ".".join(segments)

    @override
    def _emit_invocation(self, expr: syside.InvocationExpression) -> str:
        """Emit a shared library call or backend-specific calc-def call."""
        library_call = self._emit_library_invocation(expr)
        if library_call is not None:
            return library_call[0]
        external_call = self._emit_external_calculation_invocation(
            expr,
            external_module=self._needs.external_module,
            external_names=self._needs.external_names,
            used_external=self._needs.used_external,
        )
        if external_call is not None:
            return external_call
        func = expr.function
        qn = None if func is None else func.qualified_name
        raise UnsupportedConstructError(
            f"function {qn or '<unresolved>'!s} is not in quake's "
            "supported set.",
            node=expr,
        )

    def _feature_alias(self, feature: syside.Feature) -> str | None:
        """Return the runtime alias for ``feature``, if one is configured."""
        for candidate, alias in self._feature_aliases:
            if feature is candidate:
                return alias
        return None
