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
}
