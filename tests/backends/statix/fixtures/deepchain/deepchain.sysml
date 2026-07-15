package DEEPCHAIN {
    private import ScalarValues::*;

    attribute def Inner {
        attribute leaf : Real = 0.5;
    }
    attribute def Middle {
        attribute inner : Inner;
    }
    item def Deep {
        attribute middle : Middle;
    }

    attribute def Box {
        attribute count : Integer = 1;
    }
    item def DeepInt {
        attribute box : Box;
    }

    // Three-segment payload chain: rejected as deeper than one composite hop.
    state def MachineDeepChain {
        attribute middle : Middle;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle do send new Deep(middle) to commPort then armed;
        transition first armed
            accept reading : Deep via commPort
            if reading.middle.inner.leaf > 0.5
            then fired;
    }

    // The resolved leaf field is Integer, not Real: rejected.
    state def MachineChainOnIntegerLeaf {
        attribute box : Box;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle do send new DeepInt(box) to commPort then armed;
        transition first armed
            accept reading : DeepInt via commPort
            if reading.box.count > 0
            then fired;
    }

    // No `send` constructor argument is bound to the read chain's first
    // segment (a send with no constructor arguments): rejected.
    state def MachineChainNoMatchingArg {
        attribute box : Box;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle do send new DeepInt() to commPort then armed;
        transition first armed
            accept reading : DeepInt via commPort
            if reading.box.count > 0
            then fired;
    }

    // The matched send argument is an inline constructor, not a bare
    // reference to a composite machine attribute: rejected.
    state def MachineChainOnInlineArg {
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Deep(new Middle()) to commPort
            then armed;
        transition first armed
            accept reading : Deep via commPort
            if reading.middle.inner > 0.5
            then fired;
    }
}
