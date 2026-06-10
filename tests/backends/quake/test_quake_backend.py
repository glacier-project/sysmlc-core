from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sismic.model import Statechart

from sysmlc.backends import OutputOptions, discover_backends
from sysmlc.backends.quake.backend import QuakeBackend
from sysmlc.errors import SerializationError
from sysmlc.sysml.loading import load_model

if TYPE_CHECKING:
    import syside

SM_EXAMPLES_DIR = Path(__file__).resolve().parents[3] / "models" / "sm-examples"
SM01_DIR = SM_EXAMPLES_DIR / "sm01-helloworld"
MACHINE_QN = "SM01::Machine"


@pytest.fixture(scope="module")
def backend() -> QuakeBackend:
    return QuakeBackend()


@pytest.fixture(scope="module")
def model() -> syside.Model:
    return load_model(SM01_DIR)


@pytest.fixture(scope="module")
def artifact(backend: QuakeBackend, model: syside.Model) -> Statechart:
    result = backend.build(model, MACHINE_QN)
    assert isinstance(result, Statechart)
    return result


def test_build_returns_named_statechart(artifact: Statechart) -> None:
    assert artifact.name == "Machine"


def test_serialize_yaml(backend: QuakeBackend, artifact: Statechart) -> None:
    text = backend.serialize(artifact, "yaml")
    assert "statechart:" in text
    assert "idle" in text


def test_serialize_plantuml(
    backend: QuakeBackend, artifact: Statechart
) -> None:
    assert "@startuml" in backend.serialize(artifact, "plantuml")


def test_serialize_rejects_unknown_format(
    backend: QuakeBackend, artifact: Statechart
) -> None:
    with pytest.raises(SerializationError):
        backend.serialize(artifact, "json")


def test_write_defaults_to_all_formats(
    backend: QuakeBackend, artifact: Statechart, tmp_path: Path
) -> None:
    written = backend.write(artifact, OutputOptions(output_dir=tmp_path))
    assert sorted(p.name for p in written) == ["Machine.puml", "Machine.yaml"]
    assert "statechart:" in (tmp_path / "Machine.yaml").read_text()
    assert "@startuml" in (tmp_path / "Machine.puml").read_text()


def test_write_single_format(
    backend: QuakeBackend, artifact: Statechart, tmp_path: Path
) -> None:
    written = backend.write(
        artifact, OutputOptions(output_dir=tmp_path, formats=("yaml",))
    )
    assert [p.name for p in written] == ["Machine.yaml"]
    assert not (tmp_path / "Machine.puml").exists()


def test_write_basename_override(
    backend: QuakeBackend, artifact: Statechart, tmp_path: Path
) -> None:
    written = backend.write(
        artifact,
        OutputOptions(
            output_dir=tmp_path, formats=("yaml",), basename="custom"
        ),
    )
    assert [p.name for p in written] == ["custom.yaml"]


def test_write_creates_missing_output_dir(
    backend: QuakeBackend, artifact: Statechart, tmp_path: Path
) -> None:
    nested = tmp_path / "a" / "b"
    backend.write(artifact, OutputOptions(output_dir=nested, formats=("yaml",)))
    assert (nested / "Machine.yaml").is_file()


def test_summary_reports_counts(
    backend: QuakeBackend, artifact: Statechart
) -> None:
    summary = backend.summary(artifact)
    assert "Machine" in summary
    assert "states" in summary
    assert "transitions" in summary


def test_quake_backend_is_discoverable() -> None:
    backends = discover_backends()
    assert "quake" in backends
    assert isinstance(backends["quake"], QuakeBackend)
