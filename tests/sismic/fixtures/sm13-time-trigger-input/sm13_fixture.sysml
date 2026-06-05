// Test fixture for sm13 (not a corpus example): an `in` duration with no
// default, provided at runtime via the interpreter's initial context.
package SM13Input {
    private import SI::*;
    private import ScalarValues::*;
    private import ISQ::DurationValue;

    state def MachineAfterInput {
        in attribute pickDuration : DurationValue;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after pickDuration then running;
    }
}
