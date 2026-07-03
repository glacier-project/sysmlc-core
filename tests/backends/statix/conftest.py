import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import syside

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.program import CProgram
from sysmlc.backends.statix.serialize import emit_context_initializer
from sysmlc.sysml.loading import load_model

_MODELS = Path(__file__).resolve().parents[3] / "models" / "sm-examples"

# The sm-examples referenced across the statix backend tests, by folder stem.
_WANTED = {
    "sm01",
    "sm02",
    "sm03",
    "sm04",
    "sm05",
    "sm06",
    "sm07",
    "sm08",
    "sm09",
    "sm11",
}


@pytest.fixture(scope="session")
def sm_models() -> dict[str, syside.Model]:
    """Load each referenced sm-example once, keyed by folder stem (sm01…)."""
    out: dict[str, syside.Model] = {}
    for folder in sorted(_MODELS.glob("sm*-*")):
        stem = folder.name.split("-")[0]
        if stem in _WANTED:
            out[stem] = load_model(folder)
    return out


def _demo_main(program: CProgram) -> str:
    """A tiny host main: init the machine and print its settled state id."""
    p = program.prefix
    init = emit_context_initializer(program)
    ctx_line = (
        f"    {p}_context_t ctx = {{0}};"
        if init == f"{p}_context_t"
        else f"    {p}_context_t ctx = {init};"
    )
    return (
        f'#include "{p}_statechart_config.h"\n'
        f'#include "{p}_context.h"\n'
        "#include <stdio.h>\n\n"
        "int main(void) {\n"
        f"{ctx_line}\n"
        "    sc_runtime_t rt;\n"
        f"    sc_status_t st = sc_runtime_init(&rt, "
        f"&{p}_statechart_machine, &ctx);\n"
        "    sc_state_id_t state = SC_STATE_INVALID;\n"
        "    (void)sc_runtime_get_state(&rt, &state);\n"
        '    (void)printf("status=%d state=%u\\n", (int)st, (unsigned)state);\n'
        "    return st == SC_STATUS_OK ? 0 : 1;\n"
        "}\n"
    )


@pytest.fixture
def statix_run(
    tmp_path: Path,
) -> Callable[[CProgram], int]:
    """Return a callable that builds, compiles, and runs a program.

    The callable writes the generated project + a demo ``main.c`` into a temp
    dir, compiles it via the generated CMake (under the strict warning set),
    runs it, and returns the machine's settled state id.
    """

    def _run(program: CProgram) -> int:
        StatixBackend().write(program, OutputOptions(output_dir=tmp_path))
        (tmp_path / "main.c").write_text(_demo_main(program))
        cml = tmp_path / "CMakeLists.txt"
        cml.write_text(
            cml.read_text().replace(
                f"{program.prefix}_actions.c)",
                f"{program.prefix}_actions.c)\n\n"
                "add_executable(demo main.c)\n"
                f"target_link_libraries(demo {program.prefix}_statechart)\n",
            )
        )
        build = tmp_path / "build"
        subprocess.run(
            ["cmake", "-S", str(tmp_path), "-B", str(build)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["cmake", "--build", str(build)],
            check=True,
            capture_output=True,
        )
        out = subprocess.run(
            [str(build / "demo")],
            check=True,
            capture_output=True,
            text=True,
        )
        return int(out.stdout.split("state=")[1].split()[0])

    return _run
