from __future__ import annotations

from typing import TYPE_CHECKING, override

import syside

from sysmlc.codegen.python import (
    PythonCodeGen,
    PythonCodeGenContext,
    payload_signature,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class SismicCodeGen(PythonCodeGen):
    """Python code generator for Sismic statecharts."""

    def __init__(
        self,
        context: PythonCodeGenContext | None = None,
        *,
        feature_aliases: Sequence[tuple[syside.Feature, str]] = (),
    ) -> None:
        """Initialize the generator.

        Args:
            context: General Python rendering context.
            feature_aliases: Transition-local feature identities that should
                render as target runtime names. The comparison is by object
                identity so same-named SysML features in other scopes do not
                alias accidentally.
        """
        super().__init__(context)
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

    def _feature_alias(self, feature: syside.Feature) -> str | None:
        """Return the runtime alias for ``feature``, if one is configured."""
        for candidate, alias in self._feature_aliases:
            if feature is candidate:
                return alias
        return None
