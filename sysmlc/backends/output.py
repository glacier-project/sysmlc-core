"""An in-memory representation of a backend's generated output.

A backend describes what it generates as a :class:`GeneratedOutput`: a set
of text files at paths relative to the output directory. Folders are
implied by the paths. Building the description is separate from writing it,
so the output can be inspected without touching the disk, and every backend 
writes its files the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sysmlc.errors import SerializationError

if TYPE_CHECKING:
    from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class GeneratedFile:
    """One generated text file.

    Attributes:
        path: Location relative to the output directory, using ``/`` as the
            separator. It must name a file inside the output directory: it
            cannot be absolute, empty, or contain ``..``.
        content: The complete text of the file.

    Raises:
        SerializationError: If ``path`` is absolute, empty, or contains
            ``..``.
    """

    path: PurePosixPath
    content: str

    def __post_init__(self) -> None:
        if self.path.is_absolute() or not self.path.parts:
            raise SerializationError(
                f"generated file path '{self.path}' must be a relative "
                "path to a file"
            )
        if ".." in self.path.parts:
            raise SerializationError(
                f"generated file path '{self.path}' must stay inside the "
                "output directory"
            )


@dataclass(frozen=True)
class GeneratedOutput:
    """The complete set of files a backend generates for one artifact.

    Attributes:
        files: The generated files, in the order they are written and
            reported. No two files share a path, and no file's path is also
            used as a folder by another file.

    Raises:
        SerializationError: If two files share a path, or a file's path is
            also a folder of another file.
    """

    files: tuple[GeneratedFile, ...]

    def __post_init__(self) -> None:
        paths: set[PurePosixPath] = set()
        for file in self.files:
            if file.path in paths:
                raise SerializationError(
                    f"two generated files share the path '{file.path}'"
                )
            paths.add(file.path)
        folders = {parent for path in paths for parent in path.parents}
        conflicts = sorted(paths & folders)
        if conflicts:
            raise SerializationError(
                f"generated path '{conflicts[0]}' is both a file and a folder"
            )

    @property
    def paths(self) -> tuple[PurePosixPath, ...]:
        """Return the relative path of every file, in order."""
        return tuple(file.path for file in self.files)

    def content(self, path: PurePosixPath) -> str:
        """Return the content of the file at ``path``.

        Args:
            path: The file's path relative to the output directory.

        Returns:
            The complete text of the file.

        Raises:
            KeyError: If no generated file has that path.
        """
        for file in self.files:
            if file.path == path:
                return file.content
        raise KeyError(str(path))

    def write(self, output_dir: Path) -> list[Path]:
        """Write every file under ``output_dir``, creating folders as needed.

        Existing files at the same paths are replaced.

        Args:
            output_dir: The directory the relative file paths start from. It
                is created when missing.

        Returns:
            The written paths, in the order of :attr:`files`.
        """
        written: list[Path] = []
        output_dir.mkdir(parents=True, exist_ok=True)
        for file in self.files:
            target = output_dir.joinpath(*file.path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content)
            written.append(target)
        return written
