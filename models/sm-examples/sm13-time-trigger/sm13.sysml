package SM13 {
    private import SI::*;
    private import ScalarValues::*;
    private import ISQ::DurationValue;

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

    // `accept after` combined with an `if` guard is now rejected (fail-loud).
    // state def MachineAfterGuard {
    //     attribute ready : Boolean := true;
    //     entry;
    //         then idle;
    //     state idle;
    //     state running;
    //     transition first idle accept after 5 [s] if ready then running;
    //     transition first running then done;
    // }
}
