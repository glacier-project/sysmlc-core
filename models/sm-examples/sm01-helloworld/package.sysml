package SM01 {
    state def Machine {
        entry;
            then idle;

        state idle;
        state running;

        transition first idle then running;
    }
}
