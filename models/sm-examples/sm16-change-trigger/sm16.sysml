package SM16 {
    private import ScalarValues::*;

    // A bare change trigger: fires at the rise, or at entry if already true.
    state def MachineWhenBare {
        attribute hot : Boolean := false;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept when hot then running;
        transition first running then done;
    }

    // A guarded change trigger: the guard is tested once, at delivery;
    // a false guard consumes the occurrence. Kick re-enters `idle`.
    item def Kick;

    state def MachineWhenGuard {
        attribute hot : Boolean := false;
        attribute enabled : Boolean := true;
        entry;
            then idle;
        state idle;
        state away;
        state running;
        transition first idle accept when hot if enabled then running;
        transition first idle accept Kick then away;
        transition first away accept Kick then idle;
        transition first running then done;
    }

    // Re-entry arms a fresh observation: a still-true condition fires again.
    item def Reset;

    state def MachineWhenReentry {
        attribute hot : Boolean := false;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept when hot then running;
        transition first running accept Reset then idle;
    }

    // Two change triggers on one source resolve in declaration order.
    state def MachineWhenTwo {
        attribute hot : Boolean := false;
        attribute cold : Boolean := false;
        entry;
            then idle;
        state idle;
        state warmed;
        state chilled;
        transition first idle accept when hot then warmed;
        transition first idle accept when cold then chilled;
    }

    // A composed condition: the whole expression is what is observed.
    state def MachineWhenComposed {
        attribute hot : Boolean := false;
        attribute enabled : Boolean := false;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept when hot and enabled then running;
        transition first running then done;
    }
}
