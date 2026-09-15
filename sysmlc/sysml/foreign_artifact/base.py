"""A code written in a non SysMLv2 language.

A Foreign Artifact could be:
- an external file passed by CLI.
- an external file defined in the metadata (transformed into a external file).
- a textual representation (transformed into a external file).
this file is parse into an object with structure of:
- language which is written the file
- path
- file name
- all the names of the functions declared in the file
"""

import atexit
import re
import shutil
import tempfile
from pathlib import Path

import syside

from sysmlc.errors import SysmlcError, UnsupportedConstructError
from sysmlc.sysml.foreign_artifact.languages import (
    c_function_declarations,
    get_language,
)
from sysmlc.sysml.foreign_artifact.metadata import (
    get_foreign_artifact_filepath_from_metadata,
)
from sysmlc.sysml.foreign_artifact.text_rep import (
    extract_text_rep,
    write_file,
)


class ForeignArtifact:
    """An external file bounded to a sysml model in a specific language."""

    lang: str
    path: Path
    file_name: str
    funct_names: frozenset[str]

    def __init__(
        self,
        path: Path,
        lang: str,
    ) -> None:
        self.path = path
        self.lang = lang
        self.file_name, self.funct_names = parse_artifact(path, lang)

    def __hash__(self) -> int:
        return hash((self.path, self.lang))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ForeignArtifact):
            return NotImplemented
        return self.path == other.path and self.lang == other.lang


class ForeignArtifactError(SysmlcError):
    """A user-facing error, reported as a message without a traceback."""


def resolve_foreign_artifact(
    model_dir: Path,
    model: syside.Model,
    element_qn: str,
    lang: str = "python",
) -> list[ForeignArtifact]:
    """Collect every Foreign Artifact present in the model."""
    # check if is a supported lang
    try:
        _ = get_language(lang)
    except UnsupportedConstructError:
        raise ForeignArtifactError(
            f"foreign artifact of language {lang} not supported"
        ) from None

    external: list[ForeignArtifact] = []

    # Searching in metadatas for foreign artifact
    external.extend(parse_metadata(model_dir, model, lang))
    # Searching textual rep
    external.extend(parse_text_rep(model, element_qn, lang))

    return external


# FA from MetaData
def parse_metadata(
    model_dir: Path,
    model: syside.Model,
    lang: str,
) -> list[ForeignArtifact]:
    """Parse a Metadata of Foreign Artifact into a ``ForeignArtifact`` if any."""
    external: list[ForeignArtifact] = []
    for raw_path in (
        get_foreign_artifact_filepath_from_metadata(model, lang) or []
    ):
        raw_path = Path(raw_path)
        path = raw_path if raw_path.is_absolute() else model_dir / raw_path
        external.append(ForeignArtifact(path, lang))
    return external


# FA from TextRep
def parse_text_rep(
    model: syside.Model,
    element_qn: str,
    lang: str,
) -> list[ForeignArtifact]:
    """Parse a TextRep into ``ForeignArtifact``(s), or ``[]`` if none.

    Parses all the Textual Representation bodies found in a model into a
    new file and parses that file into a ``ForeignArtifact``.

    A ``"c"`` rep also gets a synthesized companion header, returned as a
    second, ``"c_h"`` artifact: unlike a metadata- or CLI-supplied file,
    there is no user-authored header to provide one here, and sysmlc
    already knows every function the extracted body defines -- a backend
    that requires a declared companion for a backed extern (see
    ``sysmlc_statix``) would otherwise reject this path outright.
    """
    text_rep = extract_text_rep(model, element_qn, lang)
    if not text_rep:
        return []

    file_name, source_lines = text_rep
    out_dir = Path(tempfile.mkdtemp(prefix="sysmlc-reps-"))
    atexit.register(shutil.rmtree, out_dir, ignore_errors=True)
    file_path = write_file(source_lines, out_dir, file_name, lang)
    artifacts = [ForeignArtifact(file_path, lang)]

    if lang.strip().lower() == "c":
        declarations = c_function_declarations("\n".join(source_lines))
        if declarations:
            header_path = write_file(
                _c_header_lines(file_name, declarations),
                out_dir,
                file_name,
                "c_h",
            )
            artifacts.append(ForeignArtifact(header_path, "c_h"))

    return artifacts


def _c_header_lines(file_name: str, declarations: tuple[str, ...]) -> list[str]:
    """Assemble a minimal, include-guarded C header from declarations."""
    guard = re.sub(r"[^0-9A-Za-z]", "_", file_name).upper() + "_H"
    return [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        *declarations,
        "",
        f"#endif /* {guard} */",
    ]


def parse_raw_file(
    file_path: Path,
    lang: str,
) -> ForeignArtifact:
    """Parse a file into a ``ForeignArtifact``."""
    return ForeignArtifact(
        file_path,
        lang,
    )


def parse_artifact(
    file_path: Path,
    lang: str = "python",
) -> tuple[str, frozenset[str]]:
    """Parse a file into ``(file_name, sync_function_names)``.

    Raises:
        ForeignArtifactError If the file cannot be read.
    """
    try:
        names = get_functions_names(file_path, lang)
    except OSError as error:
        raise ForeignArtifactError(
            f"cannot read file {file_path}: {error}"
        ) from error
    except SyntaxError as error:
        raise ForeignArtifactError(
            f"file {file_path} is not valid: {error}"
        ) from error

    return file_path.stem, names


def get_functions_names(
    module_path: Path,
    lang: str = "python",
) -> frozenset[str]:
    """Names of the module's top-level synchronous function defs.

    These are the names a backing module offers to calc-def call sites;
    an ``async def`` cannot back a synchronous call, so it is excluded.

    Raises:
        OSError: If the file cannot be read.
        SyntaxError: If the file is not valid Python.
        ForeignArtifactError: If requested a language not supported
    """
    try:
        return get_language(lang).function_names(module_path.read_text())
    except (OSError, SyntaxError, UnsupportedConstructError) as error:
        raise ForeignArtifactError(str(error)) from error
