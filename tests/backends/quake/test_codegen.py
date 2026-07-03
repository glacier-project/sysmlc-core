from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import syside

from sysmlc.backends.quake.codegen import SismicCodeGen
from sysmlc.codegen.python import PythonCodeGenContext
from tests import _load_inline_model, _single_element


def _get_sismic_py_codegen(
    quote: str, *, part_system_mode: bool = False
) -> SismicCodeGen:
    context = PythonCodeGenContext(string_delimiter=quote)
    return SismicCodeGen(context, part_system_mode=part_system_mode)


_SEND_VIA_MODEL = """
package Test {
    item def Ping;

    state def Machine {
        port commPort;

        entry;
            then idle;
        state idle;
        state running;

        transition first idle
            do send new Ping() via commPort
            then running;
    }
}
"""


class TestSismicCodeGen:
    def test_send_action_via_is_dropped_without_routing(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        # A send through a port delivers only over the port's connections;
        # without a part system there are none, so nothing is emitted.
        code_gen = _get_sismic_py_codegen(string_delimiter)
        model = _load_inline_model(tmp_path, _SEND_VIA_MODEL)

        send = _single_element(model, syside.SendActionUsage)
        emitted = code_gen.render_action(send)

        assert emitted == ""

    def test_send_action_via_routes_in_part_mode(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        code_gen = _get_sismic_py_codegen(
            string_delimiter, part_system_mode=True
        )
        model = _load_inline_model(tmp_path, _SEND_VIA_MODEL)

        send = _single_element(model, syside.SendActionUsage)
        emitted = code_gen.render_action(send)

        assert emitted == (
            f"_sysmlc_route({string_delimiter}Ping{string_delimiter}, "
            f"{string_delimiter}commPort{string_delimiter})"
        )
