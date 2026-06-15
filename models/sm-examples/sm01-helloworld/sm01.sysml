package SM01 {
    state def MachineEntryThen {
        entry;
            then idle;

        state idle;
        state running;

        transition first idle then running;
    }

    state def MachineFirstStartThen {
        first start then idle;

        state idle;
        state running;

        transition first idle then running;
    }
}
