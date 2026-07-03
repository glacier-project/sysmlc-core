from sysmlc.backends.base import OutputOptions, discover_backends
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.program import CProject


def test_entry_point_discovers_statix():
    assert "statix" in discover_backends()


def test_build_and_write_self_contained_project(sm_models, tmp_path):
    backend = StatixBackend()
    artifact = backend.build(sm_models["sm04"], "SM04::MachineEntryIncrement")
    written = backend.write(artifact, OutputOptions(output_dir=tmp_path))
    assert written
    assert (tmp_path / "include" / "sm04" / "machineentryincrement.h").exists()
    assert (tmp_path / "src" / "sm04" / "machineentryincrement.c").exists()
    assert (
        tmp_path / "host" / "sm04" / "machineentryincrement_runner.c"
    ).exists()
    assert (tmp_path / "src" / "sc" / "sc_runtime.c").exists()
    assert (tmp_path / "include" / "sc" / "sc_runtime.h").exists()
    assert (tmp_path / "CMakeLists.txt").exists()


def test_build_model_writes_multiple_statecharts(sm_models, tmp_path):
    backend = StatixBackend()
    artifact = backend.build_model(sm_models["sm01"])
    assert isinstance(artifact, CProject)
    assert len(artifact.programs) == 3
    backend.write(artifact, OutputOptions(output_dir=tmp_path))
    assert (tmp_path / "src" / "sm01" / "machine.c").exists()
    assert (
        tmp_path / "src" / "sm01" / "machineinitial1_bytransition.c"
    ).exists()
    assert (
        tmp_path / "src" / "sm01" / "machineinitial3_byqualifiedname.c"
    ).exists()
    assert (tmp_path / "CMakeLists.txt").exists()


def test_summary(sm_models):
    backend = StatixBackend()
    artifact = backend.build(sm_models["sm01"], "SM01::Machine")
    assert "Machine" in backend.summary(artifact)
