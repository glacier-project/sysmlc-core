package SM01 {
    state def Machine {
        entry;
            then idle;

        state idle;
        state running;

        transition first idle then running;
    }

    state def MachineInitial1_ByTransition {
        first start then idle;

        state idle;
        state running;

        transition first idle then running;
    }

    state def MachineInitial3_ByQualifiedName {
        entry; then MachineInitial3_ByQualifiedName::idle;

        state idle;
        state running;

        transition first idle then running;
    }
}
