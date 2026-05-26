package SM02 {
    item def Tick;

    state def Machine {
        port commPort;
        entry;
            then idle;

        state idle;
        state running;

        transition first idle accept Tick via commPort then running;
    }

    state def MachineNamed {
        port commPort;
        entry;
            then idle;

        state idle;
        state running;

        transition first idle
            accept reading : Tick via commPort
            then running;
    }

    state def MachinePortless {
        entry;
            then idle;

        state idle;
        state running;

        transition first idle accept Tick then running;
    }
}
