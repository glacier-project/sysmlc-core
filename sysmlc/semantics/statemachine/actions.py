from __future__ import annotations

import syside

from sysmlc.errors import UnsupportedConstructError


def inline_actions(
    action: syside.ActionUsage | None,
) -> list[syside.ActionUsage]:
    """Return an action slot's inline actions in execution order.

    Covers both the shorthand form (the slot is itself the ``assign``/``send``)
    and the block form (the actions are the wrapping action's owned features).
    Returns every owned ``ActionUsage`` (not only ``assign``/``send``) so that
    an unsupported action kind still fails loud when a backend renders it,
    rather than being silently dropped. Returns an empty list when ``action`` is
    None or owns no action. Referenced or typed wrappers cannot be inspected as
    inline bodies, even when they also own local statements.

    Bodies without explicit sequencing use declaration order. Explicit
    successions must form one complete linear sequence, optionally bounded
    by the inherited ``start`` and ``done`` snapshots.

    Raises:
        UnsupportedConstructError: If the slot references another action or
            its explicit sequencing cannot be emitted as one linear sequence.
    """
    if action is None:
        return []
    if isinstance(
        action, (syside.AssignmentActionUsage, syside.SendActionUsage)
    ):
        return [action]
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
    statements = [
        candidate
        for candidate in action.nested_actions.collect()
        if isinstance(candidate, syside.ActionUsage)
    ]
    return _ordered_actions(action, statements)


def _ordered_actions(
    action: syside.ActionUsage,
    statements: list[syside.ActionUsage],
) -> list[syside.ActionUsage]:
    """Follow one complete succession chain, or retain declaration order."""
    for transition in action.nested_transitions.collect():
        raise UnsupportedConstructError(
            "conditional action successions are unsupported; "
            "only an unconditional linear sequence is supported.",
            node=transition,
        )
    connections = action.nested_connections.collect()
    for connection in connections:
        if isinstance(connection, syside.SuccessionFlowUsage):
            raise UnsupportedConstructError(
                "succession flows in action bodies are unsupported.",
                node=connection,
            )
    successions = [
        connection
        for connection in connections
        if isinstance(connection, syside.SuccessionAsUsage)
    ]
    if not successions:
        return statements

    statement_set = set(statements)
    nodes: set[syside.Feature] = set(statements)
    successors: dict[syside.Feature, syside.Feature] = {}
    predecessors: dict[syside.Feature, syside.Feature] = {}
    for statement in statements:
        _require_single_occurrence(statement)
    for succession in successions:
        _require_single_occurrence(succession)
        for end in succession.connector_ends.collect():
            _require_single_occurrence(end)
            if end.owned_cross_feature is not None:
                _require_single_occurrence(end.owned_cross_feature)
        source = succession.source_feature
        targets = succession.target_features.collect()
        if source is None or len(targets) != 1:
            raise UnsupportedConstructError(
                "an action succession must have one source and one target.",
                node=succession,
            )
        target = targets[0]
        for endpoint in (source, target):
            if endpoint.chaining_features.collect() or (
                endpoint not in statement_set
                and not (
                    _is_boundary(endpoint, "start")
                    or _is_boundary(endpoint, "done")
                )
            ):
                raise UnsupportedConstructError(
                    "action successions must connect local actions or the "
                    "inherited start/done snapshots without feature chains.",
                    node=succession,
                )
            nodes.add(endpoint)
        if (source not in statement_set and _is_boundary(source, "done")) or (
            target not in statement_set and _is_boundary(target, "start")
        ):
            raise UnsupportedConstructError(
                "an action sequence cannot precede start or follow done.",
                node=succession,
            )
        if (source in successors and successors[source] is not target) or (
            target in predecessors and predecessors[target] is not source
        ):
            raise UnsupportedConstructError(
                "branching or merging action successions are unsupported.",
                node=succession,
            )
        successors[source] = target
        predecessors[target] = source

    heads = nodes.difference(predecessors)
    ordered: list[syside.ActionUsage] = []
    visited: set[syside.Feature] = set()
    current = next(iter(heads)) if len(heads) == 1 else None
    while current is not None and current not in visited:
        visited.add(current)
        if isinstance(current, syside.ActionUsage) and current in statement_set:
            ordered.append(current)
        current = successors.get(current)
    if current is not None or visited != nodes:
        raise UnsupportedConstructError(
            "action successions must form one complete acyclic linear "
            "sequence covering every inline action.",
            node=action,
        )
    return ordered


def _is_boundary(feature: syside.Feature, name: str) -> bool:
    """Whether a feature is a canonical inherited action boundary."""
    return feature.is_library_element and feature.matches_qualified_name(
        ["Actions", "Action", name]
    )


def _require_single_occurrence(feature: syside.Feature) -> None:
    """Reject an explicit multiplicity other than one occurrence."""
    multiplicity = feature.declared_multiplicity
    if multiplicity is None:
        return
    upper = multiplicity.upper_bound
    lower = multiplicity.lower_bound or upper
    for bound in (lower, upper):
        if bound is not None:
            value, report = syside.Compiler().evaluate(bound)
            if (
                type(value) is int
                and value == 1
                and not report.fatal
                and not any(
                    diagnostic.severity == syside.DiagnosticSeverity.Error
                    for diagnostic in report.diagnostics
                )
            ):
                continue
        raise UnsupportedConstructError(
            "explicit action-sequence multiplicity must evaluate to [1].",
            node=feature,
        )


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
