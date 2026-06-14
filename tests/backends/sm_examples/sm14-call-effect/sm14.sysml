package SM14 {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::DurationValue;

    // `sysmlc::log` comes from the auto-loaded library shipped in Task 1.
    package Plant {
        calc def step { in x : Real; in dt : Real; return : Real; }
    }

    state def MachineCallEffect {
        attribute theta : Real := 0.0;

        action logAct : sysmlc::log { in :>> tag = "plant"; in :>> value = theta; }

        entry; then idle;
        state idle;
        state ticking;
        transition first idle
            accept after 0.1 [s]
            do logAct
            then ticking;
        transition first ticking
            accept after 0.1 [s]
            do assign theta := Plant::step(theta, 0.1)
            then idle;
    }
}
