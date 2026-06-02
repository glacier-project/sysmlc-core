package SM11 {
    private import ScalarValues::*;

    item def Ping;
    item def Reading {
        attribute value : Integer;
    }

    // A send effect raises an event the same machine then accepts.
    state def MachineSelfSend {
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle do send new Ping() via commPort then armed;
        transition first armed accept Ping via commPort then fired;
    }

    // A send whose payload carries a scalar argument.
    state def MachinePayload {
        attribute current : Integer := 7;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle do send new Reading(current) via commPort then armed;
        transition first armed accept Reading via commPort then fired;
    }

    // A mixed effect body: an assignment and a send, in declaration order.
    state def MachineMixed {
        attribute count : Integer := 0;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        transition first idle do action {
            assign count := count + 1;
            send new Ping() via commPort;
        } then armed;
    }
}
