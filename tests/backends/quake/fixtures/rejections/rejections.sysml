package Rejections {
    private import SI::*;
    private import ScalarValues::*;

    item def Go;

    part def Controller { port inPort; }
    part controller : Controller;

    // A send addressed to another occurrence cannot be delivered by a
    // single statechart; only the machine's own port is a self-send.
    state def MachineSendToPeer {
        entry;
            then idle;
        state idle;
        transition first idle do send new Go() to controller then done;
    }

    // A chained receiver (another machine's port) is cross-machine
    // addressing too.
    state def MachineSendToPeerPort {
        entry;
            then idle;
        state idle;
        transition first idle do send new Go() to controller.inPort then done;
    }

    // An eventless self-loop never stabilizes (nothing breaks the loop).
    state def MachineSelfLoop {
        entry;
            then idle;
        state idle;
        transition first idle then idle;
    }

    // A negative `after` duration is rejected.
    state def MachineNegDuration {
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after -5 [s] then running;
    }

    // A state definition without an initial substate cannot be emitted as a
    // sismic compound state.
    state def MachineNoInitial {
        state idle;
        state running;

        transition first idle then running;
    }

    // Initial targets must be direct substates. Deep targets would require
    // decomposing initial choices across multiple sismic compound states.
    state def MachineDeepInitialQualifiedName {
        entry; then container::idle;

        state container {
            state idle;
            state running;
        }
    }

    state def MachineDeepInitialFeatureChain {
        entry; then container.idle;

        state container {
            state idle;
            state running;
        }
    }

    state def MachineDeepInitialConflict {
        entry; then running.hot;

        state running {
            entry; then warming;

            state warming;
            state hot;
        }
    }
}
