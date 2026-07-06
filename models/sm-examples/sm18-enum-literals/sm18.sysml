package SM18 {
    private import ScalarValues::*;

    // A plain symbolic enumeration: literals carry no declared value.
    enum def Mode {
        enum idle;
        enum busy;
    }

    // A String-valued enumeration: each literal declares its own value.
    enum def LightColor :> String {
        enum red = "red";
        enum green = "green";
        enum yellow = "yellow";
    }

    // A Real-valued enumeration using the bare literal spelling (no `enum`
    // keyword), like the official GradePoints example.
    enum def GradePoints :> Real {
        A = 4.0;
        B = 3.0;
        C = 2.0;
    }

    // Payload carrying an enum-typed field, sent as a self-event.
    item def Announce {
        attribute color : LightColor;
    }

    // A String-valued literal initializes an attribute, an effect assigns
    // another literal, and a guard compares against a third.
    state def MachineStringEnum {
        attribute c : LightColor := LightColor::red;
        entry;
            then idle;
        state idle;
        state green;
        state matched;
        transition first idle do assign c := LightColor::green then green;
        transition first green if c == LightColor::green then matched;
    }

    // A Real-valued enum literal initializes the attribute and gates a
    // numeric guard.
    state def MachineRealEnum {
        attribute g : GradePoints := GradePoints::A;
        entry;
            then grading;
        state grading;
        state passed;
        transition first grading if g >= GradePoints::B then passed;
    }

    // A plain symbolic enum literal initializes the attribute, an effect
    // assigns another, and a guard compares against it.
    state def MachinePlainEnum {
        attribute m : Mode := Mode::idle;
        entry;
            then ready;
        state ready;
        state working;
        state checked;
        transition first ready do assign m := Mode::busy then working;
        transition first working if m == Mode::busy then checked;
    }

    // A send whose payload argument is an enum literal, accepted by the same
    // machine as a self-event.
    state def MachineEnumPayload {
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state fired;
        transition first idle
            do send new Announce(LightColor::yellow) to commPort
            then armed;
        transition first armed accept Announce via commPort then fired;
    }
}
