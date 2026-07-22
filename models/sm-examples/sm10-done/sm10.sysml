package SM10 {
    private import ScalarValues::*;

    // Root-level done.
    state def MachineRootDone {
        entry;
            then idle;
        state idle;
        state running;
        transition first idle then running;
        transition first running then done;
    }

    // Nested done: the machine stays alive.
    state def MachineNestedDone {
        entry;
            then running;
        state running {
            entry;
                then warming;
            state warming;
            state hot;
            transition first warming then hot;
            transition first hot then done;
        }
        state stopped;
        transition first running then stopped;
    }

    // Parallel: each region reaches its own done.
    state def MachineParallelDone parallel {
        state lights {
            entry;
                then off;
            state off;
            state on;
            transition first off then on;
            transition first on then done;
        }
        state sound {
            entry;
                then silent;
            state silent;
            state beeping;
            transition first silent then beeping;
            transition first beeping then done;
        }
    }

    // Two `then done` in one scope share a single final state.
    state def MachineTwoDone {
        attribute shortcut : Boolean := true;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if shortcut then done;
        transition first idle if not shortcut then running;
        transition first running then done;
    }

    item def EventA;
    item def EventB;
    item def EventC;
    item def Pause;
    item def Resume;

    // A completion transition leaving a parallel state is a join: it may
    // fire only once every region has independently reached its own done.
    state def MachineParallelJoin {
        entry;
            then working;
        state working parallel {
            state a {
                entry;
                    then a1;
                state a1;
                transition first a1 accept EventA then done;
            }
            state b {
                entry;
                    then b1;
                state b1;
                transition first b1 accept EventB then done;
            }
        }
        state finished;
        transition first working then finished;
    }

    // A completion transition leaving a plain composite is the N=1 case of
    // the same join: it may fire only once the composite has reached its own
    // done, not as soon as the composite is entered.
    state def MachineCompositeJoin {
        entry;
            then working;
        state working {
            entry;
                then w1;
            state w1;
            transition first w1 accept EventA then done;
        }
        state finished;
        transition first working then finished;
    }

    // A three-region join: the completion transition may fire only once
    // every one of the three regions has independently reached its own
    // done, not when only two of the three have.
    state def MachineParallelJoinThree {
        entry;
            then working;
        state working parallel {
            state a {
                entry;
                    then a1;
                state a1;
                transition first a1 accept EventA then done;
            }
            state b {
                entry;
                    then b1;
                state b1;
                transition first b1 accept EventB then done;
            }
            state c {
                entry;
                    then c1;
                state c1;
                transition first c1 accept EventC then done;
            }
        }
        state finished;
        transition first working then finished;
    }

    // Restart / re-arm: `working` is a parallel state that can be paused
    // (a group interrupt) and resumed mid-completion. Re-entering `working`
    // must reset every region's completion flag, so a partial completion
    // left over from before the pause cannot make the join fire early.
    state def MachineParallelRestart {
        entry;
            then working;
        state working parallel {
            state a {
                entry;
                    then a1;
                state a1;
                transition first a1 accept EventA then done;
            }
            state b {
                entry;
                    then b1;
                state b1;
                transition first b1 accept EventB then done;
            }
        }
        state paused;
        state finished;
        transition first working accept Pause then paused;
        transition first paused accept Resume then working;
        transition first working then finished;
    }

    // A user `if` guard on a completion-gated eventless transition: the
    // guard and the completion flag are both required. Two eventless
    // branches share `working` as their source, so each must carry the
    // completion gate as well as its own guard.
    state def MachineGuardedJoin {
        attribute go : Boolean := false;
        entry;
            then working;
        state working {
            entry;
                then w1;
            state w1;
            transition first w1 accept EventA then done;
        }
        state approved;
        state rejected;
        transition first working if go then approved;
        transition first working if not go then rejected;
    }

    // A nested chain of completions: three composites, each with its own
    // done, so the outermost eventless transition may fire only once the
    // whole chain has bottomed out, not after any single level completes.
    state def MachineDeepJoin {
        entry;
            then l1;
        state l1 {
            entry;
                then l2;
            state l2 {
                entry;
                    then l3;
                state l3 {
                    entry;
                        then leaf;
                    state leaf;
                    transition first leaf accept EventA then done;
                }
                transition first l3 then done;
            }
            transition first l2 then done;
        }
        state finished;
        transition first l1 then finished;
    }

    // A parallel state where only one region has a `then done`: the other
    // (`b`) never reaches a scoped final at all. Once any region uses the
    // done/join pattern, every region is required, `b`'s missing done
    // means the join can never legitimately fire, not that it is silently
    // exempt from it.
    state def MachinePartialJoin {
        entry;
            then working;
        state working parallel {
            state a {
                entry;
                    then a1;
                state a1;
                transition first a1 accept EventA then done;
            }
            state b {
                entry;
                    then b1;
                state b1;
                state b2;
                transition first b1 accept EventB then b2;
            }
        }
        state finished;
        transition first working then finished;
    }
}
