from __future__ import annotations

from typing import TYPE_CHECKING, override

from sysmlc.codegen.python import PythonCodeGen, payload_signature

if TYPE_CHECKING:
    import syside


class SismicCodeGen(PythonCodeGen):
    """Python code generator for Sismic statecharts."""

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
