"""The language-neutral part of translating SysML expressions to source code.

:class:`ExpressionCodeGen` walks SysML expressions and actions and decides
their structure: which handler a node goes to, where parentheses are
needed, and how a function call is resolved. A subclass for one language
supplies the spelling: operator tokens and precedences, literals,
references, the assignment statement, and the library-function callees.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Final

import syside

from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.foreign_artifact.base import interpret_artifacts

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sysmlc.sysml.foreign_artifact.base import ForeignArtifact

logger = logging.getLogger(__name__)

COMPARISON_OPERATORS: Final[frozenset[syside.Operator]] = frozenset(
    {
        syside.Operator.Equals,
        syside.Operator.NotEquals,
        syside.Operator.Less,
        syside.Operator.LessEqual,
        syside.Operator.Greater,
        syside.Operator.GreaterEqual,
    }
)


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


class ExpressionCodeGen(ABC):
    """Translates SysML expressions and actions to one language's source.

    A subclass sets the class attributes below and implements the abstract
    ``_emit_*`` hooks and :meth:`_render_assignment_statement`. It may
    override any other ``_emit_*`` method to change how one kind of node
    is rendered.

    Attributes:
        _language_name: The language's display name, used in error
            messages. Lowercased, it is also the foreign-artifact language
            whose functions back external calc-def calls.
        _error_type: The error raised for an unsupported construct.
        _binary_operators: Each supported binary operator's token and
            precedence; a higher precedence binds tighter.
        _unary_operators: Each supported unary operator's token, including
            any space after it, and precedence.
        _library_functions: Each supported SysML library function's
            qualified name, mapped to the callee to emit.

    Args:
        external: The Foreign Artifacts available to back external calc-def
            calls, or None if none were provided.
    """

    _language_name: ClassVar[str]
    _error_type: ClassVar[type[UnsupportedConstructError]] = (
        UnsupportedConstructError
    )
    _binary_operators: ClassVar[Mapping[syside.Operator, tuple[str, int]]]
    _unary_operators: ClassVar[Mapping[syside.Operator, tuple[str, int]]]
    _library_functions: ClassVar[Mapping[str, str]] = {}

    def __init__(self, external: list[ForeignArtifact] | None = None) -> None:
        self._external: list[ForeignArtifact] = external or []
        self._used_external: dict[ForeignArtifact, set[str]] = {}
        self._external_symbols = interpret_artifacts(
            self._external, self._language_name
        )

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
        """Translate ``expr`` to source code.

        Args:
            expr: The expression node to translate.

        Returns:
            Source for ``expr``, with no enclosing parentheses.

        Raises:
            ValueError: If ``expr`` (or any sub-expression) is a node
                kind the emitter does not support.
        """
        return self._emit(expr)

    def render_assignment(self, assign: syside.AssignmentActionUsage) -> str:
        """Translate an assignment action to an assignment statement.

        Args:
            assign: The ``assign <target> := <expr>`` action to translate.

        Returns:
            Source for the assignment statement, as spelled by
            :meth:`_render_assignment_statement`.

        Raises:
            ValueError: If the assignment target has no resolved name, if the
                value expression is absent, or if the value expression is a
                node kind ``render_expression`` does not support.
        """
        target = self.render_assignment_target(assign)
        value = assign.value_expression
        if value is None:
            raise ValueError("AssignmentActionUsage has no value expression")
        return self._render_assignment_statement(
            target, self.render_expression(value)
        )

    def render_assignment_target(
        self, assign: syside.AssignmentActionUsage
    ) -> str:
        """Translate an assignment target to a dotted feature path.

        Args:
            assign: The ``assign <target> := <expr>`` action to inspect.

        Returns:
            Source for the assignment target, e.g. ``counter`` or
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
        """Translate a supported action usage to a statement.

        Args:
            action: An assignment or send action.

        Returns:
            Source for the action.

        Raises:
            UnsupportedConstructError: If the action is of another kind; the
                language's ``_error_type``.
        """
        if isinstance(action, syside.AssignmentActionUsage):
            return self.render_assignment(action)
        if isinstance(action, syside.SendActionUsage):
            return self.render_send(action)
        raise self._error_type("unsupported action type", node=action)

    def render_send(self, send: syside.SendActionUsage) -> str:
        """Translate a send action to a statement.

        How a send is delivered depends on the runtime the code targets, so
        a subclass that supports sends must override this method.

        Args:
            send: The ``send new <Type>(<args>)`` action to translate.

        Returns:
            Source for the send action.

        Raises:
            NotImplementedError: Always, unless overridden.
        """
        raise NotImplementedError(
            "render_send must be implemented by subclasses"
        )

    @abstractmethod
    def _render_assignment_statement(self, target: str, value: str) -> str:
        """Spell an assignment of ``value`` to ``target`` as a statement.

        Args:
            target: The rendered assignment target.
            value: The rendered value expression.

        Returns:
            The statement source.
        """

    @abstractmethod
    def _emit_literal_boolean(self, expr: syside.LiteralBoolean) -> str:
        """Emit a boolean literal."""

    @abstractmethod
    def _emit_literal_integer(self, expr: syside.LiteralInteger) -> str:
        """Emit an integer literal; always non-negative in SysML."""

    @abstractmethod
    def _emit_literal_rational(self, expr: syside.LiteralRational) -> str:
        """Emit a rational literal."""

    @abstractmethod
    def _emit_literal_string(self, expr: syside.LiteralString) -> str:
        """Emit a string literal, escaped for the language."""

    @abstractmethod
    def _emit_feature_reference(
        self, expr: syside.FeatureReferenceExpression
    ) -> str:
        """Emit a reference to a single feature."""

    @abstractmethod
    def _emit_feature_chain(self, expr: syside.FeatureChainExpression) -> str:
        """Emit a chained reference such as ``a.b.c``."""

    def _library_call_needs_math(self, callee: str) -> bool:
        """Return whether calling ``callee`` needs the math library.

        Args:
            callee: A callee from ``_library_functions``.

        Returns:
            False by default; a language whose math functions need an
            import or include overrides this.
        """
        return False

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
            Source for ``expr``.

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
        """Emit a library or external calc-def call; reject anything else.

        Raises:
            UnsupportedConstructError: If the called function is neither in
                ``_library_functions`` nor backed by a foreign artifact; the
                language's ``_error_type``.
        """
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
        raise self._error_type(
            f"function {qn or '<unresolved>'!s} is not in "
            f"{self._language_name} codegen's supported set.",
            node=expr,
        )

    def _emit_library_invocation(
        self, expr: syside.InvocationExpression
    ) -> tuple[str, bool] | None:
        """Emit a library function call from ``_library_functions``.

        Non-operator invocations are atoms, so no precedence wrapping is
        needed.

        Args:
            expr: The invocation expression to translate.

        Returns:
            ``(source, needs_math)`` for a function in
            ``_library_functions``, where ``needs_math`` comes from
            :meth:`_library_call_needs_math`; ``None`` for any other
            function.
        """
        func = expr.function
        qn = None if func is None else func.qualified_name
        callee = None if qn is None else self._library_functions.get(str(qn))
        if callee is None:
            return None
        args = ", ".join(
            self._emit(argument, 0) for argument in expr.arguments.collect()
        )
        return f"{callee}({args})", self._library_call_needs_math(callee)

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
            Source for the call when the invoked function resolves to a
            ``CalculationDefinition`` backed by one of the configured
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
                f"any of the provided external {self._language_name} "
                "artifacts.",
                node=expr,
            )
        return None

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
            Source for ``expr``.

        Raises:
            ValueError: If the operator value or arity is not supported.
        """
        op = expr.operator
        operands = expr.operands.collect()
        logger.debug("operator %s with %d operand(s)", op, len(operands))

        if op in self._binary_operators and len(operands) == 2:
            return self._emit_binary(expr, parent_precedence)
        if op in self._unary_operators and len(operands) == 1:
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
            Source for ``expr``, wrapped in parentheses when this
            operator's precedence is strictly less than
            ``parent_precedence``.
        """
        token, prec = self._binary_operators[expr.operator]
        operands = expr.operands.collect()
        if expr.operator in COMPARISON_OPERATORS:
            # A comparison operand that is itself a comparison always gets
            # parentheses: Python reads 'a < b < c' as a chain, not as
            # '(a < b) < c', and C compilers warn about it. So both sides
            # get +1 to force parens around equal-precedence operands.
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
        body = f"{lhs} {token} {rhs}"
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
            Source for ``expr``, wrapped in parentheses when this
            operator's precedence is strictly less than
            ``parent_precedence``.
        """
        token, prec = self._unary_operators[expr.operator]
        inner = self._emit(expr.operands.collect()[0], prec)
        body = f"{token}{inner}"
        return f"({body})" if prec < parent_precedence else body
