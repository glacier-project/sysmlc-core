from __future__ import annotations

from typing import TYPE_CHECKING, override

import syside

from sysmlc.codegen.python import (
    PythonCodeGen,
    PythonCodeGenContext,
    payload_signature,
)
from sysmlc.errors import UnsupportedConstructError

if TYPE_CHECKING:
    from collections.abc import Sequence


class QuakeRenderNeeds:
    """Tracks external imports configured for generated sismic snippets."""

    def __init__(self) -> None:
        self.external_module: str | None = None
        self.external_names: frozenset[str] = frozenset()

    def register_external(self, *, module: str, names: frozenset[str]) -> None:
        """Record the --python module and the function names it provides."""
        self.external_module = module
        self.external_names = names

    def external_import_lines(self) -> list[str]:
        """Render sorted imports for all configured external functions."""
        if self.external_module is None:
            return []
        return [
            f"from {self.external_module} import {name}"
            for name in sorted(self.external_names)
        ]


class SismicCodeGen(PythonCodeGen):
    """Python code generator for Sismic statecharts."""

    def __init__(
        self,
        context: PythonCodeGenContext | None = None,
        *,
        needs: QuakeRenderNeeds | None = None,
        feature_aliases: Sequence[tuple[syside.Feature, str]] = (),
    ) -> None:
        """Initialize the generator.

        Args:
            context: General Python rendering context.
            needs: External import configuration shared by generated snippets.
            feature_aliases: Transition-local feature identities that should
                render as target runtime names. The comparison is by object
                identity so same-named SysML features in other scopes do not
                alias accidentally.
        """
        super().__init__(context)
        self._needs = needs if needs is not None else QuakeRenderNeeds()
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
            used_external=None,
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
