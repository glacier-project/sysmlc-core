package SM01v2 {
    state def MachineInitial1_ByTransition {
        first start then idle;

        state idle;
        state running;

        transition first idle then running;
    }

    state def MachineInitial2_ByEntry {
        entry; then idle;

        state idle;
        state running;

        transition first idle then running;
    }

    state def MachineInitial3_ByQualifiedName {
        entry; then container::idle;

        state container {
            state idle;
            state running;

            transition first idle then running;
        }
    }

    state def MachineInitial4_ByFeatureChain {
        entry; then container.idle;

        state container {
            state idle;
            state running;

            transition first idle then running;
        }
    }

    state def MachineInitial5_NoDeclared_TestError {
        state idle;
        state running;

        transition first idle then running;
    }
}
