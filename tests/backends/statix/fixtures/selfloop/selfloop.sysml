package SELFLOOP {
    private import ScalarValues::*;

    item def E;

    // Flat machine used to pin EXTERNAL self-transition semantics.
    // `a` bumps `n` on entry. Posting E takes the self-loop a -> a; under
    // external semantics `a` is re-entered so `n` becomes 2 and the eventless
    // guarded transition a -> b then fires. Under (wrong) internal semantics
    // `a` is not re-entered, `n` stays 1, and the machine stays in `a`.
    state def MachineSelfLoop {
        port commPort;
        attribute n : Integer := 0;
        entry;
            then a;
        state a {
            entry action bump {
                assign n := n + 1;
            }
        }
        state b;
        transition first a accept E via commPort then a;
        transition first a if n >= 2 then b;
    }
}
