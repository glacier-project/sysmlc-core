package SM12 {
    private import ScalarValues::*;

    item def Ping;

    // A do-action body runs once at state entry: a single assign.
    state def MachineDoAssign {
        attribute progress : Integer := 0;
        entry;
            then working;
        state working {
            do action {
                assign progress := progress + 1;
            }
        }
        state finished;
        transition first working then finished;
    }

    // A do-action body with multiple assigns, in declaration order.
    state def MachineDoMulti {
        attribute a : Integer := 0;
        attribute b : Integer := 0;
        entry;
            then working;
        state working {
            do action {
                assign a := 1;
                assign b := a + 2;
            }
        }
        state finished;
        transition first working then finished;
    }

    // Shorthand do-assign.
    state def MachineDoShorthand {
        attribute progress : Integer := 0;
        entry;
            then working;
        state working {
            do assign progress := progress + 1;
        }
        state finished;
        transition first working then finished;
    }

    // A do-action that sends an event.
    state def MachineDoSend {
        port commPort;
        entry;
            then working;
        state working {
            do action {
                send new Ping() to commPort;
            }
        }
        state finished;
        transition first working then finished;
    }

    // Shorthand do-send.
    state def MachineDoSendShorthand {
        port commPort;
        entry;
            then working;
        state working {
            do send new Ping() to commPort;
        }
        state finished;
        transition first working then finished;
    }

    // Entry action then do action on the same state.
    state def MachineEntryThenDo {
        attribute log : Integer := 0;
        entry;
            then working;
        state working {
            entry assign log := 1;
            do action {
                assign log := log + 10;
            }
        }
        state finished;
        transition first working then finished;
    }

    // A do action on a composite (non-leaf) state usage.
    state def MachineCompositeDo {
        attribute progress : Integer := 0;
        entry;
            then working;
        state working {
            entry;
                then sub1;
            do action {
                assign progress := progress + 1;
            }
            state sub1;
            state sub2;
            transition first sub1 then sub2;
        }
        state finished;
        transition first working then finished;
    }

    // A do action on the root state definition.
    state def MachineRootDo {
        attribute progress : Integer := 0;
        do action {
            assign progress := progress + 1;
        }
        entry;
            then working;
        state working;
        state finished;
        transition first working then finished;
    }

    // A do action on a region of a parallel state.
    state def MachineParallelDo parallel {
        attribute counter : Integer := 0;
        state regionA {
            entry;
                then a1;
            do action {
                assign counter := counter + 1;
            }
            state a1;
            state a2;
            transition first a1 then a2;
        }
        state regionB {
            entry;
                then b1;
            state b1;
            state b2;
            transition first b1 then b2;
        }
    }

    // Run-once-faithful: the do sets a flag a completion (eventless)
    // transition reads, so the machine reaches `finished`.
    state def MachineDoEnablesCompletion {
        attribute ready : Boolean := false;
        entry;
            then working;
        state working {
            do action {
                assign ready := true;
            }
        }
        state finished;
        transition first working if ready then finished;
    }

    // An empty do action.
    state def MachineEmptyDo {
        entry;
            then working;
        state working {
            do;
        }
        state finished;
        transition first working then finished;
    }

    // Entry action then do action at the ROOT/container build site:
    // the entry runs first, the do follows.
    state def MachineRootEntryThenDo {
        attribute x : Integer := 0;
        entry assign x := 1;
            then working;
        do action {
            assign x := x + 10;
        }
        state working;
        state finished;
        transition first working then finished;
    }

    // An empty do action on the root state definition: a no-op
    state def MachineRootEmptyDo {
        do;
        entry;
            then working;
        state working;
        state finished;
        transition first working then finished;
    }

    // A named but empty do block
    state def MachineNamedEmptyDo {
        entry;
            then working;
        state working {
            do action providePower { }
        }
        state finished;
        transition first working then finished;
    }
}
