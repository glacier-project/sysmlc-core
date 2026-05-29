package SM04 {
    private import ScalarValues::*;

    state def MachineEntryIncrement {
        attribute counter : Integer := 0;
        entry;
            then idle;
        state idle {
            entry action incr {
                assign counter := counter + 1;
            }
        }
        state running;
        transition first idle then running;
    }

    state def MachineExitDecrement {
        attribute counter : Integer := 1;
        entry;
            then idle;
        state idle {
            exit action dec {
                assign counter := counter - 1;
            }
        }
        state running;
        transition first idle then running;
    }

    state def MachineMultiEntry {
        attribute a : Integer := 0;
        attribute b : Integer := 0;
        entry;
            then idle;
        state idle {
            entry action setup {
                assign a := 1;
                assign b := a + 2;
            }
        }
        state running;
        transition first idle then running;
    }

    state def MachineEntryAndExit {
        attribute entered : Integer := 0;
        attribute exited : Integer := 0;

        entry;
            then idle;
        state idle {
            entry action onEnter {
                assign entered := entered + 1;
            }
            exit action onExit {
                assign exited := exited + 1;
            }
        }
        state running;
        transition first idle then running;
    }
}
