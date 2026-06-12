from __future__ import annotations

import math

import syside

from sysmlc.semantics.statemachine.facts import Trigger, TriggerKind


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

    - a signal ``accept E via port`` -> ``Trigger(SIGNAL, signal_name=E,
      payload_name=<declared name or None>, via_port=<port or None>)``;
    - a relative ``accept after <d>`` -> ``Trigger(AFTER, after=<SI seconds>)``,
      or ``Trigger(AFTER, after=<attr-ref node>)`` for a bare/chained reference;
    - an absolute ``accept at`` -> ``Trigger(AT)``;
    - a change ``accept when <cond>`` -> ``Trigger(WHEN, condition=<expr
      node>)``;
    - an eventless transition -> None.

    Whether ``AT``/``WHEN`` are acceptable is a backend (capability) concern, so
    this classifies them faithfully rather than rejecting them.

    Raises:
        ValueError: If an ``after`` duration does not evaluate to a finite,
            non-negative number, or if an ``accept when`` condition does not
            resolve to an expression.
    """
    invocation = trigger_invocation(trans)
    if invocation is None:
        name = _signal_name(trans)
        if name is None:
            return None
        return Trigger(
            TriggerKind.SIGNAL,
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
            return Trigger(TriggerKind.AFTER, after=duration)
        return Trigger(
            TriggerKind.AFTER,
            after=_duration_seconds(invocation, compiler, stdlib),
        )
    if invocation.kind is syside.TriggerKind.At:
        return Trigger(TriggerKind.AT)
    return Trigger(TriggerKind.WHEN, condition=_change_condition(invocation))


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
    number = evaluate_to_number(invocation, compiler, stdlib)
    if number is None:
        raise ValueError(
            "an `accept after` duration does not evaluate to a number; the "
            "duration must be a DurationValue with a resolvable value."
        )
    seconds = float(number)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(
            f"an `accept after` duration evaluates to {seconds!r}; the "
            "duration must be a finite, non-negative DurationValue."
        )
    return seconds
