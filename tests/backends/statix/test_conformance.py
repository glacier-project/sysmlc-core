from collections.abc import Callable

import pytest
from sismic.exceptions import InvariantError
from sismic.interpreter import Interpreter

from sysmlc.backends.quake.builder import build_statechart
from sysmlc.backends.statix.builder import build_statix

pytestmark = pytest.mark.statix

# Flat eventless machines whose settled state is deterministic on init.
CASES = [
    ("sm01", "SM01::Machine"),
    ("sm03", "SM03::MachineRef"),
    ("sm04", "SM04::MachineEntryIncrement"),
    ("sm06", "SM06::MachineEffect"),
]


@pytest.mark.parametrize("stem,qn", CASES)
def test_final_state_matches_sismic(
    sm_models: dict,
    statix_run: Callable,
    stem: str,
    qn: str,
) -> None:
    # Sismic reference (quake): settle on init, read the active leaf.
    interpreter = Interpreter(build_statechart(sm_models[stem], qn))
    interpreter.execute()
    sismic_leaf = sorted(interpreter.configuration)[-1]

    # statix C: build, compile, run the generated host runner.
    program = build_statix(sm_models[stem], qn)
    statix_leaf = statix_run(program)

    assert statix_leaf == sismic_leaf, (
        f"{stem}: statix {statix_leaf!r} != sismic {sismic_leaf!r}"
    )


SM08_CASES = [
    "SM08::MachineNested",
    "SM08::MachineDeep",
    "SM08::MachineNameCollision",
    "SM08::MachineCrossOut",
    "SM08::MachineCrossIn",
]


@pytest.mark.parametrize("qn", SM08_CASES)
def test_sm08_hierarchy_matches_sismic(
    sm_models: dict,
    statix_run: Callable,
    qn: str,
) -> None:
    interpreter = Interpreter(build_statechart(sm_models["sm08"], qn))
    interpreter.execute()
    sismic_leaf = sorted(interpreter.configuration)[-1]

    program = build_statix(sm_models["sm08"], qn)
    statix_leaf = statix_run(program)

    assert statix_leaf == sismic_leaf, (
        f"{qn}: statix {statix_leaf!r} != sismic {sismic_leaf!r}"
    )


SM10_CASES = [
    "SM10::MachineRootDone",
    "SM10::MachineNestedDone",
    "SM10::MachineTwoDone",
]


@pytest.mark.parametrize("qn", SM10_CASES)
def test_sm10_final_states_match_sismic(
    sm_models: dict,
    statix_run_final: Callable,
    qn: str,
) -> None:
    interpreter = Interpreter(build_statechart(sm_models["sm10"], qn))
    interpreter.execute()

    program = build_statix(sm_models["sm10"], qn)
    leaf, final = statix_run_final(program)

    assert final == interpreter.final, (
        f"{qn}: statix final={final} != sismic final={interpreter.final}"
    )
    if not interpreter.final:
        # Still-alive machine (nested done): compare the innermost active leaf.
        sismic_leaf = sorted(interpreter.configuration)[-1]
        assert leaf == sismic_leaf, (
            f"{qn}: statix {leaf!r} != sismic {sismic_leaf!r}"
        )


SM11_CASES = [
    ("SM11::MachineSelfSend", ()),
    ("SM11::MachinePayload", ()),
    ("SM11::MachineStringPayload", ()),
    ("SM11::MachineMixed", ()),
    ("SM11::MachineReadablePayloadGuard", ()),
    ("SM11::MachineReadablePayloadRejected", ()),
    ("SM11::MachineReadablePayloadEffect", ()),
    ("SM12::MachineDoSend", ()),
]


@pytest.mark.parametrize("qn,events", SM11_CASES)
def test_sm11_send_matches_sismic(
    sm_models: dict,
    statix_run: Callable,
    qn: str,
    events: tuple[str, ...],
) -> None:
    stem = qn.split("::")[0].lower()
    interpreter = Interpreter(build_statechart(sm_models[stem], qn))
    interpreter.execute()
    for e in events:
        interpreter.queue(e)
        interpreter.execute()
    sismic_leaf = sorted(interpreter.configuration)[-1]

    program = build_statix(sm_models[stem], qn)
    statix_leaf = statix_run(program, events)

    assert statix_leaf == sismic_leaf, (
        f"{qn}: statix {statix_leaf!r} != sismic {sismic_leaf!r}"
    )


# do-action machines that settle deterministically on init. Every supported
# variant reaches `finished`; MachineDoEnablesCompletion is the discriminating
# case -- it only reaches `finished` if the do body ran at entry (setting the
# `ready` flag the completion transition reads).
SM12_CASES = [
    "SM12::MachineDoAssign",
    "SM12::MachineDoMulti",
    "SM12::MachineDoShorthand",
    "SM12::MachineEntryThenDo",
    "SM12::MachineCompositeDo",
    "SM12::MachineDoEnablesCompletion",
    "SM12::MachineEmptyDo",
    "SM12::MachineRootEmptyDo",
    "SM12::MachineNamedEmptyDo",
]


@pytest.mark.parametrize("qn", SM12_CASES)
def test_sm12_do_matches_sismic(
    sm_models: dict,
    statix_run: Callable,
    qn: str,
) -> None:
    interpreter = Interpreter(build_statechart(sm_models["sm12"], qn))
    interpreter.execute()
    sismic_leaf = sorted(interpreter.configuration)[-1]

    program = build_statix(sm_models["sm12"], qn)
    statix_leaf = statix_run(program)

    assert statix_leaf == sismic_leaf, (
        f"{qn}: statix {statix_leaf!r} != sismic {sismic_leaf!r}"
    )


SM17_CASES = [
    ("SM17::MachineScoped", ()),
    ("SM17::MachineCounterLimit", ("Tick", "Tick")),
    ("SM17::MachineNegated", ("Tick",)),
    ("SM17::MachineFunctionViolation", ("Tick",)),
]


@pytest.mark.parametrize("qn,events", SM17_CASES)
def test_sm17_constraints_match_sismic(
    sm_models: dict,
    statix_run_status: Callable,
    qn: str,
    events: tuple[str, ...],
) -> None:
    # Derive the oracle verdict: does Sismic raise InvariantError on this run?
    interpreter = Interpreter(build_statechart(sm_models["sm17"], qn))
    violated = False
    try:
        interpreter.execute()
        for e in events:
            interpreter.queue(e)
            interpreter.execute()
    except InvariantError:
        violated = True

    status = statix_run_status(build_statix(sm_models["sm17"], qn), events)
    if violated:
        assert status == "SC_STATUS_CONSTRAINT_VIOLATED", (
            f"{qn}: statix {status!r}"
        )
    else:
        assert status != "SC_STATUS_CONSTRAINT_VIOLATED", (
            f"{qn}: statix {status!r}"
        )
