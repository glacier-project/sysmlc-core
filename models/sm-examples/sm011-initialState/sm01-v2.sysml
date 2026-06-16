package SM01v2 {
    state def MachineInitial_ByTransition {
        first start then idle;

        state idle;
        state running;

        transition first idle then running;
    }

    state def MachineInitial_ByEntry {
        entry; then idle;

        state idle;
        state running;

        transition first idle then running;
    }

    state def MachineInitial_ByQualifiedName {
        entry; then container::idle;

        state container {
            state idle;
            state running;

            transition first idle then running;
        }
    }

    state def MachineInitial_ByFeatureChain {
        entry; then container.idle;

        state container {
            state idle;
            state running;

            transition first idle then running;
        }
    }

    state def MachineInitial_NoDeclared {
        state idle;
        state running;

        transition first idle then running;
    }
}
