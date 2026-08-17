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


def test_missing_lang_matches_any_target() -> None:
    model = load_model(FIXTURES_DIR / "external-module-no-lang")
    result = get_foreign_artifact_filepath_from_metadata(model, "python")
    assert result == ("generic.py",)


def test_multiple_files_on_one_application_are_rejected() -> None:
    model = load_model(FIXTURES_DIR / "external-module-multi-file")
    with pytest.raises(
        UnsupportedConstructError, match="only a single file per module"
    ):
        get_foreign_artifact_filepath_from_metadata(model, "python")


def test_two_declarations_across_model_are_rejected() -> None:
    model = load_model(FIXTURES_DIR / "external-module-multi-declaration")
    with pytest.raises(
        UnsupportedConstructError,
        match="only one global @ForeignArtifact per model",
    ):
        get_foreign_artifact_filepath_from_metadata(model, "python")
