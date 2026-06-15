package Microwave {
    private import ScalarValues::*;
    private import SI::*;

    item def StartCmd;
    item def PauseCmd;
    item def ResumeCmd;
    item def DoorOpen;
    item def Finished;

    // Hierarchy + parallel showcase: `cooking` is a composite state whose
    // `heating` substate runs two parallel regions (heater and turntable).
    // Substates never reference root attributes: rosetta renders composite
    // scopes as child reactors that cannot see the parent's state.
    state def MicrowaveBehavior {
        port commPort;

        entry;
            then idle;

        state idle;

        state cooking {
            entry;
                then heating;

            state heating parallel {
                state heater {
                    entry;
                        then warming;
                    state warming;
                    transition first warming accept after 0.4 [s] then done;
                }
                state turntable {
                    entry;
                        then rotating;
                    state rotating;
                    transition first rotating accept after 0.6 [s] then done;
                }
            }

            state paused;

            // Pause is a group interrupt on the parallel state; resuming
            // re-enters `heating`, which RESTARTS both regions (composite
            // re-entry resets contained machines -- LF reset semantics).
            transition first heating accept PauseCmd then paused;
            transition first paused accept ResumeCmd then heating;
            // Both regions completed: the cooking cycle is done.
            transition first heating then done;
        }

        transition first idle accept StartCmd via commPort then cooking;
        // Door-open group interrupt aborts cooking from any substate.
        transition first cooking accept DoorOpen then idle;
        // Completion semantics: fires when `cooking` reaches its `done`;
        // announces Finished on commPort so a paired testbench observes it.
        transition first cooking do send new Finished() via commPort then idle;
    }

    // Testbench: after 0.1 s sends StartCmd; expects Finished within 5 s
    // (the cooking cycle completes at ~0.6 s logical). Missing it latches
    // verdict := 1, which violates `testPassed` and aborts with exit 1.
    state def MicrowaveTest {
        attribute verdict : Integer := 0;
        assert constraint testPassed { verdict == 0 }

        port commPort;

        entry; then starting;
        state starting;
        state cookingWait;
        state fail {
            entry assign verdict := 1;
        }

        transition first starting
            accept after 0.1 [s]
            do send new StartCmd() via commPort
            then cookingWait;
        transition first cookingWait accept Finished via commPort then done;
        transition first cookingWait accept after 5.0 [s] then fail;
        transition first fail then done;
    }

    part def Microwave       { port commPort; exhibit state : MicrowaveBehavior; }
    part def MicrowaveTester { port commPort; exhibit state : MicrowaveTest; }

    part microwaveSystem {
        part plant : Microwave;
        part tb    : MicrowaveTester;
        connect plant.commPort to tb.commPort;
    }
}
