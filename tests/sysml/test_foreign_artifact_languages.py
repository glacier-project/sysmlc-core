from __future__ import annotations

from sysmlc.sysml.foreign_artifact.languages import (
    SUPPORTED_LANG,
    c_function_declarations,
    get_language,
)


def test_c_h_is_supported() -> None:
    assert "c_h" in SUPPORTED_LANG
    language = get_language("c_h")
    assert language.extension == "h"


def test_c_h_exposes_declared_names_not_defined_ones() -> None:
    language = get_language("c_h")
    # A prototype declaration is what a header actually carries.
    assert language.function_names("double step(double x, double dt);\n") == {
        "step"
    }
    # A function *definition* (a body, `{...}`) is never mistaken for one --
    # that would let a header alone satisfy a backend's "is this backed by
    # a real, linkable definition" check.
    assert (
        language.function_names(
            "double step(double x, double dt) { return x + dt; }\n"
        )
        == frozenset()
    )


def test_c_h_is_case_insensitive() -> None:
    assert get_language("C_H").name == "c_h"


def test_c_function_declarations_synthesizes_prototypes() -> None:
    source = "double step(double x, double dt)\n{\n    return x + dt;\n}\n"
    assert c_function_declarations(source) == (
        "double step(double x, double dt);",
    )


def test_c_function_declarations_finds_every_function_in_order() -> None:
    source = (
        "double step(double x, double dt) { return x + dt; }\n"
        "void reset(void) { }\n"
    )
    assert c_function_declarations(source) == (
        "double step(double x, double dt);",
        "void reset(void);",
    )
