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

    def resolve_target(target):
        """Resolve Feature → StateUsage recursively."""
        if isinstance(target, syside.StateUsage):
            return target

        if isinstance(target, syside.Feature):
            feat_target = getattr(target, "feature_target", None)
            return resolve_target(feat_target) if feat_target else None

        return None

    def direct_child(container, state):
        """Return closest valid child of container."""
        children = substates(container)
        if not children:
            return None

        if state in children:
            return state

        curr = state
        while curr is not None:
            parent = getattr(curr, "eContainer", None)
            if parent in children:
                return parent
            curr = parent

        return children[0]

    def iter_successions(container):
        """Yield all SuccessionAsUsage in container."""
        for feat in container.owned_features.collect():
            if isinstance(feat, syside.SuccessionAsUsage):
                yield feat

    # Case 1: "entry; then <state>;"
    if entry := container.entry_action:
        for feat in iter_successions(container):
            if feat.source is not entry:
                continue
            for target in feat.targets.collect():
                state_target = resolve_target(target)
                if state_target:
                    return direct_child(container, state_target)

    # Case 2: "first start then <state>;"
    for feat in iter_successions(container):
        src = feat.source
        if not src:
            continue

        src_name = getattr(src, "name", None)
        src_qname = str(getattr(src, "name", None))
        if src_name == "start" or src_qname.endswith("::start"):
            for target in feat.targets.collect():
                state_target = resolve_target(target)
                if state_target:
                    return direct_child(container, state_target)

    # Case 3: no initial state specified
    valid_children = substates(container)
    if valid_children:
        return valid_children[0]

    raise ValueError(f"No initial state for {container.qualified_name}")
