package TrafficLight {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::DurationValue;

    enum def LightColor :> String {
        enum red = "red";
        enum green = "green";
        enum yellow = "yellow";
    }

    item def PedestrianRequest;
    // Announced on commPort when a pedestrian request triggers the walk
    // (yellow) phase; lets a paired testbench observe the pedestrian cycle.
    item def WalkOn;

    state def TrafficLight {
        attribute color : LightColor := LightColor::red;
        attribute requested : Boolean := false;

        port commPort;

        entry;
            then showRed;

        state showRed {
            entry action {
                assign color := LightColor::red;
                assign requested := false;
            }
        }
        state showGreen {
            entry assign color := LightColor::green;
        }
        // Transient latch: entered when a PedestrianRequest is accepted in
        // showGreen. Its completion transition fires at the next microstep
        // (same logical time, later priority), so the WalkOn announcement
        // arrives as a logical action -- after the testbench has settled into
        // walkWait. Mirrors the microwave `cooking` completion pattern.
        state walkRequest;
        state showYellow {
            entry assign color := LightColor::yellow;
        }

        transition first showRed accept after 4 [s] then showGreen;
        transition first showGreen
            accept PedestrianRequest
            do assign requested := true
            then walkRequest;
        // Completion: announces WalkOn then proceeds to showYellow.
        transition first walkRequest
            do send new WalkOn() via commPort
            then showYellow;
        transition first showGreen accept after 6 [s] then showYellow;
        transition first showYellow accept after 2 [s] then showRed;
    }

    // Testbench: after 5 s transitions to walkWait; the walkWait entry action
    // sends PedestrianRequest (at the next microstep, when the mode is already
    // active) so WalkOn arrives after walkWait is fully settled. Expects WalkOn
    // within 15 s (stimulus near 5 s + 2 s showYellow + generous margin).
    // Missing it latches verdict := 1, which violates `testPassed`, exit 1.
    state def TrafficLightTest {
        attribute verdict : Integer := 0;
        assert constraint testPassed { verdict == 0 }

        port commPort;

        entry; then waitGreen;
        state waitGreen;
        // Entry: send PedestrianRequest so it arrives in the next microstep,
        // after this mode is active -- ensures reaction(WalkOn) fires here.
        state walkWait {
            entry send new PedestrianRequest() via commPort;
        }
        state fail {
            entry assign verdict := 1;
        }

        transition first waitGreen accept after 5.0 [s] then walkWait;
        transition first walkWait accept WalkOn then done;
        transition first walkWait accept after 15.0 [s] then fail;
        transition first fail then done;
    }

    part def TrafficLightRig {
        exhibit state plant : TrafficLight;
        exhibit state tb : TrafficLightTest;
    }
}
