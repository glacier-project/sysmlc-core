from __future__ import annotations

import pytest
import syside

from sysml2frost.generator.sismic.sismic_py_codegen import SismicPyCodeGen
from sysml2frost.loader import load_syside_model
from sysml2frost.generator.python.py_codegen import PyCodeGen, PyCodeGenContext
from pathlib import Path
from .. import _load_inline_model, _single_element

def _get_sismic_py_codegen(quote: str) -> SismicPyCodeGen:
    context = PyCodeGenContext(string_delimiter=quote)
    return SismicPyCodeGen(context)

class TestSismicPyCodeGen:

    def test_send_action_typed_result_keeps_source(self, string_delimiter: str, tmp_path: Path) -> None:
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

        assert emitted == f'send({string_delimiter}Ping{string_delimiter})'
