package NestedAttributePreamble {
    private import SI::*;
    private import ScalarValues::*;
    private import ISQ::DurationValue;

    // A nested composite owns the attribute that its own transition
    // reads as a relative time trigger.
    state def MachineNestedAttrSelfScope {
        entry;
            then outer;
        state outer {
            attribute innerDur : DurationValue default 3 [s];
            entry;
                then alpha;
            state alpha;
            state beta;
            transition first alpha accept after innerDur then beta;
        }
    }

    // A nested composite owns the attribute, but the transition that
    // reads it lives in a deeper substate.
    state def MachineNestedAttrDeepScope {
        entry;
            then outer;
        state outer {
            attribute innerDur : DurationValue default 4 [s];
            entry;
                then mid;
            state mid {
                entry;
                    then alpha;
                state alpha;
                state beta;
                transition first alpha accept after innerDur then beta;
            }
        }
    }

    // Root and a nested scope both declare attributes, with distinct
    // names.
    state def MachineRootAndNestedDistinctNames {
        attribute speed : Real := 1.5;
        entry;
            then outer;
        state outer {
            attribute innerDur : DurationValue default 2 [s];
            entry;
                then alpha;
            state alpha;
            state beta;
            transition first alpha accept after innerDur then beta;
        }
    }

    // Root and a nested scope declare attributes with the same name. Build raises.
    state def MachineCollisionRootNested {
        attribute x : Real := 1.0;
        entry;
            then outer;
        state outer {
            attribute x : Real := 2.0;
            entry;
                then alpha;
            state alpha;
            state beta;
            transition first alpha then beta;
        }
    }

    // Two sibling composites declare an attribute with the same
    // name. Build raises.
    state def MachineCollisionSiblings {
        entry;
            then groupA;
        state groupA {
            attribute count : Real := 0.0;
            entry;
                then alphaA;
            state alphaA;
            state betaA;
            transition first alphaA then betaA;
        }
        state groupB {
            attribute count : Real := 0.0;
            entry;
                then alphaB;
            state alphaB;
            state betaB;
            transition first alphaB then betaB;
        }
        transition first groupA then groupB;
    }
}
