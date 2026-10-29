package InlineControls {
    private import ScalarValues::*;
    item def Ping;
    state def Machine {
        attribute count : Integer := 0;
        port p;
        entry; then named;
        state named {
            entry action onEntry { assign count := 1; }
            exit action onExit { send new Ping() to p; }
        }
        state anonymous {
            entry action { assign count := 2; }
            exit action { send new Ping() to p; }
        }
        state shorthand {
            entry assign count := 3;
            exit send new Ping() to p;
        }
        state empty {
            entry action namedEmpty;
            exit action {}
        }
        state absent;
        transition first named accept Ping
            do action effect { assign count := 4; } then anonymous;
        transition first anonymous accept Ping
            do action { assign count := 5; } then shorthand;
        transition first shorthand accept Ping
            do assign count := 6 then empty;
        transition first empty accept Ping
            do send new Ping() to p then absent;
    }
}
