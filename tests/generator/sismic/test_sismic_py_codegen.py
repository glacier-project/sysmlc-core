from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import syside

from sysmlc.generator.python.py_codegen import PyCodeGenContext
from sysmlc.generator.sismic.sismic_py_codegen import SismicPyCodeGen

from .. import _load_inline_model, _single_element


def _get_sismic_py_codegen(quote: str) -> SismicPyCodeGen:
    context = PyCodeGenContext(string_delimiter=quote)
    return SismicPyCodeGen(context)


class TestSismicPyCodeGen:
    def test_send_action_typed_result_keeps_source(
        self, string_delimiter: str, tmp_path: Path
    ) -> None:
        code_gen = _get_sismic_py_codegen(string_delimiter)
        model = _load_inline_model(
            tmp_path,
            """
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
            """,
        )

        send = _single_element(model, syside.SendActionUsage)
        emitted = code_gen.emit_action(send)

        assert emitted == f"send({string_delimiter}Ping{string_delimiter})"
