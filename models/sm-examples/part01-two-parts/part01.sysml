package Part01 {
    private import ScalarValues::*;
    private import SI::*;

    item def Ping;
    item def Pong;

    state def PlantBehavior {
        port commPort;
        entry; then idle;
        state idle;
        state pinged;
        transition first idle accept Ping via commPort then pinged;
        transition first pinged
            do send new Pong() via commPort
            then idle;
    }
    state def TesterBehavior {
        port commPort;
        attribute verdict : Integer := 0;
        assert constraint ok { verdict == 0 }
        entry; then ready;
        state ready;
        state waitPong;
        state fail { entry assign verdict := 1; }
        transition first ready
            accept after 0.1 [s]
            do send new Ping() via commPort
            then waitPong;
        transition first waitPong accept Pong via commPort then done;
        transition first waitPong accept after 5.0 [s] then fail;
        transition first fail then done;
    }

    part def Plant  { port commPort; exhibit state : PlantBehavior; }
    part def Tester { port commPort; exhibit state : TesterBehavior; }

    part pingSystem {                         // top-level usage -> main reactor
        part plant : Plant;
        part tb : Tester;
        connect plant.commPort to tb.commPort;
    }
}
