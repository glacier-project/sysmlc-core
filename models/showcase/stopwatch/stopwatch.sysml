package Stopwatch {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::DurationValue;

    item def StartCmd;
    item def StopCmd;
    item def ResetCmd;
    // Announced on commPort when a StopCmd is accepted in running;
    // lets a paired testbench observe the stop event.
    item def Stopped;

    state def StopwatchBehavior {
        attribute elapsed : Integer := 0;

        port commPort;

        entry;
            then stopped;

        state stopped;
        state running;

        transition first stopped accept StartCmd via commPort then running;
        // Periodic tick: the after-self-loop re-enters `running`, which
        // restarts the mode timer -- one increment per second.
        transition first running
            accept after 1 [s]
            do assign elapsed := elapsed + 1
            then running;
        // Completion: announces Stopped on commPort so a paired testbench
        // observes the run/stop cycle.
        transition first running
            accept StopCmd via commPort
            do send new Stopped() via commPort
            then stopped;
        transition first stopped
            accept ResetCmd
            do assign elapsed := 0
            then stopped;
    }

    // Testbench: after 0.1 s sends StartCmd; after 3.4 s more (absolute 3.5 s)
    // transitions to stopWait whose entry action sends StopCmd -- so the mode
    // is already active when Stopped comes back (same microstep pattern as
    // TrafficLightTest.walkWait). Expects Stopped within 10 s; missing it
    // latches verdict := 1, violates `testPassed`, aborts with exit 1.
    state def StopwatchTest {
        attribute verdict : Integer := 0;
        assert constraint testPassed { verdict == 0 }

        port commPort;

        entry; then starting;
        state starting;
        state runningWait;
        // Entry: send StopCmd so it arrives in the next microstep, after
        // this mode is active -- ensures reaction(Stopped) fires here.
        state stopWait {
            entry send new StopCmd() via commPort;
        }
        state fail {
            entry assign verdict := 1;
        }

        transition first starting
            accept after 0.1 [s]
            do send new StartCmd() via commPort
            then runningWait;
        transition first runningWait accept after 3.4 [s] then stopWait;
        transition first stopWait accept Stopped via commPort then done;
        transition first stopWait accept after 10.0 [s] then fail;
        transition first fail then done;
    }

    part def Stopwatch       { port commPort; exhibit state : StopwatchBehavior; }
    part def StopwatchTester { port commPort; exhibit state : StopwatchTest; }

    part stopwatchSystem {
        part plant : Stopwatch;
        part tb    : StopwatchTester;
        connect plant.commPort to tb.commPort;
    }
}
