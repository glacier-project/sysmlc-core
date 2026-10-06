from __future__ import annotations

from pathlib import Path

import pytest

from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.foreign_artifact.metadata import (
    get_foreign_artifact_filepath_from_metadata,
)
from sysmlc.sysml.loading import load_model

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "external-module"


def test_basic_metadata_is_resolved_without_local_definition() -> None:
    model = load_model(FIXTURES_DIR / "external-module-basic")
    result = get_foreign_artifact_filepath_from_metadata(model, "python")
    assert result == ("basic_impl.py",)


def test_no_metadata_application_returns_none() -> None:
    model = load_model(FIXTURES_DIR / "external-module-absent")
    result = get_foreign_artifact_filepath_from_metadata(model, "python")
    assert result is None


def test_lang_mismatch_is_filtered_out() -> None:
    model = load_model(FIXTURES_DIR / "external-module-lang-mismatch")
    result = get_foreign_artifact_filepath_from_metadata(model, "python")
    assert result is None


def test_missing_lang_is_rejected() -> None:
    model = load_model(FIXTURES_DIR / "external-module-no-lang")
    with pytest.raises(UnsupportedConstructError, match="lang must evaluate"):
        get_foreign_artifact_filepath_from_metadata(model, "python")


def test_multiple_files_on_one_application_are_all_returned() -> None:
    model = load_model(FIXTURES_DIR / "external-module-multi-file")
    result = get_foreign_artifact_filepath_from_metadata(model, "python")
    assert result == ("a.py", "b.py")


def test_two_languages_on_the_same_element_are_both_found() -> None:
    """A single element can carry one @ForeignArtifact per language.

    Regression test: the underlying element query used to return only the
    first metadata application per element (see
    sysmlc.sysml.metadata.find_applied_metadata), so a second application
    of the same metadata definition -- here, a second language -- was
    invisible.
    """
    model = load_model(FIXTURES_DIR / "external-module-multi-lang")
    assert get_foreign_artifact_filepath_from_metadata(model, "python") == (
        "impl.py",
    )
    assert get_foreign_artifact_filepath_from_metadata(model, "c") == (
        "impl.c",
        "impl.h",
    )


def test_two_declarations_across_model_are_composed() -> None:
    model = load_model(FIXTURES_DIR / "external-module-multi-declaration")
    assert get_foreign_artifact_filepath_from_metadata(model, "python") == (
        "a.py",
        "b.py",
    )
