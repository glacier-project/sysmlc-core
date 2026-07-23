package SM11 {
    private import ScalarValues::*;

    item def Ping;
    item def Reading {
        attribute value : Integer;
    }
    attribute def Sample {
        attribute value : Real = 0.75;
    }
    item def Measurement {
        attribute value : Real;
        attribute sample : Sample;
    }
    item def Note {
        attribute text : String;
    }
    item def Labeled {
        attribute value : Integer;
        attribute label : String;
    }
    item def Flagged {
        attribute armed : Boolean;
    }
    item def Mixed {
        attribute armed : Boolean;
        attribute value : Real;
        attribute ready : Boolean;
    }

    // A send effect raises an event the same machine then accepts.
    state def MachineSelfSend {
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle do send new Ping() to commPort then armed;
        transition first armed accept Ping via commPort then fired;
    }

    // A send whose payload carries a scalar argument.
    state def MachinePayload {
        attribute current : Integer := 7;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle do send new Reading(current) to commPort then armed;
        transition first armed accept Reading via commPort then fired;
    }

    // A send whose payload carries a string argument.
    state def MachineStringPayload {
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle do send new Note("hi") to commPort then armed;
        transition first armed accept Note via commPort then fired;
    }

    // A named accept payload can be read from the transition guard.
    state def MachineReadablePayloadGuard {
        attribute current : Real := 0.9;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Measurement(current) to commPort
            then armed;
        transition first armed
            accept reading : Measurement via commPort
            if reading.value > 0.5
            then fired;
    }

    // A rejected payload guard consumes the event and leaves the source active.
    state def MachineReadablePayloadRejected {
        attribute current : Real := 0.4;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Measurement(current) to commPort
            then armed;
        transition first armed
            accept reading : Measurement via commPort
            if reading.value > 0.5
            then fired;
    }

    // A named accept payload can be read from the transition effect.
    state def MachineReadablePayloadEffect {
        attribute current : Real := 0.9;
        attribute captured : Real := 0.0;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Measurement(current) to commPort
            then armed;
        transition first armed
            accept reading : Measurement via commPort
            do assign captured := reading.value
            then fired;
    }

    // Payload references can be chained beyond a single field.
    state def MachineReadablePayloadChain {
        attribute current : Real := 0.9;
        attribute sample : Sample;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Measurement(current, sample) to commPort
            then armed;
        transition first armed
            accept reading : Measurement via commPort
            if reading.sample.value > 0.5
            then fired;
    }

    // The whole payload occurrence can be referenced on its own, not only
    // through a field.
    state def MachineReadablePayloadWhole {
        attribute current : Real := 0.9;
        item captured : Measurement;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Measurement(current) to commPort
            then armed;
        transition first armed
            accept reading : Measurement via commPort
            do assign captured := reading
            then fired;
    }

    // A named accept payload that is never referenced anywhere in the
    // guard or effect -- must build cleanly, treated as unread.
    state def MachineReadablePayloadUnused {
        attribute current : Real := 0.9;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Measurement(current) to commPort
            then armed;
        transition first armed
            accept reading : Measurement via commPort
            then fired;
    }

    // Two different transitions read the SAME event via two DIFFERENT
    // subfeature paths, AND a third reads it wholly -- all now legal:
    // statix's wire format is the event's own declared type regardless of
    // which subset of fields (or the whole value) any given transition
    // reads.
    state def MachineReadablePayloadMixed {
        attribute current : Real := 0.9;
        attribute captured : Real := 0.0;
        item wholeCaptured : Measurement;
        port commPort;
        entry;
            then a;
        state a;
        state b;
        state c;
        state d;
        transition first a do send new Measurement(current) to commPort then b;
        transition first b
            accept reading : Measurement via commPort
            do assign captured := reading.value
            then c;
        transition first c
            accept reading : Measurement via commPort
            if reading.sample.value > 0.5
            then d;
        transition first d
            accept reading : Measurement via commPort
            do assign wholeCaptured := reading
            then a;
    }


    // A mixed effect body: an assignment and a send, in declaration order.
    state def MachineMixed {
        attribute count : Integer := 0;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        transition first idle do action {
            assign count := count + 1;
            send new Ping() to commPort;
        } then armed;
    }

    // A composite payload with an unrepresentable sibling field: reading
    // ONLY the representable field must still be rejected, naming the
    // OTHER (never-read) field -- every leaf crosses the wire together.
    state def MachineReadablePayloadUnrepresentableSibling {
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle do send new Labeled(1) to commPort then armed;
        transition first armed
            accept reading : Labeled via commPort
            if reading.value > 0
            then fired;
    }

    // A named accept payload of an Integer leaf, read in a guard.
    state def MachineReadableIntegerPayload {
        attribute count : Integer := 3;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Reading(count) to commPort
            then armed;
        transition first armed
            accept reading : Reading via commPort
            if reading.value > 0
            then fired;
    }

    // A named accept payload of a Boolean leaf, read bare (no comparison
    // operator needed) in a guard -- mirrors SM03::MachineRef's bare
    // `ctx->enabled` guard shape, now off a decoded payload local instead
    // of a context attribute.
    state def MachineReadableBooleanPayload {
        attribute ready : Boolean := true;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Flagged(ready) to commPort
            then armed;
        transition first armed
            accept reading : Flagged via commPort
            if reading.armed
            then fired;
    }

    // Boolean, Real, Boolean in that DECLARATION ORDER specifically --
    // proves sizeof(struct), not a naive sum of leaf sizes, is the real
    // wire length: { bool, double, bool } needs 24 bytes on a common
    // target (1 + 7 padding + 8 + 1 + 7 trailing padding), which a
    // sum-then-round heuristic (1+8+1=10 -> 16) would under-count, but
    // 8 x leaf_count (8 x 3 = 24) correctly covers.
    state def MachineMixedPrimitivePadding {
        attribute a : Boolean := true;
        attribute v : Real := 1.5;
        attribute r : Boolean := false;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Mixed(a, v, r) to commPort
            then armed;
        transition first armed
            accept reading : Mixed via commPort
            if reading.value > 1.0
            then fired;
    }
}
