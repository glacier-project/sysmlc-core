from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

import syside

from sysmlc.codegen.python import (
    LIBRARY_FUNCTIONS,
    PythonCodeGen,
    PythonCodeGenContext,
    payload_signature,
)
from sysmlc.errors import UnsupportedConstructError
from sysmlc.semantics.statemachine.interface import send_via_port

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


class QuakeRenderNeeds:
    """Tracks external imports configured for generated sismic snippets."""

    def __init__(self) -> None:
        self.external_module: str | None = None
        self.external_names: frozenset[str] = frozenset()
        self.used_external: set[str] = set()

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
        route_via_sends: bool = False,
        feature_aliases: Sequence[tuple[syside.Feature, str]] = (),
    ) -> None:
        """Initialize the generator.

        Args:
            context: General Python rendering context.
            needs: External import configuration shared by generated snippets.
            route_via_sends: Render ``send ... via <port>`` as calls to the
                injected part-system router instead of sismic ``send``.
            feature_aliases: Transition-local feature identities that should
                render as target runtime names. The comparison is by object
                identity so same-named SysML features in other scopes do not
                alias accidentally.
        """
        super().__init__(context)
        self._needs = needs if needs is not None else QuakeRenderNeeds()
        self._route_via_sends = route_via_sends
        self._feature_aliases = tuple(feature_aliases)

    @override
    def render_send(self, send: syside.SendActionUsage) -> str:
        """Translate a send action to a sismic ``send(...)`` call.

        Emits ``send('<Event>'[, <field>=<expr>, ...])``: ``<Event>`` is the
        payload type's name. Each positional constructor argument
        becomes a kwarg named by the payload attribute it binds to, in
        declaration order.

        Bare-value sends are rejected by ``payload_signature``. The payload
        must be a typed ``new <Sig>(...)`` constructor.

        Args:
            send: The ``send new <Type>(<args>)`` action to translate.

        Returns:
            Python source for the ``send(...)`` call.

        Raises:
            ValueError: If the payload is not a ``new <Type>(...)`` constructor
                resolving to a named definition, if an argument has no
                corresponding named attribute, or if an argument uses an
                expression shape the emitter rejects.
        """
        event_name, pairs = payload_signature(send)
        kwargs = ", ".join(
            f"{name}={self.render_expression(argument)}"
            for name, argument in pairs
        )
        delimiter = self._context.string_delimiter
        via_port = send_via_port(send)
        if self._route_via_sends and via_port is not None:
            event = f"{delimiter}{event_name}{delimiter}"
            port = f"{delimiter}{via_port}{delimiter}"
            if kwargs:
                return f"{ROUTER_CONTEXT_KEY}({event}, {port}, {kwargs})"
            return f"{ROUTER_CONTEXT_KEY}({event}, {port})"
        if kwargs:
            return f"send({delimiter}{event_name}{delimiter}, {kwargs})"
        return f"send({delimiter}{event_name}{delimiter})"

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
