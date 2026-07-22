"""Cross-TU ABI propagation test for SC_EVENT_PAYLOAD_SIZE.

See docs/superpowers/specs/2026-07-16-statix-payload-marshalling-design.md
Sec.2 item 8 -- this is deliberately a SEPARATE executable added to a
generated project's own CMakeLists.txt, linking (not recompiling) the
generated statix_statecharts library, so that a passing result is genuine
evidence of cross-translation-unit ABI agreement, not a single TU agreeing
with itself.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from sysmlc.backends.base import OutputOptions
from sysmlc.backends.statix.backend import StatixBackend
from sysmlc.backends.statix.builder import build_statix
from sysmlc.sysml.loading import load_model

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "payload_abi_host.c"


def test_payload_abi_host_inherits_size_through_public_link(
    tmp_path: Path,
) -> None:
    model = load_model("models/sm-examples/sm11-send-effect")
    program = build_statix(model, "SM11::MachineReadablePayloadWhole")
    StatixBackend().write(program, OutputOptions(output_dir=tmp_path))

    host_dir = tmp_path / "host"
    host_dir.mkdir(exist_ok=True)
    (host_dir / "payload_abi_host.c").write_text(_FIXTURE.read_text())

    cmakelists = tmp_path / "CMakeLists.txt"
    cmakelists.write_text(
        cmakelists.read_text()
        + "\nadd_executable(payload_abi_host host/payload_abi_host.c)\n"
        "target_link_libraries(payload_abi_host PRIVATE statix_statecharts)\n"
    )

    build = tmp_path / "build"
    subprocess.run(
        ["cmake", "-S", str(tmp_path), "-B", str(build)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["cmake", "--build", str(build), "--target", "payload_abi_host"],
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        [str(build / "payload_abi_host")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
