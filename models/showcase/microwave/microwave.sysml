package Microwave {
    private import ScalarValues::*;
    private import SI::*;

    item def StartCmd;
    item def PauseCmd;
    item def ResumeCmd;
    item def DoorOpen;

    // Hierarchy + parallel showcase: `cooking` is a composite state whose
    // `heating` substate runs two parallel regions (heater and turntable).
    // Substates never reference root attributes: rosetta renders composite
    // scopes as child reactors that cannot see the parent's state.
    state def Microwave {
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

        transition first idle accept StartCmd then cooking;
        // Door-open group interrupt aborts cooking from any substate.
        transition first cooking accept DoorOpen then idle;
        // Completion semantics: fires when `cooking` reaches its `done`.
        transition first cooking then idle;
    }
}
