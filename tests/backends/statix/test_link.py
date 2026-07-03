import subprocess

import pytest

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend

pytestmark = pytest.mark.statix


def test_multiple_statecharts_link_into_one_project(sm_models, tmp_path):
    # SM01 declares three state defs; build them all into one project.
    project = StatixBackend().build_model(sm_models["sm01"])
    assert len(project.programs) == 3
    StatixBackend().write(project, OutputOptions(output_dir=tmp_path))

    build = tmp_path / "build"
    subprocess.run(
        ["cmake", "-S", str(tmp_path), "-B", str(build)],
        check=True,
        capture_output=True,
    )
    # The whole project (shared runtime + 3 statechart units + 3 runners) must
    # compile and link with no duplicate-symbol errors under strict warnings.
    subprocess.run(
        ["cmake", "--build", str(build)],
        check=True,
        capture_output=True,
    )

    # Each generated runner must run; sm01_machine settles idle -> running.
    out = subprocess.run(
        [str(build / "sm01_machine_runner")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "state=running" in out.stdout
