from __future__ import annotations

import syside

from sysmlc.errors import UnsupportedConstructError


def inline_actions(
    action: syside.ActionUsage | None,
) -> list[syside.ActionUsage]:
    """Return an action slot's inline action usages, in declaration order.

    Covers both the shorthand form (the slot is itself the ``assign``/``send``)
    and the block form (the actions are the wrapping action's owned features).
    Returns every owned ``ActionUsage`` (not only ``assign``/``send``) so that
    an unsupported action kind still fails loud when a backend renders it,
    rather than being silently dropped. Returns an empty list when ``action`` is
    None or owns no action. Referenced or typed wrappers cannot be inspected as
    inline bodies, even when they also own local statements.

    Raises:
        UnsupportedConstructError: If the slot references another action.
    """
    if action is None:
        return []
    if isinstance(
        action, (syside.AssignmentActionUsage, syside.SendActionUsage)
    ):
        candidates: list[syside.Feature] = [action]
    else:
        if _references_action(action):
            membership = action.owning_membership
            phase = "action slot"
            if isinstance(membership, syside.StateSubactionMembership):
                if membership.kind == syside.StateSubactionKind.Do:
                    require_inline_one_shot(action)
                phase = {
                    syside.StateSubactionKind.Entry: "`entry` action",
                    syside.StateSubactionKind.Do: "`do` action",
                    syside.StateSubactionKind.Exit: "`exit` action",
                }[membership.kind]
            elif isinstance(membership, syside.TransitionFeatureMembership):
                if membership.kind == syside.TransitionFeatureKind.Effect:
                    phase = "transition effect"
            raise UnsupportedConstructError(
                f"a {phase} that references another action is unsupported; "
                "only inline action bodies are supported.",
                node=action,
            )
        candidates = action.owned_features.collect()
    return [
        candidate
        for candidate in candidates
        if isinstance(candidate, syside.ActionUsage)
    ]


def require_inline_one_shot(do_action: syside.ActionUsage) -> None:
    """Reject a ``do`` action body that cannot be emitted as a one-shot.

    An opt-in check for targets without a running-activity slot: only an
    inline ``assign``/``send`` ``do`` body can be emitted (as a run-once
    entry statement).

    Raises:
        UnsupportedConstructError: If the do action references another action (a
            typed perform or the reference-subsetting shorthand), or its body
            contains anything other than inline ``assign``/``send``.
    """
    if _references_action(do_action):
        raise UnsupportedConstructError(
            "a `do` action that references another action is unsupported; "
            "only inline `assign`/`send` do-action bodies are supported.",
            node=do_action,
        )
    for action in do_action.nested_actions.collect():
        if not isinstance(
            action,
            (syside.AssignmentActionUsage, syside.SendActionUsage),
        ):
            raise UnsupportedConstructError(
                "a `do` action body contains an unsupported "
                f"{type(action).__name__}; only `assign` and `send` "
                "do-action bodies are supported.",
                node=action,
            )


def _references_action(action: syside.ActionUsage) -> bool:
    """Whether a slot explicitly types or subsets another action."""
    return bool(
        action.owned_typings.collect()
        or action.owned_reference_subsetting is not None
        or any(
            not subsetting.is_implied
            for subsetting in action.owned_subsettings.collect()
        )
    )
