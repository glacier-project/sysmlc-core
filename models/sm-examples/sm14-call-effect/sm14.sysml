package SM14 {
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import SI::*;
    private import ISQ::DurationValue;

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
}
