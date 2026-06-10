from __future__ import annotations

import syside

from sysmlc.semantics.statemachine import states
from sysmlc.semantics.statemachine.facts import CompletionTarget, TransitionFact


def container_transitions(
    container: syside.StateDefinition | syside.StateUsage,
) -> list[syside.TransitionUsage]:
    """Return the transitions owned directly by a state container.

    A ``StateDefinition`` exposes them as ``owned_transitions``, while a
    composite ``StateUsage`` exposes them as ``nested_transitions``.
    """
    if isinstance(container, syside.StateDefinition):
        return container.owned_transitions.collect()
    return container.nested_transitions.collect()


def source_path(
    state_def: syside.StateDefinition, trans: syside.TransitionUsage
) -> str:
    """Return the relative path of a transition's source state.

    Raises:
        ValueError: If the transition has no resolved source.
    """
    source = trans.source
    if source is None:
        raise ValueError(
            f"Transition in state def {state_def.qualified_name} "
            "has no resolved source."
        )
    return states.state_path(state_def, source)


def target(
    state_def: syside.StateDefinition,
    trans: syside.TransitionUsage,
    container: syside.StateDefinition | syside.StateUsage,
) -> str | CompletionTarget:
    """Resolve a transition's target.

    Returns the target's relative state path, or a ``CompletionTarget`` for the
    owning scope when the target is the standard-library ``done``.

    Raises:
        ValueError: If the transition has no resolved target.
    """
    succession = trans.succession
    targets = succession.targets.collect() if succession is not None else []
    if not targets:
        raise ValueError(
            f"Transition in state def {state_def.qualified_name} "
            "has no resolved target."
        )
    feature_target = targets[0].feature_target
    if states.is_done_target(feature_target):
        scope = (
            ""
            if isinstance(container, syside.StateDefinition)
            else states.state_path(state_def, container)
        )
        return CompletionTarget(scope=scope)
    return states.state_path(state_def, feature_target)


def self_loop_is_unstable(transition: TransitionFact) -> bool:
    """Whether a self-loop transition has nothing to gate it.

    A sismic-oriented opt-in check: a transition whose source equals its target
    with no event, no timer/guard, and no effect would never stabilize.
    """
    return (
        isinstance(transition.target, str)
        and transition.source == transition.target
        and transition.trigger is None
        and (transition.guard is None or transition.effect is None)
    )
