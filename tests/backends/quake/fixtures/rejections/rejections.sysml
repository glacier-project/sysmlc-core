package Rejections {
    private import SI::*;
    private import ScalarValues::*;

    // `accept after` combined with an `if` guard is rejected: sismic's
    // `after` is monotonic, so the combination would be unsound.
    state def MachineAfterGuard {
        attribute ready : Boolean := true;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after 5 [s] if ready then running;
        transition first running then done;
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
