from pathlib import Path

import pytest
import syside

from sysmlc.semantics.statemachine.facts import SignalTrigger
from sysmlc.semantics.statemachine.triggers import classify
from sysmlc.sysml.queries import iter_elements, resolve
from tests import _load_inline_model


@pytest.mark.parametrize("named", [False, True])
@pytest.mark.parametrize(
    "fields", ["", "attribute value : ScalarValues::Integer;"]
)
def test_signal_retains_accepted_type(
    tmp_path: Path, named: bool, fields: str
) -> None:
    accept = "reading : Event" if named else "Event"
    model = _load_inline_model(
        tmp_path,
        f"""package Signals {{
            item def Event {{ {fields} }}
            state def Controller {{
                state idle;
                entry; then idle;
                transition first idle accept {accept} then idle;
            }}
        }}""",
    )
    (trans,) = iter_elements(model, syside.TransitionUsage)
    trigger = classify(trans, syside.Compiler(), syside.Stdlib(model.index))
    assert isinstance(trigger, SignalTrigger)
    assert trigger.accepted_type is resolve(
        model, syside.ItemDefinition, "Signals::Event"
    )
    assert trigger.signal_name == "Event"
    assert trigger.payload_name == ("reading" if named else None)


def test_signal_constructor_remains_source_compatible() -> None:
    trigger = SignalTrigger("Tick", "reading", None, "port")
    assert trigger.accepted_type is None
    assert trigger.via_port == "port"
