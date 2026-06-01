package SM08 {
    private import ScalarValues::*;

    state def MachineNested {
        entry;
            then idle;
        state idle;
        state running {
            entry;
                then warming;
            state warming;
            state hot;
            transition first warming then hot;
        }
        transition first idle then running;
    }

    state def MachineDeep {
        entry;
            then idle;
        state idle;
        state running {
            entry;
                then warming;
            state warming {
                entry;
                    then low;
                state low;
                state high;
                transition first low then high;
            }
            state cool;
            transition first warming then cool;
        }
        transition first idle then running;
    }

    // Two composites reuse the names `active` and `paused`.
    state def MachineNameCollision {
        entry;
            then groupA;
        state groupA {
            entry;
                then active;
            state active;
            state paused;
            transition first active then paused;
        }
        state groupB {
            entry;
                then active;
            state active;
            state paused;
            transition first active then paused;
        }
        transition first groupA then groupB;
    }
}
