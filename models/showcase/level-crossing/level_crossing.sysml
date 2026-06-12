package LevelCrossing {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::DurationValue;

    item def TrainApproaching;
    item def TrainPassed;
    item def Reset;
    item def BarrierFault {
        attribute severity : Integer;
    }

    // A railway level crossing: a timed securing sequence (warn lights,
    // bell, barrier), a closed state that holds until BOTH the bell
    // cycle has finished AND the train has passed (a parallel join with
    // one time-driven and one signal-driven region), a timed opening
    // sequence, and a latched fail-safe — a severe barrier fault while
    // lowering deep-exits the sequence; any fault while closed is a
    // group interrupt. Safety flavor: the crossing never reopens on a
    // fault path without an explicit operator reset.
    state def LevelCrossing {
        in attribute maxFaults : Integer default 3;
        attribute trainsPassed : Integer := 0;
        attribute faults : Integer := 0;

        assert constraint counters {
            trainsPassed >= 0 and faults >= 0 and faults <= maxFaults
        }

        entry;
            then open;

        state open;

        // Securing sequence: each step is timed; a severe fault while
        // the barrier is lowering escapes the WHOLE sequence into the
        // fail-safe latch (deep exit).
        state securing {
            entry;
                then warnLights;
            state warnLights;
            state bell;
            state barrierDown;
            transition first warnLights accept after 0.4 [s] then bell;
            transition first bell accept after 0.4 [s] then barrierDown;
            transition first barrierDown
                accept fault : BarrierFault
                if fault.severity >= 2
                then failSafe;
            transition first barrierDown accept after 0.7 [s] then done;
        }

        // Closed: the bell rings itself out while the passage watcher
        // waits for the train; the join reopens only when both regions
        // have completed.
        state closed parallel {
            state bellCycle {
                entry;
                    then ringing;
                state ringing;
                state quiet;
                transition first ringing accept after 1.0 [s] then quiet;
                transition first quiet accept after 0.5 [s] then done;
            }
            state passage {
                entry;
                    then waiting;
                state waiting;
                transition first waiting accept TrainPassed then done;
            }
        }

        state opening {
            entry;
                then barrierUp;
            state barrierUp;
            state lightsOff;
            transition first barrierUp accept after 0.7 [s] then lightsOff;
            transition first lightsOff accept after 0.4 [s] then done;
        }

        // The fault counter lives on the latch's entry so BOTH fault
        // paths (deep exit while securing, interrupt while closed) count
        // uniformly — substate scopes cannot touch attributes.
        state failSafe {
            entry assign faults := faults + 1;
        }

        transition first open accept TrainApproaching then securing;
        transition first securing then closed;

        // Join: bell cycle finished AND train passed.
        transition first closed then opening;
        transition first opening
            do assign trainsPassed := trainsPassed + 1
            then open;

        // Any barrier fault while closed latches the fail-safe: barriers
        // stay down until an operator reset.
        transition first closed accept BarrierFault then failSafe;

        transition first failSafe accept Reset then open;
    }
}
