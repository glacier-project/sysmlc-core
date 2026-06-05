package SM13NoDefault {
    private import SI::*;
    private import ScalarValues::*;
    private import ISQ::DurationValue;

    state def MachineAfterNoDefault {
        attribute pickDuration : DurationValue;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after pickDuration then running;
    }
}
