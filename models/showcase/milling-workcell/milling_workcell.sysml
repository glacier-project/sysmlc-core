package MillingWorkcell {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::DurationValue;

    enum def CellStatus :> String {
        enum offline = "offline";
        enum standby = "standby";
        enum running = "running";
        enum recovering = "recovering";
        enum failed = "failed";
    }

    item def PowerOn;
    item def StartBatch;
    item def Shutdown;
    item def EStop;
    item def DoorOpened;
    item def DoorClosed;
    item def Reset;
    item def ToolChanged;
    item def VibrationSpike {
        attribute level : Integer;
    }
    item def BatchReport {
        attribute pieces : Integer;
        attribute wear : Real;
    }

    // An automated milling workcell: power-up homing sequence, a batch
    // production loop whose machining stage runs three parallel regions
    // (spindle ∥ coolant ∥ vibration monitor), bounded fault recovery,
    // tool-wear bookkeeping with a service interlock, and safety
    // interrupts (door, emergency stop).
    //
    // Authoring constraint (rosetta scope rule): substates inside
    // composite scopes never reference machine attributes — data logic
    // lives at root scope; composite internals are signal/timer-driven.
    state def MillingWorkcell {
        port reportPort;

        in attribute batchSize : Integer default 4;
        in attribute toolWearLimit : Real default 100.0;
        in attribute wearPerPiece : Real default 7.5;
        in attribute maxRetries : Integer default 3;
        // Rational magnitude on purpose: fractional overrides ("500 [ms]")
        // can only land in a rational literal.
        attribute retryDelay : DurationValue default 2.0 [s];
        attribute produced : Integer := 0;
        attribute faults : Integer := 0;
        attribute services : Integer := 0;
        attribute toolWear : Real := 0.0;
        attribute status : CellStatus := CellStatus::offline;

        assert constraint wearWithinLimit {
            toolWear >= 0.0 and toolWear <= toolWearLimit
        }
        assert constraint countersNonNegative {
            produced >= 0 and faults >= 0 and services >= 0
        }
        assert constraint retriesBounded { faults <= maxRetries }

        entry;
            then cold;

        state cold {
            entry assign status := CellStatus::offline;
        }

        // Power-up homing: one axis at a time, completion hands over to
        // `ready` (an eventless transition out of a composite fires on
        // its completion, never on entry).
        state homing {
            entry;
                then axisX;
            state axisX;
            state axisY;
            state axisZ;
            transition first axisX accept after 0.3 [s] then axisY;
            transition first axisY accept after 0.3 [s] then axisZ;
            transition first axisZ accept after 0.3 [s] then done;
        }

        state ready {
            entry assign status := CellStatus::standby;
        }

        // One pass through `producing` machines ONE piece; the batch loop
        // is closed by the guarded completion transitions below.
        state producing {
            entry;
                then loadPart;
            state loadPart;
            state machining parallel {
                state spindle {
                    entry;
                        then spinUp;
                    state spinUp;
                    state cutting;
                    transition first spinUp accept after 0.2 [s] then cutting;
                    transition first cutting accept after 1.0 [s] then done;
                }
                state coolant {
                    entry;
                        then priming;
                    state priming;
                    state flowing;
                    transition first priming accept after 0.1 [s] then flowing;
                    transition first flowing accept after 1.0 [s] then done;
                }
                // The monitor trips on a strong vibration reading and
                // DEEP-EXITS two scopes up into fault recovery; its
                // watching window otherwise closes after the cut.
                state monitor {
                    entry;
                        then watching;
                    state watching;
                    state tripped;
                    transition first watching
                        accept spike : VibrationSpike
                        if spike.level >= 4
                        then tripped;
                    transition first watching accept after 1.3 [s] then done;
                    transition first tripped then faultRecovery;
                }
            }
            state unloadPart;
            transition first loadPart accept after 0.5 [s] then machining;
            // Join: fires when ALL three regions have completed.
            transition first machining then unloadPart;
            transition first unloadPart accept after 0.3 [s] then done;
        }

        state paused;
        state faultRecovery {
            entry action {
                assign status := CellStatus::recovering;
                assign faults := faults + 1;
            }
        }
        state triage;
        state toolService;
        // Transient latch: entered when a batch completes (produced + 1 >=
        // batchSize). Its eventless completion transition fires one microstep
        // later, sending BatchReport via reportPort after `ready` (and the
        // testbench's `batchWait`) are already active. This breaks the LF
        // causality cycle that lfc 0.11 would otherwise flag: if the send
        // were in the same reaction as `reset(ready)`, lfc sees the path
        // plant.BatchReport → tb.BatchReport → tb.Shutdown → plant.Shutdown
        // (consumed in `ready`) as a same-tag cycle. Mirrors the
        // furuta-pendulum `announcing` pattern.
        state announcing;
        state emergencyStop {
            entry assign status := CellStatus::failed;
        }
        state alarmed {
            entry assign status := CellStatus::failed;
        }

        transition first cold accept PowerOn then homing;
        transition first homing then ready;

        // A worn tool intercepts the next batch: same-signal guards form
        // a first-match dispatch.
        transition first ready
            accept StartBatch
            if toolWear < toolWearLimit * 0.8
            do assign status := CellStatus::running
            then producing;
        transition first ready
            accept StartBatch
            if toolWear >= toolWearLimit * 0.8
            then toolService;
        transition first ready accept Shutdown then done;

        // Batch loop on piece completion; the fault counter clears with
        // every completed batch.
        transition first producing
            if produced + 1 < batchSize
            do action {
                assign produced := produced + 1;
                assign toolWear := toolWear + wearPerPiece;
            }
            then producing;
        transition first producing
            if produced + 1 >= batchSize
            do action {
                assign produced := produced + 1;
                assign toolWear := toolWear + wearPerPiece;
                assign faults := 0;
            }
            then announcing;
        // Completion: send BatchReport one microstep after batch finishes,
        // then return to ready for the next batch or Shutdown.
        transition first announcing
            do send new BatchReport(produced, toolWear) via reportPort
            then ready;

        // Group interrupts on the running batch (the piece in progress
        // is lost; contained machines reset on re-entry).
        transition first producing accept DoorOpened then paused;
        transition first producing accept EStop then emergencyStop;
        transition first paused accept DoorClosed then producing;
        transition first paused accept EStop then emergencyStop;

        // Bounded retry: triage decides on entry between another attempt
        // and the alarm latch.
        transition first faultRecovery accept after retryDelay then triage;
        transition first triage if faults < maxRetries then producing;
        transition first triage if faults >= maxRetries then alarmed;

        transition first toolService
            accept ToolChanged
            do action {
                assign toolWear := 0.0;
                assign services := services + 1;
            }
            then ready;

        transition first emergencyStop
            accept Reset
            do assign faults := 0
            then cold;
        transition first alarmed
            accept Reset
            do assign faults := 0
            then cold;
    }

    // Testbench: drives PowerOn at 0.1 s, StartBatch at 1.2 s (absolute),
    // then waits for BatchReport — the batch-completion announcement the
    // plant sends on reportPort via the `announcing` transient latch once
    // all batchSize pieces are machined. On receipt the testbench goes to
    // done (request_stop() ends the simulation; no Shutdown needed).
    //
    // The testbench intentionally does NOT send Shutdown.  Wiring Shutdown
    // between the testbench and the plant would create an lfc 0.11 causality
    // cycle: `announcing.startup → BatchReport + reset(ready)` → `tb.BatchReport`
    // → `tb reaction → shutdownSend` → `Shutdown` → `plant.ready reaction(Shutdown)`.
    // Omitting Shutdown breaks the cycle; the plant stays in `ready` while
    // the testbench calls request_stop(), which cleanly ends the run.
    //
    // A 20 s timeout guards against stalls (generous: one piece ≈ 2.1 s
    // logical; even four pieces + homing finish well under 12 s).
    state def MillingWorkcellTest {
        attribute verdict : Integer := 0;
        assert constraint testPassed { verdict == 0 }

        port commPort;

        entry; then powerWait;
        state powerWait;
        state startWait;
        state batchWait;
        state fail {
            entry assign verdict := 1;
        }

        // Stimulus chain (absolute logical times, batchSize = 1):
        //   0.1 s  send PowerOn   → plant: cold → homing (0.9 s total)
        //   1.2 s  send StartBatch → plant: ready → producing → announcing
        //  ~3.3 s  BatchReport received from announcing microstep
        //  testbench → done (request_stop)
        transition first powerWait
            accept after 0.1 [s]
            do send new PowerOn() via commPort
            then startWait;
        transition first startWait
            accept after 1.1 [s]
            do send new StartBatch() via commPort
            then batchWait;
        transition first batchWait accept BatchReport then done;
        transition first batchWait accept after 20.0 [s] then fail;
        transition first fail then done;
    }

    part def MillingWorkcellRig {
        exhibit state plant : MillingWorkcell;
        exhibit state tb : MillingWorkcellTest;
    }
}
