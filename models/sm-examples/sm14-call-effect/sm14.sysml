package SM14 {
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import SI::*;
    private import ISQ::DurationValue;

    // `sysmlc::log` comes from the auto-loaded library shipped in Task 1.
    package Plant {
        calc def step { in x : Real; in dt : Real; return : Real; }
    }

    state def MachineAssignCall {
        attribute x : Real := 0.0;
        entry; then a;
        state a;
        state b;
        transition first a
            accept after 0.1 [s]
            do assign x := NumericalFunctions::max(x, 0.0)
            then b;
    }

    state def MachineCallEffect {
        attribute theta : Real := 0.0;
        entry; then ticking;
        state ticking;
        transition first ticking
            accept after 0.1 [s]
            do assign theta := Plant::step(theta, 0.1)
            then ticking;
    }
}
