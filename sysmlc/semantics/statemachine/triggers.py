from __future__ import annotations

import math

import syside

from sysmlc.semantics.statemachine.facts import (
    AfterTrigger,
    AtTrigger,
    SignalTrigger,
    Trigger,
    WhenTrigger,
)


def trigger_invocation(
    trans: syside.TransitionUsage,
) -> syside.TriggerInvocationExpression | None:
    """Return the transition's trigger-invocation payload, or None.

    A time/change trigger (``accept after``/``at``/``when``) carries a
    ``TriggerInvocationExpression`` as its accepter payload argument: a signal
    accept or an eventless transition does not.
    """
    actions = list(trans.trigger_actions)
    if not actions:
        return None
    payload = actions[0].payload_argument
    if isinstance(payload, syside.TriggerInvocationExpression):
        return payload
    return None


def evaluate_to_number(
    expr: syside.Expression,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
) -> int | float | None:
    """Evaluate ``expr`` to a number in SI base units, or None.

    Uses the syside compiler's quantity evaluation, so a quantity expression
    collapses to its SI base scalar (``2 [min]`` -> ``120.0``). A ``bool`` does
    not count as a number.
    """
    value, _report = compiler.evaluate(
        expr, stdlib=stdlib, experimental_quantities=True
    )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def classify(
    trans: syside.TransitionUsage,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
) -> Trigger | None:
    """Classify a transition's accepter into a neutral ``Trigger``, or None.

    - a signal ``accept E via port`` -> ``SignalTrigger``;
    - a relative ``accept after <d>`` -> ``AfterTrigger`` carrying the SI
      seconds, or the attr-ref node for a bare/chained reference;
    - an absolute ``accept at <t>`` -> ``AtTrigger`` carrying the SI
      seconds, or the attr-ref node for a bare/chained reference;
    - a change ``accept when <cond>`` -> ``WhenTrigger`` carrying the
      condition node;
    - an eventless transition -> None.

    Raises:
        ValueError: If an ``after`` duration does not evaluate to a finite,
            non-negative number, if an ``at`` instant does not evaluate to a
            finite number, or if an ``accept when`` condition does not resolve
            to an expression.
    """
    invocation = trigger_invocation(trans)
    if invocation is None:
        name = _signal_name(trans)
        if name is None:
            return None
        return SignalTrigger(
            signal_name=name,
            payload_name=_payload_name(trans),
            via_port=_via_port(trans),
        )
    if invocation.kind is syside.TriggerKind.After:
        duration = invocation.arguments.collect()[0]
        if isinstance(
            duration,
            (
                syside.FeatureReferenceExpression,
                syside.FeatureChainExpression,
            ),
        ):
            return AfterTrigger(duration=duration)
        return AfterTrigger(
            duration=_duration_seconds(invocation, compiler, stdlib)
        )
    if invocation.kind is syside.TriggerKind.At:
        instant = invocation.arguments.collect()[0]
        if isinstance(
            instant,
            (
                syside.FeatureReferenceExpression,
                syside.FeatureChainExpression,
            ),
        ):
            return AtTrigger(instant=instant)
        return AtTrigger(instant=_instant_seconds(invocation, compiler, stdlib))
    return WhenTrigger(condition=_change_condition(invocation))


def _change_condition(
    invocation: syside.TriggerInvocationExpression,
) -> syside.Expression:
    """Return the monitored boolean condition of an ``accept when`` trigger.

    Raises:
        ValueError: If the wrapper does not resolve to an expression.
    """
    argument = invocation.arguments.collect()[0]
    if isinstance(argument, syside.FeatureReferenceExpression):
        referent = argument.referent
        if isinstance(referent, syside.Expression):
            return referent
    raise ValueError(
        "an `accept when` condition does not resolve to an expression."
    )


def _signal_name(trans: syside.TransitionUsage) -> str | None:
    """Return a signal accepter's payload type simple name, or None.

    Only called for a transition with no trigger invocation (so a time/change
    trigger has already been excluded).
    """
    actions = list(trans.trigger_actions)
    if not actions:
        return None
    param = actions[0].payload_parameter
    if param is None:
        return None
    typings = param.owned_typings.collect()
    if not typings:
        return None
    general = typings[0].general
    if general is None:
        return None
    return general.name


def _payload_name(trans: syside.TransitionUsage) -> str | None:
    """Return the accepter's declared payload parameter name, or None.

    ``accept reading : Tick`` declares ``reading``, a bare ``accept Tick``
    declares nothing.
    """
    actions = list(trans.trigger_actions)
    if not actions:
        return None
    param = actions[0].payload_parameter
    if param is None:
        return None
    return param.declared_name


def _via_port(trans: syside.TransitionUsage) -> str | None:
    """Return the simple name of the accepter's ``via`` receiver, or None."""
    actions = list(trans.trigger_actions)
    if not actions:
        return None
    receiver = actions[0].receiver_argument
    if isinstance(receiver, syside.FeatureReferenceExpression):
        ref = receiver.referent
        if ref is not None:
            return ref.name
    return None


def _duration_seconds(
    invocation: syside.TriggerInvocationExpression,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
) -> float:
    """Evaluate a relative time trigger's duration to SI base seconds.

    Raises:
        ValueError: If the duration does not evaluate to a finite, non-negative
            number.
    """
    seconds = _finite_seconds(
        invocation,
        compiler,
        stdlib,
        construct="accept after",
        quantity="duration",
        value_type="DurationValue",
    )
    if seconds < 0:
        raise ValueError(
            f"an `accept after` duration evaluates to {seconds!r}; the "
            "duration must be a finite, non-negative DurationValue."
        )
    return seconds


def _instant_seconds(
    invocation: syside.TriggerInvocationExpression,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
) -> float:
    """Evaluate an absolute time trigger's instant to SI base seconds.

    Raises:
        ValueError: If the instant does not evaluate to a finite number.
    """
    return _finite_seconds(
        invocation,
        compiler,
        stdlib,
        construct="accept at",
        quantity="instant",
        value_type="TimeInstantValue",
    )


def _finite_seconds(
    invocation: syside.TriggerInvocationExpression,
    compiler: syside.Compiler,
    stdlib: syside.Stdlib,
    *,
    construct: str,
    quantity: str,
    value_type: str,
) -> float:
    """Evaluate a time trigger quantity to finite SI base seconds.

    Raises:
        ValueError: If the quantity does not evaluate to a finite number.
    """
    number = evaluate_to_number(invocation, compiler, stdlib)
    if number is None:
        raise ValueError(
            f"an `{construct}` {quantity} does not evaluate to a number; the "
            f"{quantity} must be a {value_type} with a resolvable value."
        )
    seconds = float(number)
    if not math.isfinite(seconds):
        raise ValueError(
            f"an `{construct}` {quantity} evaluates to {seconds!r}; the "
            f"{quantity} must be a finite {value_type}."
        )
    return seconds
