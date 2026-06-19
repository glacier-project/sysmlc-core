from __future__ import annotations

from typing import TYPE_CHECKING

import syside

from sysmlc.semantics.statemachine import states

if TYPE_CHECKING:
    from collections.abc import Iterator


def scope_constraints(
    container: syside.StateDefinition | syside.StateUsage,
) -> list[syside.AssertConstraintUsage]:
    """Return the asserted constraints directly declared in a container.

    Plain (non-asserted) ``constraint`` usages are excluded: SysML does not
    require them to hold, so they generate no runtime checks.
    """
    return [
        member
        for member in container.owned_members.collect()
        if isinstance(member, syside.AssertConstraintUsage)
    ]


def iter_scope_constraints(
    container: syside.StateDefinition | syside.StateUsage,
) -> Iterator[
    tuple[
        syside.StateDefinition | syside.StateUsage,
        syside.AssertConstraintUsage,
    ]
]:
    """Yield every ``(scope, asserted constraint)`` pair under ``container``.

    Walks ``container`` and every substate; each yielded ``scope`` is the
    state container that directly declares the constraint.
    """
    for constraint in scope_constraints(container):
        yield container, constraint
    for substate in states.substates(container):
        yield from iter_scope_constraints(substate)
