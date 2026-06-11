package Stopwatch {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::DurationValue;

    item def StartCmd;
    item def StopCmd;
    item def ResetCmd;

    state def Stopwatch {
        attribute elapsed : Integer := 0;

        entry;
            then stopped;

        state stopped;
        state running;

        transition first stopped accept StartCmd then running;
        // Periodic tick: the after-self-loop re-enters `running`, which
        // restarts the mode timer -- one increment per second.
        transition first running
            accept after 1 [s]
            do assign elapsed := elapsed + 1
            then running;
        transition first running accept StopCmd then stopped;
        transition first stopped
            accept ResetCmd
            do assign elapsed := 0
            then stopped;
    }
}
