package FurutaPendulum {
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import TrigFunctions::*;
    private import SI::*;

    item def AngleReading {
        attribute theta : Real;
    }
    // Announced on commPort when the controller transitions into stabilizing;
    // lets a paired testbench observe that the pendulum reached the balanced
    // region (|theta| < catchAngle on two consecutive readings).
    item def Balanced;

    state def PendulumController {
        in attribute catchAngle : Real default 0.5;
        in attribute dropAngle : Real default 1.2;

        inout attribute energy : Real := 0.0;

        port commPort;

        entry;
            then swingUp;

        state swingUp;
        state catching;
        // Transient latch: entered when a second consecutive AngleReading
        // confirms |theta| < catchAngle.  Its completion transition fires at
        // the next microstep (same logical time, later priority), so the
        // Balanced announcement arrives as a logical action -- after the
        // testbench has settled into balancedWait.  Mirrors the traffic-light
        // `walkRequest` pattern (and solves the LF causality cycle: the send
        // is not in the same reaction that consumed AngleReading).
        state announcing;
        state stabilizing;

        transition first swingUp
            accept reading : AngleReading
            if abs(reading.theta) < catchAngle
            then catching;
        transition first catching
            accept reading : AngleReading
            if abs(reading.theta) < catchAngle
            do assign energy := cos(reading.theta)
            then announcing;
        transition first catching
            accept reading : AngleReading
            if abs(reading.theta) >= catchAngle
            then swingUp;
        // Completion: announce Balanced and enter stabilizing.
        transition first announcing
            do send new Balanced() via commPort
            then stabilizing;
        transition first stabilizing
            accept reading : AngleReading
            if abs(reading.theta) >= dropAngle
            then swingUp;
    }

    // Testbench: drives a scripted theta sequence and verifies the controller
    // announces Balanced (i.e. reaches stabilizing) on the way through.
    //
    // Trajectory rationale
    // --------------------
    // Thetas [1.5, 0.9, 0.4, 0.3, 0.2, 0.1, 1.4] sampled every 0.1 s mirror
    // the run-test drivers.  The first four readings drive the full swing-up
    // and catch sequence; the remaining three are exercised by the standalone
    // showcase run-test (test_showcase_furuta_pendulum) and the run_all script.
    //
    //   t=0.1 s  theta=1.5 (≥0.5)  → swingUp stays
    //   t=0.2 s  theta=0.9 (≥0.5)  → swingUp stays
    //   t=0.3 s  theta=0.4 (<0.5)  → swingUp→catching
    //   t=0.4 s  theta=0.3 (<0.5)  → catching→announcing→stabilizing
    //            Balanced sent (via `announcing` transient state, one
    //            microstep after step4 fires), balancedWait already active
    //
    // Design choice: the chain ends at step4.  After step4 the testbench
    // enters `balancedWait` and waits for Balanced.  Extending the chain
    // further (thetas 0.2, 0.1, 1.4) would create a same-tag dependency
    // loop in LF 0.11: `Balanced → reset(step5) → step5 startup →
    // t_step5 → AngleReading → plant → Balanced` is flagged as a causality
    // cycle by lfc's conservative modal-reactor analysis even though the
    // timer fires at a strictly later logical time.  The four-send prefix
    // is sufficient to prove stabilization; the full seven-reading scenario
    // is covered by the standalone machine run-test.
    state def FurutaTest {
        attribute verdict : Integer := 0;
        assert constraint testPassed { verdict == 0 }

        port commPort;

        entry; then step1;

        // --- stimulus chain (four sends, one per 0.1 s) ---
        state step1;
        state step2;
        state step3;
        state step4;
        // verdict gate: Balanced is announced at t=0.4 s + 1 microstep,
        // while balancedWait is already the active state -- no priority
        // tricks needed.
        state balancedWait;
        state fail {
            entry assign verdict := 1;
        }

        transition first step1
            accept after 0.1 [s]
            do send new AngleReading(1.5) via commPort
            then step2;
        transition first step2
            accept after 0.1 [s]
            do send new AngleReading(0.9) via commPort
            then step3;
        transition first step3
            accept after 0.1 [s]
            do send new AngleReading(0.4) via commPort
            then step4;
        // theta=0.3 triggers catching→announcing→stabilizing; Balanced is
        // sent from `announcing`'s entry reaction one microstep after this
        // timer fires, so balancedWait is already active when it arrives.
        transition first step4
            accept after 0.1 [s]
            do send new AngleReading(0.3) via commPort
            then balancedWait;
        transition first balancedWait accept Balanced then done;
        transition first balancedWait accept after 5.0 [s] then fail;
        transition first fail then done;
    }

    part def FurutaRig {
        exhibit state plant : PendulumController;
        exhibit state tb : FurutaTest;
    }
}
