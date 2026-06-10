from __future__ import annotations

from collections.abc import Sequence

type QualifiedName = str | Sequence[str]


def normalize_qualified_name(qualified_name: QualifiedName) -> tuple[str, ...]:
    """Normalize a qualified name to SysIDE's segment-based representation.

    Args:
        qualified_name: Qualified name as a ``"::"``-joined string or as a
            sequence of segments.

    Returns:
        Tuple of non-empty segments suitable for SysIDE matching APIs.
    """
    if isinstance(qualified_name, str):
        return tuple(
            segment for segment in qualified_name.split("::") if segment
        )
    return tuple(qualified_name)
