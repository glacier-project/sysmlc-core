package WHENENTRYDO {
    private import ScalarValues::*;

    // A `do` that mutates the very attribute its own `when` condition
    // watches: pins the arm-last convention -- the guard must see the
    // do-mutated value the first time it is checked, during `_init`'s own
    // completion settle.
    state def MachineWhenEntryDoMutates {
        attribute hot : Boolean := false;
        entry;
            then idle;
        state idle {
            do assign hot := true;
        }
        state running;
        transition first idle accept when hot then running;
    }
}
