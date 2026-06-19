from __future__ import annotations

import syside

from sysmlc.errors import UnsupportedConstructError
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
    """Resolve the initial substate selected by a container.

    Raises:
        ValueError: If no initial state is declared.
    """

    # UTILITY FUNCTIONS
    def unwrap_to_stateusage(
        x: syside.Feature | syside.StateUsage | None,
    ) -> syside.StateUsage | None:
        """Unwrap a Feature to a StateUsage, if possible."""
        visited = set()
        while x is not None and id(x) not in visited:
            visited.add(id(x))

            if isinstance(x, syside.StateUsage):
                return x

            nxt = getattr(x, "feature_target", None)
            if nxt is None or nxt is x:
                return None
            x = nxt
        return None

    def get_target(
        container: syside.StateDefinition | syside.StateUsage | None,
    ) -> syside.StateUsage | None:
        """Return the initial target of a container."""
        # Coverage of case:
        # - Case 0: "entry; then <state>;"
        # - Case 1: "first start then <state>;"
        valid_types = (syside.StateDefinition, syside.StateUsage)
        if not isinstance(container, valid_types):
            return None

        entry = getattr(container, "entry_action", None)
        for feat in container.owned_features.collect():
            if not isinstance(feat, syside.SuccessionAsUsage):
                continue

            is_entry = entry and getattr(
                feat.source, "qualified_name", None
            ) == getattr(entry, "qualified_name", None)
            is_start = feat.source and (
                getattr(feat.source, "name", None) == "start"
                or str(getattr(feat.source, "qualified_name", None)).endswith(
                    "::start"
                )
            )

            if not is_entry and not is_start:
                continue

            for target in feat.targets.collect():
                if tgt := unwrap_to_stateusage(target):
                    return tgt

        return None

    # ----
    # Searching for initial target declared by the container itself
    # ----
    initial_target = get_target(container)

    if initial_target:
        if getattr(initial_target, "owner", None) != container:
            raise UnsupportedConstructError(
                "Initial target "
                f"{initial_target.qualified_name} is not a direct substate "
                f"of {container.qualified_name}. Only direct initial "
                "substates are supported."
            )
        return initial_target

    raise ValueError(f"No initial state for {container.qualified_name}")
