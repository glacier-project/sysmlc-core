from __future__ import annotations

import syside

from sysmlc.semantics.statemachine.facts import StateKind


def substates(
    container: syside.StateDefinition | syside.StateUsage,
) -> list[syside.StateUsage]:
    """Return the immediate substates of a state container.

    A ``StateDefinition`` exposes them as ``owned_states``, while a composite
    ``StateUsage`` exposes them as ``nested_states``.
    """
    if isinstance(container, syside.StateDefinition):
        return container.owned_states.collect()
    return container.nested_states.collect()


def state_path(state_def: syside.StateDefinition, state: syside.Feature) -> str:
    """Return a state's path relative to the state definition.

    The path is the state's qualified name with the state definition's own
    qualified name stripped off.
    """
    prefix = f"{state_def.qualified_name}::"
    return str(state.qualified_name).removeprefix(prefix)


def state_kind(
    container: syside.StateDefinition | syside.StateUsage,
) -> StateKind:
    """Classify a state container as COMPOSITE, PARALLEL, or LEAF.

    Never returns FINAL: final (``done``) states are synthesized by a backend,
    not read from the source.
    """
    if container.is_parallel:
        return StateKind.PARALLEL
    if substates(container):
        return StateKind.COMPOSITE
    return StateKind.LEAF


def is_done_target(feature_target: syside.Feature) -> bool:
    """Whether a transition target is the standard-library ``done``."""
    return str(feature_target.qualified_name) == "States::StateAction::done"


def resolve_initial(
    container: syside.StateDefinition | syside.StateUsage,
) -> syside.StateUsage:
    """Resolve the initial substate selected by a container's entry.

    Raises:
        ValueError: If no entry pseudostate is declared, or if no succession
            from the entry pseudostate to a ``StateUsage`` can be found.
    """
    entry = container.entry_action
    if entry is None:
        raise ValueError(
            f"State {container.qualified_name} has no entry "
            "pseudostate; expected an `entry; then <state>;` declaration."
        )
    for feat in container.owned_features.collect():
        if not isinstance(feat, syside.SuccessionAsUsage):
            continue
        if feat.source is not entry:
            continue
        for target in feat.targets.collect():
            if isinstance(target, syside.StateUsage):
                return target
    raise ValueError(
        f"No entry succession found for state "
        f"{container.qualified_name}; expected an "
        f"`entry; then <state>;` declaration."
    )
