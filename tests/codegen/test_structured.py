from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest
import syside

from sysmlc.codegen.structured import (
    DataclassRegistry,
    GeneratedPythonModule,
    register_dataclass,
    types_import_lines,
    types_module_name,
)
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.queries import resolve
from tests import _load_inline_model

if TYPE_CHECKING:
    from pathlib import Path

BLOCK_A = ("@dataclass", "class Reading:", "    x: float = 0.0")
BLOCK_B = ("@dataclass", "class Reading:", "    x: float = 1.0")


def test_types_module_name_sanitizes_qualified_names() -> None:
    assert types_module_name("Pkg::part") == "Pkg_part_types"
    assert types_module_name("a b-c") == "a_b_c_types"


def test_types_module_name_guards_leading_digit() -> None:
    assert types_module_name("3rd::sys") == "_3rd_sys_types"


def test_types_module_name_rejects_empty_stem() -> None:
    with pytest.raises(ValueError, match="no identifier characters"):
        types_module_name("::")


@pytest.mark.parametrize(
    ("definition_source", "definition_name", "invalid_name"),
    [
        ("attribute def 'class';", "class", "class"),
        (
            "attribute def Data { attribute 'for'; }",
            "Data",
            "for",
        ),
    ],
)
def test_register_dataclass_rejects_python_keywords(
    tmp_path: Path,
    definition_source: str,
    definition_name: str,
    invalid_name: str,
) -> None:
    model = _load_inline_model(
        tmp_path,
        f"package KeywordNames {{ {definition_source} }}",
    )
    definition = resolve(
        model,
        syside.AttributeDefinition,
        f"KeywordNames::{definition_name}",
    )

    with pytest.raises(
        UnsupportedConstructError,
        match=rf"{invalid_name!r} is not a valid Python identifier",
    ):
        register_dataclass(definition, DataclassRegistry(), lambda _: "None")


def test_registry_is_idempotent_for_the_same_origin() -> None:
    registry = DataclassRegistry()
    registry.register("Reading", "Pkg::Reading", BLOCK_A)
    registry.register("Reading", "Pkg::Reading", BLOCK_A)
    assert registry.names() == ["Reading"]
    assert registry.is_registered("Reading", "Pkg::Reading")


def test_registry_rejects_two_origins_for_one_name() -> None:
    registry = DataclassRegistry()
    registry.register("Reading", "Pkg::Reading", BLOCK_A)
    with pytest.raises(UnsupportedConstructError, match="share the simple"):
        registry.register("Reading", "Other::Reading", BLOCK_A)
    assert not registry.is_registered("Reading", "Other::Reading")


def test_registry_rejects_conflicting_blocks_for_one_origin() -> None:
    registry = DataclassRegistry()
    registry.register("Reading", "Pkg::Reading", BLOCK_A)
    with pytest.raises(UnsupportedConstructError, match="conflicting"):
        registry.register("Reading", "Pkg::Reading", BLOCK_B)


def test_registry_blocks_are_sorted_and_blank_line_separated() -> None:
    registry = DataclassRegistry()
    registry.register("Zeta", "Pkg::Zeta", ("@dataclass", "class Zeta:"))
    registry.register("Alpha", "Pkg::Alpha", ("@dataclass", "class Alpha:"))
    assert registry.names() == ["Alpha", "Zeta"]
    assert registry.class_blocks() == [
        "@dataclass",
        "class Alpha:",
        "",
        "@dataclass",
        "class Zeta:",
    ]


def test_empty_registry_is_falsy_with_no_blocks() -> None:
    registry = DataclassRegistry()
    assert not registry
    assert registry.class_blocks() == []
    assert registry.module_lines() == []
    assert registry.module_lines(preceding_lines=["X = 1"]) == ["X = 1"]


def test_module_lines_wraps_blocks_with_headers() -> None:
    registry = DataclassRegistry()
    registry.register("Pt", "P::Pt", ("@dataclass", "class Pt:"))
    assert registry.module_lines() == [
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "",
        "@dataclass",
        "class Pt:",
    ]
    assert registry.module_lines(preceding_lines=["class E:", "    pass"]) == [
        "from __future__ import annotations",
        "",
        "class E:",
        "    pass",
        "",
        "from dataclasses import dataclass",
        "",
        "@dataclass",
        "class Pt:",
    ]


def test_types_import_lines_renders_one_guarded_line() -> None:
    assert types_import_lines("M_types", []) == []
    assert types_import_lines(None, []) == []
    assert types_import_lines("M_types", ["A", "B"]) == [
        "from M_types import A, B"
    ]
    with pytest.raises(ValueError, match="types module name"):
        types_import_lines(None, ["A"])


def test_generated_module_source_and_write(tmp_path: Path) -> None:
    module = GeneratedPythonModule("demo_types", ("X = 1",))
    assert module.source == "X = 1\n"
    path = module.write(tmp_path)
    assert path == tmp_path / "demo_types.py"
    assert path.read_text() == "X = 1\n"


def test_generated_module_install_is_idempotent_but_rejects_collision() -> None:
    name = "sysmlc_test_structured_install_types"
    module = GeneratedPythonModule(name, ("VALUE = 41",))
    try:
        installed = module.install()
        assert installed is module.install()
        assert installed.VALUE == 41
        clashing = GeneratedPythonModule(name, ("VALUE = 42",))
        with pytest.raises(
            UnsupportedConstructError, match="different content"
        ):
            clashing.install()
    finally:
        sys.modules.pop(name, None)


def test_generated_module_install_cleans_up_on_broken_source() -> None:
    name = "sysmlc_test_structured_broken_types"
    module = GeneratedPythonModule(name, ("raise RuntimeError('boom')",))
    try:
        with pytest.raises(RuntimeError, match="boom"):
            module.install()
        assert name not in sys.modules
    finally:
        sys.modules.pop(name, None)
