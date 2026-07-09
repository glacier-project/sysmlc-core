package TIMERREJECT {
    private import SI::*;
    private import ScalarValues::*;

    // after sourced from a composite (non-leaf) state: rejected, since
    // state_entered_at needs one unambiguous leaf.
    state def MachineTimerOnComposite {
        entry;
            then idle;
        state idle;
        state running {
            entry;
                then warming;
            state warming;
        }
        transition first idle then running;
        transition first running accept after 5 [s] then idle;
    }

    // Two competing time triggers sourced from the same leaf: rejected.
    // (Both `after`: a bare `at <literal>` is not valid SysML here -- `at`
    // requires a TimeInstantValue, never a bare DurationValue-shaped
    // literal like `8 [s]`; confirmed empirically against syside, which
    // reports "An at expression must be a TimeInstantValue" for that shape.
    // sm13's own MachineAt/MachineAtReentry always reference a
    // TimeInstantValue *attribute* instead, e.g. `accept at deadline`.)
    state def MachineTimerTwice {
        entry;
            then idle;
        state idle;
        state fast;
        state slow;
        transition first idle accept after 5 [s] then fast;
        transition first idle accept after 8 [s] then slow;
    }

    // A literal duration far beyond the representable tick range
    // (~4.29e6 seconds at the default SC_TICKS_PER_SECOND=1000): rejected
    // at build time, not deferred to an unsafe runtime cast.
    state def MachineTimerOutOfRange {
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after 999999999999 [s] then running;
    }
}
