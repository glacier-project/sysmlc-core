from __future__ import annotations

import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import syside

from sysmlc.cli import _build_parser, _load_external_modules
from sysmlc.errors import UnsupportedConstructError
from sysmlc.sysml.foreign_artifact.base import (
    ExternalDependency,
    ForeignArtifact,
    ForeignArtifactError,
    collect_foreign_dependencies,
    interpret_artifacts,
    parse_metadata,
    parse_text_rep,
    resolve_foreign_artifact,
)
from sysmlc.sysml.foreign_artifact.languages import (
    get_language,
    register_language,
)
from sysmlc.sysml.loading import load_model


def _model(folder: Path, body: str) -> syside.Model:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "model.sysml").write_text(
        "package Example { private import ScalarValues::*; "
        "private import ForeignArtifactBinding::*; " + body + " }"
    )
    return load_model(folder)


def test_declarations_are_frozen_canonical_and_do_not_read_source(
    tmp_path: Path,
) -> None:
    path = tmp_path / "not-created.py"
    artifact = ForeignArtifact(path, " Python ")
    assert artifact.lang == "python"
    assert artifact.path.is_absolute()
    assert not hasattr(artifact, "funct_names")
    with pytest.raises(FrozenInstanceError):
        field = "lang"
        setattr(artifact, field, "c")
    dependency = ExternalDependency(" Python ", (path, path))
    assert dependency.language == "python"
    assert dependency.files == (path.resolve(),)


def test_evaluated_metadata_uses_each_documents_origin(tmp_path: Path) -> None:
    for name, file in (("first space", "one.py"), ("second", "two.py")):
        folder = tmp_path / name
        folder.mkdir()
        (folder / file).write_text("def step(): return 1\n")
        (folder / "model.sysml").write_text(
            f"package {file.split('.')[0]} {{ "
            "private import ScalarValues::*; "
            "private import ForeignArtifactBinding::*; "
            f'attribute sourcePath : String = "{file}"; '
            '@ForeignArtifact { lang = "python"; files = sourcePath; } }'
        )
    model = load_model(tmp_path)
    artifacts = parse_metadata(tmp_path, model, "python")
    assert {a.path for a in artifacts} == {
        tmp_path / "first space/one.py",
        tmp_path / "second/two.py",
    }


@pytest.mark.parametrize(
    "broken",
    [
        '@ForeignArtifact { lang = "python"; files = "missing.py"; }',
        'calc def step { rep impl language "Python" /* def step( */ }',
    ],
)
def test_override_skips_unavailable_or_invalid_model_sources(
    tmp_path: Path,
    broken: str,
) -> None:
    model = _model(tmp_path / "model", broken)
    provided = tmp_path / "override.py"
    provided.write_text("def step(): return 1\n")
    artifacts = resolve_foreign_artifact(
        tmp_path / "model",
        model,
        "Example::step",
        overrides=(provided, provided),
    )
    assert artifacts == [ForeignArtifact(provided, "python")]


def test_override_is_per_language(tmp_path: Path) -> None:
    model = _model(
        tmp_path,
        """
        @ForeignArtifact { lang = "python"; files = "missing.py"; }
        @ForeignArtifact { lang = "c"; files = "impl.c"; }
    """,
    )
    python = tmp_path / "override.py"
    python.write_text("def step(): return 1\n")
    c = tmp_path / "impl.c"
    c.write_text("double step(void) { return 1; }\n")
    declarations = collect_foreign_dependencies(
        tmp_path,
        model,
        "Example",
        ("python", "c"),
        overrides={"python": (python,)},
    )
    assert {d.language: d.files for d in declarations} == {
        "python": (python,),
        "c": (c,),
    }


def test_invalid_evaluated_metadata_is_diagnosed(tmp_path: Path) -> None:
    model = _model(
        tmp_path,
        """
        attribute empty : String[*] = ();
        @ForeignArtifact { lang = "python"; files = empty; }
    """,
    )
    with pytest.raises(UnsupportedConstructError, match="files must evaluate"):
        parse_metadata(tmp_path, model, "python")


def test_duplicate_symbols_are_rejected_in_either_order(tmp_path: Path) -> None:
    files = []
    for name in ("first", "second"):
        path = tmp_path / f"{name}.py"
        path.write_text("def step(): return 1\n")
        files.append(ForeignArtifact(path, "python"))
    for ordered in (files, files[::-1]):
        with pytest.raises(
            ForeignArtifactError, match="ambiguous python function 'step'"
        ):
            interpret_artifacts(ordered, "python")


def test_runtime_loading_rejects_module_collisions_before_execution(
    tmp_path: Path,
) -> None:
    artifacts = []
    for folder in ("one", "two"):
        path = tmp_path / folder / "support.py"
        path.parent.mkdir()
        path.write_text("raise AssertionError('must not execute')\n")
        artifacts.append(ForeignArtifact(path, "python"))
    with pytest.raises(ForeignArtifactError, match="same output filename"):
        _load_external_modules(artifacts)


def test_c_parser_handles_comments_pointers_and_header_scope() -> None:
    assert get_language("c").function_names("""
        /* double phantom(double x) { return x; } */
        double *step(double *x) { return x; }
    """) == {"step"}
    assert get_language("c_h").function_names("""
        static inline double wrapper(double x) { return step(x); }
        double *step(double *x);
    """) == {"step"}
    assert (
        get_language("c_h").function_names("""
        static inline double wrapper(double x) { return step(x); }
    """)
        == set()
    )


def test_generated_c_header_preserves_types_and_deduplicates_helpers(
    tmp_path: Path,
) -> None:
    model = _model(
        tmp_path,
        """
        package A { rep impl language "C" /*
            typedef double Value;
            double helper(double x) { return x; }
        */ }
        package B { rep impl language "C" /*
            double helper(double x) { return x; }
        */ }
        calc def transform {
            in x : Real; return : Real;
            rep impl language "C" /* Value transform(Value x) { return x; } */
        }
    """,
    )
    artifacts = parse_text_rep(model, "Example::transform", "c")
    source, header = artifacts
    assert source.path.read_text().count("double helper(") == 1
    assert "typedef double Value;" in header.path.read_text()
    for args in (
        ("-c", str(source.path), "-o", str(tmp_path / "impl.o")),
        ("-x", "c", "-fsyntax-only", str(header.path)),
    ):
        result = subprocess.run(["cc", *args], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_registered_language_is_available_to_the_cli() -> None:
    from tests.backends.test_base import _StubBackend

    class Rust:
        name = "rust"
        extension = "rs"
        comment = "//"

        def validate(self, source: str) -> None:
            pass

        def function_names(self, source: str) -> frozenset[str]:
            return frozenset()

    register_language(Rust())
    parser = _build_parser({"custom": _StubBackend("custom", ("rust",))})
    args = parser.parse_args(["custom", "build", ".", "--rust", "impl.rs"])
    assert args.rust == [Path("impl.rs")]
