from sysmlc.backends.statix.program import (
    COMPLETION_EVENT,
    INTERNAL_TARGET,
    CContext,
    CField,
    CProgram,
    CState,
    CTransition,
)


def test_cprogram_holds_a_flat_machine() -> None:
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


def test_cprogram_supports_when_fields_and_internal_target() -> None:
    program = CProgram(
        name="Machine",
        qualified_name="SM16::Machine",
        prefix="sm16_machine",
        states=(CState("idle", entry_action_id=None, exit_action_id=None),),
        events=(),
        guards=(),
        actions=(),
        transitions=(
            CTransition("idle", COMPLETION_EVENT, None, None, INTERNAL_TARGET),
        ),
        context=CContext(fields=(), structs=()),
        queue_capacity=8,
        initial="idle",
        has_when=True,
        when_count=1,
    )
    assert program.has_when is True
    assert program.when_count == 1
    assert program.transitions[0].target == INTERNAL_TARGET
