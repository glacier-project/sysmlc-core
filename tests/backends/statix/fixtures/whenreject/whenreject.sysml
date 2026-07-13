package WHENREJECT {
    private import ScalarValues::*;

    // A `when` trigger whose target is its own source: rejected as a
    // self-loop (a conservative guardrail against non-quiescing settles).
    state def MachineWhenSelfLoop {
        attribute hot : Boolean := false;
        entry;
            then idle;
        state idle;
        transition first idle accept when hot then idle;
    }

    // `when` sourced from a composite (non-leaf) state: rejected, mirroring
    // the after/at leaf-only rule, even though nothing in the mechanism
    // itself forces it (see docs/statix-mapping.md).
    state def MachineWhenOnComposite {
        attribute hot : Boolean := false;
        entry;
            then idle;
        state idle;
        state running {
            entry;
                then warming;
            state warming;
        }
        transition first idle then running;
        transition first running accept when hot then idle;
    }
}
