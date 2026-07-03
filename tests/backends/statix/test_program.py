from sysmlc.backends.statix.program import (
    COMPLETION_EVENT,
    CContext,
    CField,
    CProgram,
    CState,
    CTransition,
)


def test_cprogram_holds_a_flat_machine():
    program = CProgram(
        name="Machine",
        qualified_name="SM01::Machine",
        prefix="sm01_machine",
        states=(
            CState("idle", entry_action_id=None, exit_action_id=None),
            CState("running", entry_action_id=None, exit_action_id=None),
        ),
        events=(),
        guards=(),
        actions=(),
        transitions=(
            CTransition("idle", COMPLETION_EVENT, None, None, "running"),
        ),
        context=CContext(
            fields=(CField("counter", "int32_t", "0"),), structs=()
        ),
        queue_capacity=8,
        initial="idle",
    )
    assert program.transitions[0].event is COMPLETION_EVENT
    assert program.context.fields[0].c_type == "int32_t"
    assert [s.name for s in program.states] == ["idle", "running"]
