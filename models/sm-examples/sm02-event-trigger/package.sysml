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
}
