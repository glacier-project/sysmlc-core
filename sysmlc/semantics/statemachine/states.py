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


def _is_initial_source(
    container: syside.StateDefinition | syside.StateUsage,
    source: syside.Feature | None,
) -> bool:
    """Whether ``source`` is a supported initial-selection source."""
    entry = container.entry_action
    if entry is not None and source == entry:
        return True
    if source is None:
        return False
    return str(source.qualified_name) == "States::StateAction::start"


def _target_state(
    succession: syside.SuccessionAsUsage,
) -> syside.StateUsage | None:
    """Return the first StateUsage target of a succession, if any."""
    for target_feature in succession.target_features.collect():
        target = target_feature.feature_target
        if isinstance(target, syside.StateUsage):
            return target
    return None


def _declared_initial_target(
    container: syside.StateDefinition | syside.StateUsage,
) -> syside.StateUsage | None:
    """Return the initial target declared directly by ``container``."""
    for feature in container.owned_features.collect():
        if not isinstance(feature, syside.SuccessionAsUsage):
            continue
        if not _is_initial_source(container, feature.source_feature):
            continue
        target = _target_state(feature)
        if target is not None:
            return target
    return None


def resolve_initial(
    container: syside.StateDefinition | syside.StateUsage,
) -> syside.StateUsage:
    """Resolve the initial substate selected by a container.

    Raises:
        ValueError: If no initial state is declared.
    """
    initial_target = _declared_initial_target(container)

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
