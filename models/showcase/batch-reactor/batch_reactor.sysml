package BatchReactor {
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import SI::*;
    private import ISQ::DurationValue;

    item def StartRecipe;
    item def Abort;
    item def PressureReading {
        attribute bar : Real;
    }
    item def BatchDone {
        attribute count : Integer;
    }

    // A recipe-driven batch reactor: closed-loop fill/heat/cool/drain
    // phases simulated with saturating dynamics (whitelisted min/max),
    // a reaction stage running agitation in parallel with an
    // overpressure watchdog (payload-guarded), emergency venting, and a
    // configurable number of batches before the controller stops.
    //
    // Phase dynamics follow the thermostat idiom: ONE periodic
    // after-self-loop per mode plus a guarded eventless transition
    // checked on every re-entry.
    state def BatchReactorBehavior {
        port commPort;

        in attribute tankCapacity : Real default 100.0;
        in attribute targetLevel : Real default 60.0;
        in attribute targetTemp : Real default 85.0;
        in attribute batchTarget : Integer default 2;
        in attribute inflowRate : Real default 20.0;
        in attribute heatRate : Real default 12.0;
        in attribute coolRate : Real default 15.0;
        in attribute drainRate : Real default 30.0;
        // Rational magnitude on purpose: fractional overrides ("500 [ms]")
        // can only land in a rational literal.
        attribute sampleTime : DurationValue default 1.0 [s];
        attribute level : Real := 0.0;
        attribute temperature : Real := 20.0;
        attribute batches : Integer := 0;
        attribute vented : Integer := 0;

        assert constraint levelInTank {
            level >= 0.0 and level <= tankCapacity
        }
        assert constraint tempBounded {
            temperature >= 0.0 and temperature <= 150.0
        }
        assert constraint productionCounts { batches >= 0 and vented >= 0 }

        entry;
            then idle;

        state idle;
        state filling;
        state heating;

        // Reaction stage: agitation runs to completion while the
        // watchdog either trips on a strong pressure reading
        // (deep-exiting into emergency venting) or closes its window.
        state reacting parallel {
            state agitation {
                entry;
                    then stirring;
                state stirring;
                state settling;
                transition first stirring accept after 1.5 [s] then settling;
                transition first settling accept after 1.0 [s] then done;
            }
            state ventWatch {
                entry;
                    then watching;
                state watching;
                state overpressure;
                transition first watching
                    accept reading : PressureReading
                    if reading.bar >= 9.0
                    then overpressure;
                transition first watching accept after 3.0 [s] then done;
                transition first overpressure then venting;
            }
        }

        state venting;
        state cooling;
        state draining;

        transition first idle accept StartRecipe via commPort then filling;

        transition first filling
            accept after sampleTime
            do assign level := min(level + inflowRate, tankCapacity)
            then filling;
        transition first filling if level >= targetLevel then heating;
        transition first filling accept Abort via commPort then draining;

        transition first heating
            accept after sampleTime
            do assign temperature := min(temperature + heatRate, 150.0)
            then heating;
        transition first heating if temperature >= targetTemp then reacting;
        transition first heating accept Abort via commPort then draining;

        // Join of agitation and the watchdog window.
        transition first reacting then cooling;
        transition first reacting accept Abort via commPort then venting;

        transition first venting
            accept after 1.5 [s]
            do action {
                assign vented := vented + 1;
                assign temperature := temperature - 10.0;
            }
            then cooling;

        transition first cooling
            accept after sampleTime
            do assign temperature := max(temperature - coolRate, 20.0)
            then cooling;
        transition first cooling if temperature <= 40.0 then draining;

        transition first draining
            accept after sampleTime
            do assign level := max(level - drainRate, 0.0)
            then draining;
        transition first draining
            if level <= 0.0 and batches + 1 >= batchTarget
            do action {
                assign batches := batches + 1;
                send new BatchDone(batches) via commPort;
            }
            then done;
        transition first draining
            if level <= 0.0 and batches + 1 < batchTarget
            do action {
                assign batches := batches + 1;
                send new BatchDone(batches) via commPort;
            }
            then filling;
    }

    // Testbench: at 0.2 s sends StartRecipe; waits for BatchDone (announced
    // by the reactor on every completed batch).  A generous 30 s fail-window
    // accommodates the full fill/heat/react/cool/drain cycle (~7.2 s logical
    // with the sped-up values.yaml overrides: batchTarget=1, inflowRate=60,
    // heatRate=65, coolRate=60, drainRate=60; sampleTime stays at model
    // default 1.0 s).
    //
    // No `announcing` transient latch needed: BatchDone is sent on a GUARDED
    // eventless completion transition from `draining` (level<=0 guard), not
    // directly in the same reaction that consumes an input -- so there is no
    // read-input + write-output cycle that lfc 0.11 would flag.
    state def BatchReactorTest {
        attribute verdict : Integer := 0;
        assert constraint testPassed { verdict == 0 }

        port commPort;

        entry; then starting;
        state starting;
        state batchWait;
        state fail {
            entry assign verdict := 1;
        }

        transition first starting
            accept after 0.2 [s]
            do send new StartRecipe() via commPort
            then batchWait;
        transition first batchWait accept BatchDone via commPort then done;
        transition first batchWait accept after 30.0 [s] then fail;
        transition first fail then done;
    }

    part def BatchReactor       { port commPort; exhibit state : BatchReactorBehavior; }
    part def BatchReactorTester { port commPort; exhibit state : BatchReactorTest; }

    part batchReactorSystem {
        part plant : BatchReactor;
        part tb    : BatchReactorTester;
        connect plant.commPort to tb.commPort;
    }
}
