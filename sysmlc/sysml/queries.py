from __future__ import annotations

import logging
from typing import TYPE_CHECKING, overload

import syside

if TYPE_CHECKING:
    from collections.abc import Sequence

from sysmlc.sysml.names import QualifiedName, normalize_qualified_name

logger = logging.getLogger(__name__)


def resolve[TElement: syside.Element](
    model: syside.Model,
    kind: type[TElement],
    qualified_name: QualifiedName,
) -> TElement:
    """Resolve a model element by kind and qualified name (MODEL-scoped)."""
    normalized = normalize_qualified_name(qualified_name)
    logger.info("Resolving %s %s", kind.__name__, "::".join(normalized))
    for element in model.elements(
        kind,
        include_subtypes=True,
        considered_document_kinds=syside.DocumentKind.MODEL,
    ):
        if element.matches_qualified_name(normalized):
            return element
    raise ValueError(f"{kind.__name__} {'::'.join(normalized)!r} not found")


@overload
def iter_elements(
    model: syside.Model,
    kind: None = ...,
    *,
    include_subtypes: bool = ...,
    considered_document_kinds: syside.DocumentKind = ...,
) -> Sequence[syside.Element]: ...


@overload
def iter_elements[TElement: syside.Element](
    model: syside.Model,
    kind: type[TElement],
    *,
    include_subtypes: bool = ...,
    considered_document_kinds: syside.DocumentKind = ...,
) -> Sequence[TElement]: ...


def iter_elements(
    model: syside.Model,
    kind: type[syside.Element] | None = None,
    *,
    include_subtypes: bool = True,
    considered_document_kinds: syside.DocumentKind = syside.DocumentKind.MODEL,
) -> Sequence[syside.Element]:
    """Return model elements of ``kind``, sorted for stable iteration."""
    if kind is None:
        kind = syside.Element
    return sorted(
        model.elements(
            kind,
            include_subtypes=include_subtypes,
            considered_document_kinds=considered_document_kinds,
        ),
        key=_element_sort_key,
    )


def state_definitions(model: syside.Model) -> Sequence[syside.StateDefinition]:
    """Return every state definition in the model, deterministically sorted."""
    return iter_elements(model, syside.StateDefinition)


def rig_definitions(model: syside.Model) -> Sequence[syside.PartDefinition]:
    """Part definitions that exhibit two named state usages (testbench rigs)."""
    rigs: list[syside.PartDefinition] = []
    for part_def in iter_elements(model, syside.PartDefinition):
        members = [
            member
            for member in part_def.owned_members.collect()
            if not isinstance(member, syside.Documentation | syside.Comment)
        ]
        exhibits = [
            member
            for member in members
            if isinstance(member, syside.ExhibitStateUsage)
        ]
        if (
            len(exhibits) == 2
            and len(members) == 2
            and all(exhibit.name for exhibit in exhibits)
        ):
            rigs.append(part_def)
    return rigs


def top_level_part_usages(
    model: syside.Model,
) -> Sequence[syside.PartUsage]:
    """Top-level part *usages* that compose nested parts (-> main reactors).

    A qualifying usage is owned by a ``Package`` (not nested inside another
    part) and owns at least one nested ``PartUsage``; a leaf usage merely
    typed by a part def (no children) does not qualify. Deterministically
    sorted, so single-usage auto-selection and ``--element`` are stable.
    """
    return [
        usage
        for usage in iter_elements(model, syside.PartUsage)
        if isinstance(usage.owner, syside.Package)
        and any(
            isinstance(feature, syside.PartUsage)
            for feature in usage.owned_features.collect()
        )
    ]


def exhibited_state_defs(
    model: syside.Model, rig: syside.PartDefinition
) -> list[tuple[str, syside.StateDefinition]]:
    """The rig's (usage name, exhibited state def) pairs, validated.

    A rig must hold exactly two named ``exhibit state`` usages, each
    typed by a state definition declared in the model (library
    supertypes in ``state_definitions`` heritage are filtered out), and
    nothing else (documentation aside).
    """
    model_defs = {str(sd.qualified_name): sd for sd in state_definitions(model)}
    pairs: list[tuple[str, syside.StateDefinition]] = []
    for member in rig.owned_members.collect():
        if isinstance(member, syside.Documentation | syside.Comment):
            continue
        if not isinstance(member, syside.ExhibitStateUsage):
            raise ValueError(
                f"rig {rig.name!r} owns {member.name or '<anonymous>'!r}, "
                "which is not an `exhibit state` usage; a rig holds two "
                "exhibits and nothing else"
            )
        if not member.name:
            raise ValueError(
                f"rig {rig.name!r} has an anonymous exhibit; name it — "
                "the name becomes the LF instance name"
            )
        declared = [
            sd
            for sd in member.state_definitions.collect()
            if isinstance(sd, syside.StateDefinition)
            and str(sd.qualified_name) in model_defs
        ]
        if len(declared) != 1:
            raise ValueError(
                f"exhibit {member.name!r} in rig {rig.name!r} resolves "
                f"{len(declared)} state defs declared in this model; it "
                "must be typed by exactly one (not a library type)"
            )
        pairs.append((member.name, declared[0]))
    if len(pairs) != 2:
        raise ValueError(
            f"rig {rig.name!r} exhibits {len(pairs)} machines; a rig "
            "composes exactly two"
        )
    if pairs[0][0] == pairs[1][0]:
        raise ValueError(
            f"rig {rig.name!r} exhibits two usages named {pairs[0][0]!r}; "
            "names must differ"
        )
    return pairs


def feature_value(
    attr: syside.AttributeUsage | syside.ItemUsage,
) -> syside.Expression | None:
    """Return the attribute's own value expression, if any.

    Reads the owned ``FeatureValue`` relationship first: syside's
    ``feature_value_expression`` accessor is blind to values created
    through the low-level editing API (in-memory configuration), while
    the relationship is authoritative for parsed and created values
    alike.
    """
    for rel in attr.owned_relationships.collect():
        if isinstance(rel, syside.FeatureValue):
            return rel.value
    return attr.feature_value_expression


def _element_sort_key(element: syside.Element) -> tuple[str, str, str]:
    qualified_name = element.qualified_name
    path = element.path
    name = element.name
    return (
        "" if qualified_name is None else str(qualified_name),
        str(path),
        "" if name is None else str(name),
    )
