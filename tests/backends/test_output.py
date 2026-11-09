from pathlib import Path, PurePosixPath

import pytest

from sysmlc.backends import GeneratedFile, GeneratedOutput
from sysmlc.errors import SerializationError


def test_write_creates_folders_and_files_with_their_content(
    tmp_path: Path,
) -> None:
    output = GeneratedOutput(
        (
            GeneratedFile(PurePosixPath("Main.lf"), "target Python\n"),
            GeneratedFile(PurePosixPath("src/lib/types.h"), "#pragma once\n"),
        )
    )

    output.write(tmp_path)

    assert (tmp_path / "Main.lf").read_text() == "target Python\n"
    assert (tmp_path / "src/lib/types.h").read_text() == "#pragma once\n"


def test_write_creates_a_missing_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "does" / "not" / "exist"

    GeneratedOutput((GeneratedFile(PurePosixPath("a.txt"), "a"),)).write(
        output_dir
    )

    assert (output_dir / "a.txt").read_text() == "a"


def test_write_returns_the_written_paths_in_declared_order(
    tmp_path: Path,
) -> None:
    output = GeneratedOutput(
        (
            GeneratedFile(PurePosixPath("z.lf"), ""),
            GeneratedFile(PurePosixPath("a/m.py"), ""),
            GeneratedFile(PurePosixPath("b.py"), ""),
        )
    )

    assert output.write(tmp_path) == [
        tmp_path / "z.lf",
        tmp_path / "a" / "m.py",
        tmp_path / "b.py",
    ]


def test_write_replaces_an_existing_file(tmp_path: Path) -> None:
    (tmp_path / "Main.lf").write_text("stale")

    GeneratedOutput((GeneratedFile(PurePosixPath("Main.lf"), "fresh"),)).write(
        tmp_path
    )

    assert (tmp_path / "Main.lf").read_text() == "fresh"


def test_content_is_looked_up_by_relative_path() -> None:
    output = GeneratedOutput(
        (
            GeneratedFile(PurePosixPath("Main.lf"), "lf"),
            GeneratedFile(PurePosixPath("src/types.py"), "py"),
        )
    )

    assert output.content(PurePosixPath("src/types.py")) == "py"
    assert output.content(PurePosixPath("Main.lf")) == "lf"
    assert output.paths == (
        PurePosixPath("Main.lf"),
        PurePosixPath("src/types.py"),
    )


def test_content_of_an_unknown_path_raises_key_error() -> None:
    output = GeneratedOutput((GeneratedFile(PurePosixPath("Main.lf"), "lf"),))

    with pytest.raises(KeyError):
        output.content(PurePosixPath("Other.lf"))


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "../outside.lf", "src/../../outside.lf", "", "."],
)
def test_file_path_must_stay_inside_the_output_directory(path: str) -> None:
    with pytest.raises(SerializationError):
        GeneratedFile(PurePosixPath(path), "")


def test_two_files_cannot_share_a_path() -> None:
    with pytest.raises(SerializationError, match=r"src/Main\.lf"):
        GeneratedOutput(
            (
                GeneratedFile(PurePosixPath("src/Main.lf"), "one"),
                GeneratedFile(PurePosixPath("src/Main.lf"), "two"),
            )
        )


def test_a_file_cannot_also_be_a_folder() -> None:
    with pytest.raises(
        SerializationError, match="'src' is both a file and a folder"
    ):
        GeneratedOutput(
            (
                GeneratedFile(PurePosixPath("src"), "a file"),
                GeneratedFile(PurePosixPath("src/Main.lf"), "inside a folder"),
            )
        )
