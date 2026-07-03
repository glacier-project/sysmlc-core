from sysmlc.backends.base import OutputOptions, discover_backends
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.program import CProject


def test_entry_point_discovers_statix():
    assert "statix" in discover_backends()


def test_build_and_write_self_contained_project(sm_models, tmp_path):
    backend = StatixBackend()
    artifact = backend.build(sm_models["sm04"], "SM04::MachineEntryIncrement")
    written = backend.write(artifact, OutputOptions(output_dir=tmp_path))
    names = {p.name for p in written}
    assert "sm04_machineentryincrement.c" in names
    assert "sm04_machineentryincrement.h" in names
    assert "sm04_machineentryincrement_runner.c" in names
    assert (tmp_path / "src" / "sc_runtime.c").exists()
    assert (tmp_path / "include" / "sc" / "sc_runtime.h").exists()
    assert (tmp_path / "CMakeLists.txt").exists()


def test_build_model_writes_multiple_statecharts(sm_models, tmp_path):
    backend = StatixBackend()
    artifact = backend.build_model(sm_models["sm01"])
    assert isinstance(artifact, CProject)
    assert len(artifact.programs) == 3
    written = backend.write(artifact, OutputOptions(output_dir=tmp_path))
    names = {p.name for p in written}
    assert "sm01_machine.c" in names
    assert "sm01_machineinitial1_bytransition.c" in names
    assert "sm01_machineinitial3_byqualifiedname.c" in names
    assert "CMakeLists.txt" in names


def test_summary(sm_models):
    backend = StatixBackend()
    artifact = backend.build(sm_models["sm01"], "SM01::Machine")
    assert "Machine" in backend.summary(artifact)
