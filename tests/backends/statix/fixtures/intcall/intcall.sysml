package INTCALL {
    private import ScalarValues::*;
    private import NumericalFunctions::*;

    // A library call whose result (double) is assigned to an Integer attribute.
    // statix must reject this rather than emit a double->int32 narrowing.
    state def Machine {
        attribute n : Integer := 0;
        entry; then a;
        state a;
        state b;
        transition first a do assign n := NumericalFunctions::max(n, 0) then b;
    }
}
