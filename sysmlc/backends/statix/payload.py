"""Whole-payload struct layout helpers.

Shared by builder.py (encode), codegen.py (decode), and serialize.py (sizing)
without creating an import cycle between builder.py and codegen.py (builder.py
already imports CCodeGen from codegen.py; codegen.py needs these helpers too, so
they live in their own dependency-free module rather than either of those two).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sysmlc.errors import UnsupportedConstructError

if TYPE_CHECKING:
    from sysmlc.backends.statix.program import CStruct


def _flatten_leaf_paths(
    struct_name: str,
    structs_by_name: dict[str, CStruct],
    _visiting: frozenset[str] = frozenset(),
    _prefix: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    """Depth-first, declaration-order list of leaf (double) field paths.

    Shared by both the send (encode) and receive (decode) whole-payload
    lowering, so the two directions cannot silently drift out of the same
    field ordering. Deliberately rejects anything that is not a double or a
    registered struct name -- a Boolean/Integer/enum/unrecognized field type
    must never fall through to a dict-lookup KeyError -- and rejects a
    struct that refers back to an ancestor in its own field chain
    deterministically, rather than recursing until a stack error.
    """
    if struct_name in _visiting:
        raise UnsupportedConstructError(
            f"whole-payload type {struct_name!r} has a recursive composite "
            f"definition (via {'.'.join(_prefix) or '<root>'!r}); statix "
            "cannot flatten a self-referential payload."
        )
    paths: list[tuple[str, ...]] = []
    for f in structs_by_name[struct_name].fields:
        path = (*_prefix, f.name)
        if f.c_type == "double":
            paths.append(path)
        elif f.c_type in structs_by_name:
            paths.extend(
                _flatten_leaf_paths(
                    f.c_type,
                    structs_by_name,
                    _visiting | {struct_name},
                    path,
                )
            )
        else:
            raise UnsupportedConstructError(
                f"whole-payload field '{'.'.join(path)}' has type "
                f"{f.c_type!r}, which is neither Real (double) nor a "
                "registered all-Real composite; statix requires every "
                "leaf of a whole-payload type to be Real."
            )
    return paths


def _reconstruct_nested_literal(
    struct_type: str,
    structs_by_name: dict[str, CStruct],
    paths: list[tuple[str, ...]],
) -> str:
    """Build a nested compound literal from flat sc__payload[i] reads.

    Done in the exact order _flatten_leaf_paths produced them -- the inverse
    of the send side's flattening, walking the same struct tree.
    """
    index = {path: i for i, path in enumerate(paths)}

    def render(name: str, prefix: tuple[str, ...]) -> str:
        parts = []
        for f in structs_by_name[name].fields:
            path = (*prefix, f.name)
            if f.c_type == "double":
                parts.append(f".{f.name} = sc__payload[{index[path]}]")
            else:
                parts.append(f".{f.name} = {render(f.c_type, path)}")
        return "{" + ", ".join(parts) + "}"

    return render(struct_type, ())
