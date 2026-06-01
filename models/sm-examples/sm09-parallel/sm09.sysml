package SM09 {
    private import ScalarValues::*;

    // A parallel ROOT: the whole machine is orthogonal.
    state def MachineParallel parallel {
        state lights {
            entry;
                then off;
            state off;
            state on;
            transition first off then on;
        }
        state sound {
            entry;
                then silent;
            state silent;
            state beeping;
            transition first silent then beeping;
        }
    }

    // A NESTED parallel substate inside an ordinary def.
    state def MachineNestedParallel {
        attribute count : Integer;
        entry;
            then idle;
        state idle;
        state dual parallel {
            entry assign count := 1;
            exit  assign count := 2;
            state lights {
                entry;
                    then off;
                state off;
                state on;
                transition first off then on;
            }
            state sound {
                entry;
                    then silent;
                state silent;
                state beeping;
                transition first silent then beeping;
            }
        }
        transition first idle then dual;
    }
}
