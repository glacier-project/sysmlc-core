package FieldOverrideProbe {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::DurationValue;
    enum def Color { enum cold; enum warm; }
    attribute def Inner { attribute count : Integer default 1; }
    attribute def Box {
        attribute count : Integer default 1;
        attribute inner : Inner;
        attribute delay : DurationValue default 1 [min];
        attribute color : Color default Color::cold;
    }
    state def Machine {
        attribute direct : Box { :>> count default 2; }
        attribute nested : Box { :>> inner { :>> count default 3; } }
        attribute explicit : Box { attribute :>> count default 4; }
        attribute kinds : Box {
            :>> delay default 2 [min];
            :>> color default Color::warm;
        }
        attribute unchanged : Box;
        attribute inherited : Box {
            :>> count { doc /* Retain the type default. */ }
        }
        entry; then enclosing;
        state enclosing {
            attribute local : Box { :>> inner { :>> count default 3; } }
            entry; then child;
            state child;
        }
    }
    state def Renamed {
        attribute box : Box { ref tally :>> count default 5; }
    }
    state def FixedDirect {
        attribute box : Box { :>> count = 2; }
        attribute spare : Box;
        entry; then active;
        state active { entry assign box := spare; }
    }
    state def FixedNested {
        attribute box : Box { :>> inner { :>> count = 2; } }
        attribute spare : Box;
        entry; then active;
        state active { entry assign box := spare; }
    }
    attribute def FixedBox { attribute count : Integer = 1; }
    state def InheritedFixed {
        attribute box : FixedBox { :>> count; }
    }
    item def Packet;
    state def Controls {
        ref unrelated : Inner;
        item payload : Packet;
    }
}
