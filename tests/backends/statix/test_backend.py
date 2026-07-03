from sysmlc.backends.base import OutputOptions, discover_backends
from sysmlc.backends.statix.backend import StatixBackend


def test_entry_point_discovers_statix():
    assert "statix" in discover_backends()


def test_build_and_write_self_contained_project(sm_models, tmp_path):
    backend = StatixBackend()
    artifact = backend.build(sm_models["sm04"], "SM04::MachineEntryIncrement")
    written = backend.write(artifact, OutputOptions(output_dir=tmp_path))
    names = {p.name for p in written}
    assert "machineentryincrement_actions.c" in names
    assert (tmp_path / "src" / "sc_runtime.c").exists()
    assert (tmp_path / "include" / "sc" / "sc_runtime.h").exists()
    assert (tmp_path / "CMakeLists.txt").exists()


def test_summary(sm_models):
    backend = StatixBackend()
    artifact = backend.build(sm_models["sm01"], "SM01::Machine")
    assert "Machine" in backend.summary(artifact)
