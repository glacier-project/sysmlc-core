"""Payload-schema walker.

Shared by builder.py (encode), codegen.py (decode), and serialize.py (sizing)
without creating an import cycle between builder.py and codegen.py (builder.py
already imports CCodeGen from codegen.py; codegen.py needs this helper too, so
it lives in its own dependency-free module rather than either of those two).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sysmlc.errors import UnsupportedConstructError

if TYPE_CHECKING:
    from sysmlc.backends.statix.program import CStruct

# Every C type statix can carry as a payload leaf. Real/Integer/Boolean only --
# String and generated-enum types are deliberately excluded (unrepresentable
# in a fixed-size byte-copied wire struct without further design work).
_LEAF_C_TYPES: frozenset[str] = frozenset({"double", "int32_t", "bool"})


def _walk_payload_fields(
    struct_name: str,
    structs_by_name: dict[str, CStruct],
    _visiting: frozenset[str] = frozenset(),
    _prefix: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    """Depth-first, declaration-order list of leaf field paths.

    A leaf is any field whose C type is Real (double), Integer (int32_t), or
    Boolean (bool); a field whose type is itself a registered struct name is
    recursed into instead of treated as a leaf. Shared by send-side
    materialization, receive-side representability validation, and sizing, so
    all three cannot silently drift out of the same field ordering.
    Deliberately rejects any other field type (e.g. `const char*` for
    String, or a generated enum type) -- such a field must never fall
    through to a dict-lookup KeyError -- and rejects a struct that refers
    back to an ancestor in its own field chain deterministically, rather
    than recursing until a Python stack error.
    """
    if struct_name in _visiting:
        raise UnsupportedConstructError(
            f"payload type {struct_name!r} has a recursive composite "
            f"definition (via {'.'.join(_prefix) or '<root>'!r}); statix "
            "cannot walk a self-referential payload."
        )
    paths: list[tuple[str, ...]] = []
    for f in structs_by_name[struct_name].fields:
        path = (*_prefix, f.name)
        if f.c_type in _LEAF_C_TYPES:
            paths.append(path)
        elif f.c_type in structs_by_name:
            paths.extend(
                _walk_payload_fields(
                    f.c_type,
                    structs_by_name,
                    _visiting | {struct_name},
                    path,
                )
            )
        else:
            raise UnsupportedConstructError(
                f"payload field '{'.'.join(path)}' has type {f.c_type!r}, "
                "which is neither Real/Integer/Boolean nor a registered "
                "all-primitive composite; statix requires every leaf of a "
                "payload type to be one of those."
            )
    return paths


def _reconstruct_nested_literal(
    struct_type: str,
    structs_by_name: dict[str, CStruct],
    paths: list[tuple[str, ...]],
) -> str:
    """Build a nested compound literal from flat sc__payload[i] reads.

    Done in the exact order _walk_payload_fields produced them -- the inverse
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
