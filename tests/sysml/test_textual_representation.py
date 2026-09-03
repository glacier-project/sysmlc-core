from __future__ import annotations

from pathlib import Path

import pytest

from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.foreign_artifact.base import parse_artifact, parse_text_rep
from sysmlc.sysml.foreign_artifact.text_rep import (
    extract_text_rep,
    write_file,
)
from sysmlc.sysml.loading import load_model

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_starred_unpacking_line_survives_verbatim() -> None:
    model = load_model(FIXTURES_DIR / "rep-star")
    result = extract_text_rep(model, "StarProof::unpack_last")
    assert result is not None
    _stem, lines = result
    assert "    *head, tail = values" in lines


def test_package_rep_collected_as_module_scaffolding() -> None:
    model = load_model(FIXTURES_DIR / "rep-package-scaffolding")
    result = extract_text_rep(model, "Scaffold::quadruple")
    assert result is not None
    _stem, lines = result
    assert "FACTOR = 2.0" in lines
    assert "def quadruple(x):" in lines
    # The package rep is the module preamble: it precedes the functions.
    assert lines.index("FACTOR = 2.0") < lines.index("def quadruple(x):")


def test_python_rep_outside_package_or_calc_def_is_rejected() -> None:
    model = load_model(FIXTURES_DIR / "rep-on-action")
    with pytest.raises(UnsupportedConstructError, match="logIt"):
        extract_text_rep(model, "RepOnAction::logIt")


def test_invalid_python_in_a_rep_body_names_the_calc_def() -> None:
    model = load_model(FIXTURES_DIR / "rep-bad-syntax")
    with pytest.raises(UnsupportedConstructError, match="BadSyntax::broken"):
        extract_text_rep(model, "BadSyntax::broken")


def test_generated_module_feeds_parse_external(tmp_path: Path) -> None:
    # The generated module goes through the same name harvesting as a
    # user-supplied --python file: every top-level def is importable,
    # scaffolding helpers included.
    model = load_model(FIXTURES_DIR / "rep-package-scaffolding")
    result = extract_text_rep(model, "Scaffold::quadruple")
    assert result is not None
    stem, lines = result
    module_path = write_file(lines, tmp_path, stem)
    parsed_stem, names = parse_artifact(module_path)
    assert parsed_stem == "quadruple_impl"
    assert names == frozenset({"quadruple", "_twice"})


def test_two_python_reps_on_one_calc_def_are_rejected() -> None:
    model = load_model(FIXTURES_DIR / "rep-two-bodies")
    with pytest.raises(UnsupportedConstructError, match="more than one Python"):
        extract_text_rep(model, "TwoBodies::double")


def test_def_name_mismatch_names_both_sides() -> None:
    model = load_model(FIXTURES_DIR / "rep-name-mismatch")
    with pytest.raises(
        UnsupportedConstructError,
        match="defines 'restrictAngle' but the calc def is named",
    ):
        extract_text_rep(model, "NameMismatch::restrict_angle")


def test_conflicting_defs_across_packages_are_rejected() -> None:
    model = load_model(FIXTURES_DIR / "rep-name-collision")
    with pytest.raises(
        UnsupportedConstructError, match="different implementations"
    ):
        extract_text_rep(model, "Collision::step")


def test_scaffolding_def_shadowing_a_calc_def_is_rejected() -> None:
    model = load_model(FIXTURES_DIR / "rep-scaffolding-shadow")
    with pytest.raises(
        UnsupportedConstructError, match="different implementations"
    ):
        extract_text_rep(model, "Shadow::gain")


def test_identical_duplicate_helpers_stay_allowed() -> None:
    model = load_model(FIXTURES_DIR / "rep-duplicate-identical")
    result = extract_text_rep(model, "DupA::use_sign")
    assert result is not None


def test_c_rep_is_written_and_function_names_are_harvested(
    tmp_path: Path,
) -> None:
    model = load_model(FIXTURES_DIR / "rep-c")
    result = extract_text_rep(model, "CRep::increment", "c")
    assert result is not None
    stem, lines = result
    module_path = write_file(lines, tmp_path, stem, "c")

    assert module_path.suffix == ".c"
    assert parse_artifact(module_path, "c") == (
        "increment_impl",
        frozenset({"increment"}),
    )


def test_c_text_rep_uses_c_extension_when_resolved() -> None:
    model = load_model(FIXTURES_DIR / "rep-c")
    artifact = parse_text_rep(model, "CRep::increment", "c")
    assert artifact is not None
    assert artifact.path.suffix == ".c"
    assert artifact.funct_names == frozenset({"increment"})
