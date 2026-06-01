package SM10 {
    private import ScalarValues::*;

    // Root-level done.
    state def MachineRootDone {
        entry;
            then idle;
        state idle;
        state running;
        transition first idle then running;
        transition first running then done;
    }

    // Nested done: the machine stays alive.
    state def MachineNestedDone {
        entry;
            then running;
        state running {
            entry;
                then warming;
            state warming;
            state hot;
            transition first warming then hot;
            transition first hot then done;
        }
        state stopped;
        transition first running then stopped;
    }

    // Parallel: each region reaches its own done.
    state def MachineParallelDone parallel {
        state lights {
            entry;
                then off;
            state off;
            state on;
            transition first off then on;
            transition first on then done;
        }
        state sound {
            entry;
                then silent;
            state silent;
            state beeping;
            transition first silent then beeping;
            transition first beeping then done;
        }
    }

    // Two `then done` in one scope share a single final state.
    state def MachineTwoDone {
        attribute shortcut : Boolean := true;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if shortcut then done;
        transition first idle if not shortcut then running;
        transition first running then done;
    }
}
