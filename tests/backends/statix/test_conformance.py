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
    ("SM11::MachineReadablePayloadChain", ()),
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


def _drive_time_trigger(
    interpreter: Interpreter, events: tuple[str, ...]
) -> None:
    """Feed a tick/event sequence to Sismic, mirroring statix's _tick/_post.

    A "tick:N" entry sets Sismic's virtual clock (N ticks at the default
    SC_TICKS_PER_SECOND=1000, i.e. N/1000 seconds) instead of queuing a
    signal event.
    """
    for e in events:
        if e.startswith("tick:"):
            interpreter.clock.time = int(e[len("tick:") :]) / 1000.0
        else:
            interpreter.queue(e)
        interpreter.execute()


SM13_CASES = [
    ("SM13::MachineAfterSeconds", ("tick:5000",), "done"),
    ("SM13::MachineAfterMinutes", ("tick:120000",), "done"),
    ("SM13::MachineAfterAttribute", ("tick:120000",), "done"),
    ("SM13::MachineAfterChain", ("tick:3000",), "done"),
    ("SM13::MachineAfterGuard", ("tick:5000",), "done"),
    ("SM13::MachineAt", ("tick:8000",), "done"),
    (
        "SM13::MachineAfterReentry",
        (
            "tick:2000",
            "Leave",
            "tick:3000",
            "Back",
            "tick:10000",
            "tick:13000",
        ),
        "running",
    ),
    (
        "SM13::MachineAtReentry",
        ("tick:2000", "Leave", "tick:6000", "Back", "tick:50000"),
        "idle",
    ),
]


@pytest.mark.parametrize("qn,events,expected_leaf", SM13_CASES)
def test_sm13_time_trigger_matches_sismic(
    sm_models: dict,
    statix_run: Callable,
    qn: str,
    events: tuple[str, ...],
    expected_leaf: str,
) -> None:
    interpreter = Interpreter(build_statechart(sm_models["sm13"], qn))
    interpreter.execute()
    _drive_time_trigger(interpreter, events)
    sismic_leaf = (
        sorted(interpreter.configuration)[-1]
        if interpreter.configuration
        else ("done" if interpreter.final else "")
    )
    assert sismic_leaf == expected_leaf, (
        f"{qn}: sismic settled in {sismic_leaf!r}, expected {expected_leaf!r}"
    )

    program = build_statix(sm_models["sm13"], qn)
    statix_leaf = statix_run(program, events)
    assert statix_leaf == expected_leaf, (
        f"{qn}: statix {statix_leaf!r} != expected {expected_leaf!r}"
    )


SM18_CASES = [
    "SM18::MachineStringEnum",
    "SM18::MachineRealEnum",
    "SM18::MachinePlainEnum",
    "SM18::MachineEnumPayload",
]


@pytest.mark.parametrize("qn", SM18_CASES)
def test_sm18_enum_literals_match_sismic(
    sm_models: dict,
    statix_run: Callable,
    qn: str,
) -> None:
    interpreter = Interpreter(build_statechart(sm_models["sm18"], qn))
    interpreter.execute()
    sismic_leaf = sorted(interpreter.configuration)[-1]

    program = build_statix(sm_models["sm18"], qn)
    statix_leaf = statix_run(program)

    assert statix_leaf == sismic_leaf, (
        f"{qn}: statix {statix_leaf!r} != sismic {sismic_leaf!r}"
    )


def test_sm09_machine_parallel_matches_sismic_configuration(
    sm_models: dict, statix_run_configuration: Callable
) -> None:
    sc = build_statechart(sm_models["sm09"], "SM09::MachineParallel")
    interpreter = Interpreter(sc)
    interpreter.execute()
    oracle_leaves = frozenset(
        name
        for name in interpreter.configuration
        if not sc.children_for(name)  # leaf-only, matching statix's _active_state
    )
    program = build_statix(sm_models["sm09"], "SM09::MachineParallel")
    assert statix_run_configuration(program) == oracle_leaves


def test_sm09_machine_nested_parallel_matches_sismic_configuration(
    sm_models: dict, statix_run_configuration: Callable
) -> None:
    sc = build_statechart(sm_models["sm09"], "SM09::MachineNestedParallel")
    interpreter = Interpreter(sc)
    interpreter.execute()
    oracle_leaves = frozenset(
        name for name in interpreter.configuration if not sc.children_for(name)
    )
    program = build_statix(sm_models["sm09"], "SM09::MachineNestedParallel")
    assert statix_run_configuration(program) == oracle_leaves


def test_microwave_start_forks_both_regions(
    sm_models_showcase: dict, statix_run_configuration: Callable
) -> None:
    program = build_statix(
        sm_models_showcase["microwave"], "Microwave::MicrowaveBehavior"
    )
    config = statix_run_configuration(program, ("StartCmd",))
    assert config == frozenset({"cooking::heating::heater::warming",
                                 "cooking::heating::turntable::rotating"})


def test_microwave_pause_collapses_then_resume_restarts_both_regions(
    sm_models_showcase: dict, statix_run_configuration: Callable
) -> None:
    program = build_statix(
        sm_models_showcase["microwave"], "Microwave::MicrowaveBehavior"
    )
    # Group interrupt: PauseCmd collapses both regions to one trunk leaf.
    paused = statix_run_configuration(program, ("StartCmd", "PauseCmd"))
    assert paused == frozenset({"cooking::paused"})
    # Reset-on-reentry: ResumeCmd re-forks from each region's own initial
    # child, not wherever it left off.
    resumed = statix_run_configuration(
        program, ("StartCmd", "PauseCmd", "ResumeCmd")
    )
    assert resumed == frozenset({"cooking::heating::heater::warming",
                                  "cooking::heating::turntable::rotating"})


def test_microwave_door_open_interrupts_from_a_deep_active_region(
    sm_models_showcase: dict, statix_run: Callable
) -> None:
    program = build_statix(
        sm_models_showcase["microwave"], "Microwave::MicrowaveBehavior"
    )
    assert statix_run(program, ("StartCmd", "DoorOpen")) == "idle"


def test_microwave_independent_region_timers_and_join(
    sm_models_showcase: dict, statix_run_configuration: Callable, statix_run: Callable
) -> None:
    """Hand-derived expected trace (design Sec.1): quake/Sismic does not
    correctly gate `then done` on a parallel state's all-regions-final, so
    this is verified against reasoned-through UML/Sismic semantics (design
    Sec.4.1, Sec.6), not a live quake diff.
    """
    program = build_statix(
        sm_models_showcase["microwave"], "Microwave::MicrowaveBehavior"
    )
    # After 0.4s: only heater's timer has elapsed; turntable is still
    # rotating. Join must not fire early -- one region reaching final does
    # not satisfy regions_all_final.
    mid = statix_run_configuration(
        program, ("StartCmd", "tick:400")
    )
    assert mid == frozenset({"cooking::heating::heater::done",
                              "cooking::heating::turntable::rotating"})
    # After 0.6s: both regions final -> join fires -> collapses through
    # `cooking::done` to `idle`.
    assert statix_run(program, ("StartCmd", "tick:400", "tick:600")) == "idle"
