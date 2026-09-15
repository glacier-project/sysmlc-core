from __future__ import annotations

from sysmlc.sysml.foreign_artifact.languages import SUPPORTED_LANG, get_language


def test_c_h_is_supported() -> None:
    assert "c_h" in SUPPORTED_LANG
    language = get_language("c_h")
    assert language.extension == "h"


def test_c_h_never_exposes_function_names() -> None:
    language = get_language("c_h")
    source = "double step(double x, double dt) { return x + dt; }\n"
    assert language.function_names(source) == frozenset()


def test_c_h_is_case_insensitive() -> None:
    assert get_language("C_H").name == "c_h"
