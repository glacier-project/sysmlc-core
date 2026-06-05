from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Final

import syside

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

def join_emitted_actions(actions: list[str]) -> str:
    """Join emitted action sources in declaration order."""
    return "\n".join(action for action in actions if action)

def _assignment_target_base(
    assign: syside.AssignmentActionUsage,
) -> str | None:
    """Return a chained assignment target's base feature name, if any."""
    target_feature = _assignment_target_parameter(assign)
    if target_feature is None:
        return None
    for rel in target_feature.owned_relationships.collect():
        if not isinstance(rel, syside.Specialization):
            continue
        general = rel.general
        if general is None or general.name is None:
            continue
        qn = (
            ""
            if general.qualified_name is None
            else str(general.qualified_name)
        )
        if qn.startswith("Actions::"):
            continue
        return general.name
    return None


def _assignment_target_parameter(
    assign: syside.AssignmentActionUsage,
) -> syside.Feature | None:
    """Return the owned ``target`` parameter feature of an assignment."""
    for feature in assign.owned_features.collect():
        if feature.name == "target":
            return feature
    return None

class PyCodeGenError(ValueError):
    """Raised when the PyCodeGen encounters an unsupported node or other issue.

    This error may optionally carry a reference to the AST/model node that
    triggered the problem. Its string form includes the node type and, when
    available, a resolved name or qualified name to aid debugging.
    """

    def __init__(
        self, message: str, node: syside.Element | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.node = node

    def __str__(self) -> str:
        if self.node is None:
            return self.message
        node = self.node

        node_type = type(node).__name__
        node_repr = (
            node.qualified_name or node.name or node.textual_representations
        )

        return f"{self.message} (node {node_type} {node_repr})"


@dataclass(frozen=True)
class PyCodeGenContext:
    """Context for the PyCodeGen to carry through the generation process.

    This class can be extended with additional fields as needed to carry
    information through the generation process, such as references to the
    model, symbol tables, or configuration options.
    """
    indentation_length: int = 4
    string_delimiter: str = '"'

class PyCodeGen(ABC):
    """Generates Python source code from a SysML AST node.

    This class is designed to be extended with methods for handling specific 
    node types, and to be instantiated and called from a separate driver that 
    traverses the model and dispatches to the generator methods as needed. 
    The generator methods should raise PyCodeGenError when they encounter 
    unsupported nodes or other issues, and may include the offending node in 
    the exception for better error reporting.
    """
    def __init__(self, context: PyCodeGenContext | None = None) -> None:
        self._context = context or PyCodeGenContext()

    def emit_expression(self, expr: syside.Expression) -> str:
        """Translate ``expr`` to a Python source string.

        Public entry point for the sismic expression translator.

        Args:
            expr: The expression node to translate.

        Returns:
            Python source for ``expr``, with no enclosing parentheses.

        Raises:
            ValueError: If ``expr`` (or any sub-expression) is a node
                kind the emitter does not support.
        """
        return self._emit(expr)

    def emit_assignment(self, assign: syside.AssignmentActionUsage) -> str:
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
                node kind ``emit_expression`` does not support.
        """
        target = self.emit_assignment_target(assign)
        value = assign.value_expression
        if value is None:
            raise ValueError("AssignmentActionUsage has no value expression")
        return f"{target} = {self.emit_expression(value)}"

    def emit_assignment_target(self, assign: syside.AssignmentActionUsage) -> str:
        """Translate an assignment target to a Python assignment target.

        Args:
            assign: The ``assign <target> := <expr>`` action to inspect.

        Returns:
            Python source for the assignment target, e.g. ``counter`` or
            ``equipment.flag``.

        Raises:
            ValueError: If the assignment target has no resolved feature.
        """
        target = assign.referent
        if target is None or target.name is None:
            raise ValueError("AssignmentActionUsage has no resolved target")
        base = _assignment_target_base(assign)
        if base is None:
            return target.name
        return f"{base}.{target.name}"


    def emit_action(self, action: syside.ActionUsage) -> str:
        """Translate a supported action usage to typed emitted Python."""
        if isinstance(action, syside.AssignmentActionUsage):
            return self.emit_assignment(action)
        if isinstance(action, syside.SendActionUsage):
            return self.emit_send(action)
        raise PyCodeGenError(
            "unsupported action type", node=action
        )

    def emit_send(self, send: syside.SendActionUsage) -> str:
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
        raise NotImplementedError("emit_send must be implemented by subclasses")

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
        if isinstance(expr, syside.FeatureReferenceExpression):
            return self._emit_feature_reference(expr)

        raise ValueError(f"unsupported expression node: {type(expr).__name__}")


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
        """Emit a string literal as its Python ``repr``.

        ``repr`` yields a valid Python string literal with correct quoting
        and escaping.

        Args:
            expr: The literal node to translate.

        Returns:
            Python source for ``expr``.
        """
        quote = self._context.string_delimiter
        return f"{quote}{expr.value}{quote}"


    def _emit_feature_reference(self, expr: syside.FeatureReferenceExpression) -> str:
        """Emit a bare feature reference as the referent's simple name.

        Sismic resolves the name against the interpreter context at
        evaluate time, so a qualified name would be invalid Python here.

        Args:
            expr: The feature reference to translate.

        Returns:
            Python source for ``expr``.

        Raises:
            ValueError: If the referent has no resolved name.
        """
        ref = expr.referent
        if ref is None or ref.name is None:
            raise ValueError("FeatureReferenceExpression has no resolved referent")
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
            # Comparisons are non-associative in Python: 'a < b < c' is a single expression,
            # not '(a < b) < c'. So both sides get +1 to force parens around equal-precedence sub-expressions.
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
