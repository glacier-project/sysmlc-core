package PartExt {
    private import ScalarValues::*;
    private import SI::*;
    calc def bump { in v : Real; return : Real; }
    state def CounterBehavior {
        attribute x : Real := 0.0;
        entry; then ticking;
        state ticking;
        transition first ticking
            accept after 0.1 [s]
            do assign x := PartExt::bump(x)
            then ticking;
    }
    part def Counter { exhibit state : CounterBehavior; }
    part counterSystem { part c : Counter; }
}
