from __future__ import annotations

from typing import override

import syside

from ...generator.python.py_codegen import PyCodeGen, PyCodeGenContext


class SismicCodeGen(PyCodeGen):
    """Python code generator for Sismic statecharts."""

    def __init__(self, context: PyCodeGenContext | None = None) -> None:
        super().__init__(context)

    @override
    def emit_send(self, send: syside.SendActionUsage) -> str:
        """Translate a send action to a sismic ``send(...)`` call.

        Emits ``send('<Event>'[, <field>=<expr>, ...])``: ``<Event>`` is the
        payload type's name; each positional constructor argument
        becomes a kwarg named by the payload attribute it binds to, in
        declaration order.

        Bare-value sends are rejected; payload must be a typed new <Sig>(...)

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
        payload = send.payload_argument
        if not isinstance(payload, syside.ConstructorExpression):
            raise ValueError(
                "send payload is not a `new <Type>(...)` constructor"
            )
        event_type = payload.instantiated_type
        if not isinstance(event_type, syside.Definition):
            raise ValueError(
                "send payload type does not resolve to a definition"
            )
        event_name = event_type.name
        if event_name is None:
            raise ValueError("send payload type has no resolved name")
        attributes = event_type.owned_attributes.collect()
        arguments = payload.arguments.collect()
        # Each positional argument binds to the payload attribute at the same
        # position, in declaration order; a send may pass fewer arguments than
        # the type has attributes (KerML 8.3.4.8.7).
        kwargs: list[str] = []
        for index, argument in enumerate(arguments):
            if index >= len(attributes):
                raise ValueError(
                    "send payload has more args than the type has attributes"
                )
            name = attributes[index].name
            if name is None:
                raise ValueError(
                    "send payload binds an argument to an unnamed attribute"
                )
            kwargs.append(f"{name}={self.emit_expression(argument)}")
        delimiter = self._context.string_delimiter
        kwargs_str = ", ".join(kwargs)
        if kwargs:
            return f"send({delimiter}{event_name}{delimiter}, {kwargs_str})"
        return f"send({delimiter}{event_name}{delimiter})"
