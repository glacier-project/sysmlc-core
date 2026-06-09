from __future__ import annotations

import syside


def iter_model_elements(
    model: syside.Model,
    element_kind: type[syside.Element] = syside.Element,
    *,
    include_subtypes: bool = True,
    considered_document_kinds: syside.DocumentKind = syside.DocumentKind.MODEL,
) -> list[syside.Element]:
    """Return model elements for the requested Syside class.

    ``include_subtypes=True`` is Syside's documented way to ask for all
    subtypes of a metaclass. Results are sorted to keep visitor behavior
    stable.

    Args:
        model: Loaded Syside model.
        element_kind: Syside element class to include in the traversal.
        include_subtypes: Whether to include subclasses of ``element_kind``.
        considered_document_kinds: Which Syside document set to inspect.

    Returns:
        Deterministically sorted Syside elements.
    """
    return sorted(
        model.elements(
            element_kind,
            include_subtypes=include_subtypes,
            considered_document_kinds=considered_document_kinds,
        ),
        key=_element_sort_key,
    )


def _element_sort_key(element: syside.Element) -> tuple[str, str, str]:
    qualified_name = element.qualified_name
    path = element.path
    name = element.name
    return (
        "" if qualified_name is None else str(qualified_name),
        str(path),
        "" if name is None else str(name),
    )
