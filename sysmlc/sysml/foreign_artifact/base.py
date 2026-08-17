"""A code written in a non SysMLv2 langauge.

A Foreign Artifact could be:
- an external file passed by CLI.
- an external file defined in the metadata (transformed into a external file).
- a textual representation (transformed into a external file).
this file is parse into an object with structure of:
- language which is written the file
- path
- file name
- all the names of the functions declered in the file
"""

import ast
import atexit
import shutil
import tempfile
from pathlib import Path

import syside

from sysmlc.errors import SysmlcError
from sysmlc.sysml.foreign_artifact.metadata import (
    get_foreign_artifact_filepath_from_metadata,
)
from sysmlc.sysml.foreign_artifact.text_rep import extract_text_rep, write_file

SUPPORTED_LANG = [
    "python",
]


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
    ):
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
    if lang not in SUPPORTED_LANG:
        raise ForeignArtifactError(
            f"foreign artifact of language {lang} not supported"
        )

    external: list[ForeignArtifact] = []

    # Searching in metadatas for foreign artifact
    external.extend(parse_metadata(model_dir, model, lang))
    # Seraching textual rep
    if text_rep := parse_text_rep(model, element_qn, lang):
        external.append(text_rep)

    return external


# FA from MetaData
def parse_metadata(
    model_dir: Path,
    model: syside.Model,
    lang: str,
) -> list[ForeignArtifact]:
    """Parse a Metadata of Foreign Artifact into a ``ForeignArtifact`` if any."""
    external: list[ForeignArtifact] = []
    for raw_path in get_foreign_artifact_filepath_from_metadata(model, lang):
        raw_path = Path(raw_path)
        path = raw_path if raw_path.is_absolute() else model_dir / raw_path
        external.append(ForeignArtifact(path, lang))
    return external


# FA from TextRep
def parse_text_rep(
    model: syside.Model,
    element_qn: str,
    lang: str,
) -> ForeignArtifact | None:
    """Parse a TextRep into ``ForeignArtifact`` if any.

    Parse all the Textual Representation found in a model
    into a new file and parse the file into ``ForeignArtifact``.
    """
    text_rep = extract_text_rep(model, element_qn)
    if not text_rep:
        return None

    file_name, source_lines = text_rep
    out_dir = Path(tempfile.mkdtemp(prefix="sysmlc-reps-"))
    atexit.register(shutil.rmtree, out_dir, ignore_errors=True)
    file_path = write_file(source_lines, out_dir, file_name)

    return ForeignArtifact(
        file_path,
        lang,
    )


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
    if lang == "python":
        tree = ast.parse(module_path.read_text(), filename=str(module_path))
        return frozenset(
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        )
    raise ForeignArtifactError(
        f"{lang} not supported yet for foreign artifact."
    )
