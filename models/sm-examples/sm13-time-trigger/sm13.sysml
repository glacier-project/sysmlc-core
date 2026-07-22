package SM13 {
    private import SI::*;
    private import ScalarValues::*;
    private import ISQ::DurationValue;
    private import Time::TimeInstantValue;

    // Time trigger with a literal duration in seconds.
    state def MachineAfterSeconds {
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after 5 [s] then running;
        transition first running then done;
    }

    // A literal duration in minutes.
    state def MachineAfterMinutes {
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after 2 [min] then running;
        transition first running then done;
    }

    // `pickDuration` attribute-reference duration.
    state def MachineAfterAttribute {
        attribute pickDuration : DurationValue default 2 [min];
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after pickDuration then running;
        transition first running then done;
    }

    // A chained `holder.delay` duration.
    attribute def DurationHolder {
        attribute delay : DurationValue default 3 [s];
    }

    state def MachineAfterChain {
        attribute holder : DurationHolder;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after holder.delay then running;
        transition first running then done;
    }

    // `accept after` combined with an `if` guard: the guard is tested once,
    // when the deadline occurrence is delivered; a false guard consumes it.
    state def MachineAfterGuard {
        attribute ready : Boolean := true;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after 5 [s] if ready then running;
        transition first running then done;
    }

    // Absolute time trigger via a TimeInstantValue attribute.
    state def MachineAt {
        attribute deadlineTime : TimeInstantValue default 8 [s];
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept at deadlineTime then running;
        transition first running then done;
    }

    // A timed self-loop: each re-entry re-arms a fresh deadline.
    state def MachineAfterSelfLoop {
        attribute entries : Integer := 0;
        entry;
            then idle;
        state idle {
            entry assign entries := entries + 1;
        }
        transition first idle accept after 5 [s] then idle;
    }

    // Leaving the source before the deadline invalidates the pending
    // occurrence: after a re-entry, only the freshly armed deadline fires.
    item def Leave;
    item def Back;

    state def MachineAfterReentry {
        entry;
            then idle;
        state idle;
        state away;
        state running;
        transition first idle accept after 10 [s] then running;
        transition first idle accept Leave then away;
        transition first away accept Back then idle;
    }

    // Re-entering after the absolute instant has passed does not fire.
    state def MachineAtReentry {
        attribute deadlineTime : TimeInstantValue default 5 [s];
        entry;
            then idle;
        state idle;
        state away;
        state running;
        transition first idle accept at deadlineTime then running;
        transition first idle accept Leave then away;
        transition first away accept Back then idle;
    }
}
