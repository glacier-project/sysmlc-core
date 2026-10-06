"""C syntax helpers; preprocessing and type checking remain compiler work."""

from __future__ import annotations

from typing import TYPE_CHECKING

import tree_sitter_c
from tree_sitter import Language, Node, Parser

if TYPE_CHECKING:
    from collections.abc import Iterator


def _parse(source: str) -> Node:
    """Parse standalone C syntax and reject incomplete or macro-shaped bodies."""
    root = (
        Parser(Language(tree_sitter_c.language()))
        .parse(source.encode())
        .root_node
    )
    if root.has_error:
        raise SyntaxError(
            "foreign C source has invalid or unsupported syntax; use explicit C files and headers for macro-generated declarations"
        )
    return root


def _top_level(node: Node) -> Iterator[Node]:
    """Visit declarations inside preprocessor guards, never inside functions."""
    for child in node.named_children:
        if child.type in (
            "preproc_if",
            "preproc_ifdef",
            "preproc_else",
            "preproc_elif",
        ):
            yield from _top_level(child)
        else:
            yield child


def _function_name(node: Node) -> str | None:
    """Find an ordinary function declarator, including pointer return types."""
    declarator = node.child_by_field_name("declarator")
    while declarator is not None:
        if declarator.type == "function_declarator":
            name = declarator.child_by_field_name("declarator")
            if (
                name is not None
                and name.type == "identifier"
                and name.text is not None
            ):
                return name.text.decode()
            return None
        declarator = declarator.child_by_field_name("declarator")
    return None


def _static(node: Node) -> bool:
    return any(
        c.type == "storage_class_specifier" and c.text == b"static"
        for c in node.named_children
    )


def function_names(source: str, *, headers: bool = False) -> frozenset[str]:
    """Return exported definitions or top-level prototypes, ignoring comments."""
    kind = "declaration" if headers else "function_definition"
    return frozenset(
        name
        for node in _top_level(_parse(source))
        if node.type == kind
        and not _static(node)
        and (name := _function_name(node)) is not None
    )


def _signature(node: Node, source: bytes) -> str:
    body = node.child_by_field_name("body")
    assert body is not None
    return source[node.start_byte : body.start_byte].decode().strip() + ";"


def function_declarations(source: str) -> tuple[str, ...]:
    """Derive exported function prototypes from parsed definition boundaries."""
    raw = source.encode()
    return tuple(
        _signature(node, raw)
        for node in _top_level(_parse(source))
        if node.type == "function_definition" and not _static(node)
    )


def with_function_declarations(source: str) -> str:
    """Add exported prototypes after type context and before definitions."""
    raw = source.encode()
    declarations = [
        (node.start_byte, (_signature(node, raw) + "\n").encode())
        for node in _top_level(_parse(source))
        if node.type == "function_definition" and not _static(node)
    ]
    for offset, declaration in reversed(declarations):
        raw = raw[:offset] + declaration + raw[offset:]
    return raw.decode()


def header_source(source: str) -> str:
    """Keep includes/types/macros and replace exported definitions by prototypes.

    Automatic companions require declaration-only package context. Global
    storage definitions must instead be supplied in explicit source/header pairs.
    """
    raw = source.encode()
    replacements: list[tuple[int, int, bytes]] = []
    for node in _top_level(_parse(source)):
        if node.type == "function_definition":
            text = b"" if _static(node) else _signature(node, raw).encode()
            replacements.append((node.start_byte, node.end_byte, text))
        elif node.type == "declaration" and _function_name(node) is None:
            storage = [
                c.text
                for c in node.named_children
                if c.type == "storage_class_specifier"
            ]
            # A struct/enum declaration without a variable is type context.
            if (
                b"extern" not in storage
                and b"static" not in storage
                and node.child_by_field_name("declarator") is not None
            ):
                raise SyntaxError(
                    "C representation package context defines global storage; supply an explicit C source and companion header"
                )
    for start, end, text in reversed(replacements):
        raw = raw[:start] + text + raw[end:]
    return raw.decode()


def deduplicate_functions(source: str) -> str:
    """Emit identical repeated definitions once and reject conflicting bodies."""
    raw = source.encode()
    known: dict[str, bytes] = {}
    duplicates: list[tuple[int, int]] = []
    for node in _top_level(_parse(source)):
        if node.type != "function_definition":
            continue
        name = _function_name(node)
        if name is None:
            raise SyntaxError(
                "C function definition has no ordinary function name"
            )
        body = raw[node.start_byte : node.end_byte]
        previous = known.get(name)
        if previous is None:
            known[name] = body
            continue
        if previous != body:
            raise SyntaxError(f"conflicting C definitions of {name!r}")
        duplicates.append((node.start_byte, node.end_byte))
    for start, end in reversed(duplicates):
        raw = raw[:start] + raw[end:]
    return raw.decode()


def function_sources(source: str) -> dict[str, str]:
    """Return individual definition text for representation collision checks."""
    raw = source.encode()
    return {
        name: raw[node.start_byte : node.end_byte].decode()
        for node in _top_level(_parse(source))
        if node.type == "function_definition"
        and (name := _function_name(node)) is not None
    }
