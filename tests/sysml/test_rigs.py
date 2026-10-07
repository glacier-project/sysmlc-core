from pathlib import Path

import pytest
import syside

from sysmlc.sysml.queries import exhibited_state_defs, resolve, rig_definitions
from tests import _load_inline_model


@pytest.fixture
def rig_model(tmp_path: Path) -> syside.Model:
    return _load_inline_model(
        tmp_path,
        """
        package Rigs {
            private import ScalarValues::*;
            state def Plant { entry; then idle; state idle; }
            state def Tester { entry; then idle; state idle; }
            part def Pair {
                exhibit state plant : Plant;
                exhibit state tb : Tester;
            }
            part def Three {
                exhibit state a : Plant;
                exhibit state b : Tester;
                exhibit state c : Plant;
            }
            part def Extra {
                attribute stray : Integer := 0;
                exhibit state a : Plant;
                exhibit state b : Tester;
            }
        }
    """,
    )


def test_rig_definitions_find_named_exhibits(rig_model: syside.Model) -> None:
    rigs = rig_definitions(rig_model)
    assert [str(r.qualified_name) for r in rigs] == ["Rigs::Pair"]


def test_exhibited_state_defs_preserve_names_and_types(
    rig_model: syside.Model,
) -> None:
    rig = resolve(rig_model, syside.PartDefinition, "Rigs::Pair")
    pairs = exhibited_state_defs(rig_model, rig)
    assert [(name, str(state.qualified_name)) for name, state in pairs] == [
        ("plant", "Rigs::Plant"),
        ("tb", "Rigs::Tester"),
    ]


@pytest.mark.parametrize(
    ("qn", "fragment"),
    [
        ("Rigs::Three", "exactly two"),
        ("Rigs::Extra", "exhibit state"),
    ],
)
def test_malformed_rigs_are_rejected(
    rig_model: syside.Model, qn: str, fragment: str
) -> None:
    rig = resolve(rig_model, syside.PartDefinition, qn)
    with pytest.raises(ValueError, match=fragment):
        exhibited_state_defs(rig_model, rig)
