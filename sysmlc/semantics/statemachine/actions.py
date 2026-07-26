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
    None or owns no action.
    """
    if action is None:
        return []
    if isinstance(
        action, (syside.AssignmentActionUsage, syside.SendActionUsage)
    ):
        candidates: list[syside.Feature] = [action]
    else:
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
    if (
        do_action.owned_typings.collect()
        or do_action.owned_reference_subsetting is not None
    ):
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
