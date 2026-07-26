package ScopedConstraint {
    private import ScalarValues::*;

    // The asserted constraint lives inside a state, so the pushed fact
    // must carry the state's scope path.
    state def Machine {
        attribute level : Real := 1.0;
        entry;
            then idle;
        state idle {
            assert constraint levelPositive { level > 0.0 }
        }
    }
}
