from pathlib import Path

from sysmlc.backends.base import OutputOptions, discover_backends
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.program import CProject


def test_entry_point_discovers_statix() -> None:
    assert "statix" in discover_backends()


def test_build_and_write_self_contained_project(
    sm_models: dict,
    path: Path,
) -> None:
    backend = StatixBackend()
    artifact = backend.build(sm_models["sm04"], "SM04::MachineEntryIncrement")
    written = backend.write(artifact, OutputOptions(output_dir=path))
    assert written
    assert (path / "include" / "sm04" / "machine_entry_increment.h").exists()
    assert (path / "src" / "sm04" / "machine_entry_increment.c").exists()
    assert (path / "host" / "sm04" / "machine_entry_increment_runner.c").exists()
    assert (path / "src" / "sc" / "sc_runtime.c").exists()
    assert (path / "include" / "sc" / "sc_runtime.h").exists()
    assert (path / "CMakeLists.txt").exists()


def test_build_model_writes_multiple_statecharts(
    sm_models: dict,
    path: Path,
) -> None:
    backend = StatixBackend()
    artifact = backend.build_model(sm_models["sm01"])
    assert isinstance(artifact, CProject)
    assert len(artifact.programs) == 3
    backend.write(artifact, OutputOptions(output_dir=path))
    assert (path / "src" / "sm01" / "machine.c").exists()
    assert (path / "src" / "sm01" / "machine_initial1_by_transition.c").exists()
    assert (path / "src" / "sm01" / "machine_initial3_by_qualified_name.c").exists()
    assert (path / "CMakeLists.txt").exists()


def test_summary(sm_models: dict) -> None:
    backend = StatixBackend()
    artifact = backend.build(sm_models["sm01"], "SM01::Machine")
    assert "Machine" in backend.summary(artifact)
