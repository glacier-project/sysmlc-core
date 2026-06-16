package FurutaPendulum {
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import SI::*;

    // -----------------------------------------------------------------------
    // Data types
    // -----------------------------------------------------------------------

    // Internal state type: composite attribute (attribute def so the backend
    // recognises it as a structured type and emits SimpleNamespace).
    // Default: pendulum hanging DOWN (theta = pi ≈ 3.14159, velocities zero).
    attribute def PendulumState {
        attribute theta   : Real = 3.14159;
        attribute d_theta : Real = 0.0;
        attribute phi     : Real = 0.0;
        attribute d_phi   : Real = 0.0;
    }

    // Signal: simulator → controller (4-field sensor reading).
    item def AngleReading {
        attribute theta   : Real;
        attribute d_theta : Real;
        attribute phi     : Real;
        attribute d_phi   : Real;
    }

    // Signal: controller → simulator (arm torque).
    item def Control { attribute u : Real; }

    // Signal: controller → monitor (balance achieved).
    item def Balanced;

    // -----------------------------------------------------------------------
    // External pure functions (backed by furuta_physics.py at run time).
    // Matched by simple name against furuta_physics module functions.
    // Untyped parameters so both PendulumState and AngleReading (duck-typed)
    // are accepted by the SysML type checker.
    // -----------------------------------------------------------------------
    calc def step             { in x; in u : Real; in dt : Real; return : PendulumState; }
    calc def swingup_torque   { in x; return : Real; }
    calc def catch_torque     { in x; return : Real; }
    calc def stabilize_torque { in x; return : Real; }
    calc def restrict_angle   { in theta : Real; return : Real; }

    // -----------------------------------------------------------------------
    // PendulumSimulation
    // Integrates the dynamics every 5 ms and publishes AngleReading on armPort.
    // Receives Control (latest arm torque) and stores it without re-sending
    // anything — this breaks the same-tag causality cycle.
    //
    // Two-state pattern for the timer step (single do per transition):
    //   running   → (timer, do assign x) → broadcasting
    //   broadcasting → (entry sends AngleReading) → running
    // -----------------------------------------------------------------------
    state def PendulumSimulation {
        attribute x : PendulumState;
        attribute latest_u : Real := 0.0;
        port armPort;

        entry; then running;

        state running;
        // Transient: sends the updated state as an AngleReading, then loops.
        state broadcasting {
            // Wrap theta into (-π, π] before sending so the controller
            // always sees a canonicalised angle (needed for swingUp guard).
            entry send new AngleReading(FurutaPendulum::restrict_angle(x.theta), x.d_theta, x.phi, x.d_phi) via armPort;
        }

        // --- timer self-loop: integrate physics ---
        transition first running
            accept after 0.005 [s]
            do assign x := FurutaPendulum::step(x, latest_u, 0.005)
            then broadcasting;

        // --- control input: store torque and return to running ---
        // Key design choice: broadcasting has NO completion transition.
        // broadcasting's ONLY exit is when Control arrives from the controller.
        //
        // Execution at tag T:
        //   1. broadcasting.startup fires: sends AngleReading (no reset(running))
        //   2. ctrl receives AngleReading, computes torque, outputs Control
        //   3. broadcasting.Control fires: stores latest_u, resets running
        //
        // This is a strict linear chain with no cycle. lfc accepts it.
        // On the very first iteration latest_u = 0.0 (declared above) so the
        // controller's first AngleReading immediately produces a Control reply.
        transition first broadcasting
            accept c : Control via armPort
            do assign latest_u := c.u
            then running;
    }

    // -----------------------------------------------------------------------
    // PendulumController
    // Three-mode modal controller: swingUp → catching → stabilizing.
    // Each mode uses a "send" transient state to decouple the torque assignment
    // (in the incoming transition effect) from the Control send (in entry),
    // since a single transition may carry only one do-action.
    //
    // Guard thresholds (from furuta_physics.py constants):
    //   REGION1 = 0.1   (|theta| < 0.1  → leave swingUp, enter catching)
    //   MAX_SPEED = 0.05 (|d_phi| < 0.05 → leave catching, enter stabilizing)
    //   REGION2 = 0.2   (|theta| > 0.2  → leave stabilizing, re-enter swingUp)
    // -----------------------------------------------------------------------
    state def PendulumController {
        attribute u : Real := 0.0;
        port armPort;
        port statusPort;

        entry; then swingUp;

        // --- stable waiting modes ---
        state swingUp;
        state catching;
        state stabilizing;

        // --- transient send states ---
        // Every exit from a waiting mode must send Control via armPort so the
        // simulator (stuck in `broadcasting`, waiting for Control) can advance.
        // Each send-state also sends any status signals needed for that branch.
        //
        // Naming: send<Source><Target> for guard branches; send<Mode> for
        // the default (torque-update) branches.

        // swingUp → sendSwingUp (default: compute new torque, then back to swingUp)
        state sendSwingUp {
            entry send new Control(u) via armPort;
        }
        // swingUp → sendSwingUpToCatching (guard: near top)
        state sendSwingUpToCatching {
            entry send new Control(u) via armPort;
        }

        // catching → sendCatching (default: compute new torque, then back to catching)
        state sendCatching {
            entry send new Control(u) via armPort;
        }
        // catching → sendCatchingToStabilizing (guard: balanced; Balanced sent in transition do)
        state sendCatchingToStabilizing {
            entry send new Control(u) via armPort;
        }
        // catching → sendCatchingToSwingUp (guard: pendulum dropped)
        state sendCatchingToSwingUp {
            entry send new Control(u) via armPort;
        }

        // stabilizing → sendStabilizing (default: compute new torque, back to stabilizing)
        state sendStabilizing {
            entry send new Control(u) via armPort;
        }
        // stabilizing → sendStabilizingToSwingUp (guard: pendulum fell)
        state sendStabilizingToSwingUp {
            entry send new Control(u) via armPort;
        }

        // =================================================================
        // swingUp transitions
        // =================================================================
        // Guard: near top → send current u, then switch to catching
        transition first swingUp
            accept r : AngleReading via armPort
            if abs(r.theta) < 0.1
            then sendSwingUpToCatching;
        transition first sendSwingUpToCatching then catching;

        // Default: compute swing-up torque, send, stay in swingUp
        transition first swingUp
            accept r : AngleReading via armPort
            do assign u := FurutaPendulum::swingup_torque(r)
            then sendSwingUp;
        transition first sendSwingUp then swingUp;

        // =================================================================
        // catching transitions
        // =================================================================
        // Guard: arm nearly stopped → announce Balanced (do), send u (entry), switch to stabilizing
        transition first catching
            accept r : AngleReading via armPort
            if abs(r.d_phi) < 0.05
            do send new Balanced() via statusPort
            then sendCatchingToStabilizing;
        transition first sendCatchingToStabilizing then stabilizing;

        // Guard: pendulum dropped → send u, back to swing-up
        transition first catching
            accept r : AngleReading via armPort
            if abs(r.theta) > 0.2
            then sendCatchingToSwingUp;
        transition first sendCatchingToSwingUp then swingUp;

        // Default: compute catch torque, send, stay in catching
        transition first catching
            accept r : AngleReading via armPort
            do assign u := FurutaPendulum::catch_torque(r)
            then sendCatching;
        transition first sendCatching then catching;

        // =================================================================
        // stabilizing transitions
        // =================================================================
        // Guard: pendulum fell → send u, back to swing-up
        transition first stabilizing
            accept r : AngleReading via armPort
            if abs(r.theta) > 0.2
            then sendStabilizingToSwingUp;
        transition first sendStabilizingToSwingUp then swingUp;

        // Default: compute stabilizing torque, send, stay in stabilizing
        transition first stabilizing
            accept r : AngleReading via armPort
            do assign u := FurutaPendulum::stabilize_torque(r)
            then sendStabilizing;
        transition first sendStabilizing then stabilizing;
    }

    // -----------------------------------------------------------------------
    // FurutaMonitor
    // Waits for Balanced (verdict passes, exit 0) or times out (verdict := 1,
    // constraint violated, exit 1).  15 s is generous for swing-up + catch +
    // stabilize (reference LF model stabilizes within ~3 s).
    // -----------------------------------------------------------------------
    state def FurutaMonitor {
        attribute verdict : Integer := 0;
        assert constraint testPassed { verdict == 0 }

        port statusPort;

        entry; then waiting;
        state waiting;
        state fail {
            entry assign verdict := 1;
        }

        transition first waiting accept Balanced via statusPort then done;
        transition first waiting accept after 15 [s] then fail;
        transition first fail then done;
    }

    // -----------------------------------------------------------------------
    // Part defs with ports
    // -----------------------------------------------------------------------
    part def PendulumSim {
        port armPort;
        exhibit state : PendulumSimulation;
    }

    part def Controller {
        port armPort;
        port statusPort;
        exhibit state : PendulumController;
    }

    part def Monitor {
        port statusPort;
        exhibit state : FurutaMonitor;
    }

    // -----------------------------------------------------------------------
    // Top-level part usage
    // -----------------------------------------------------------------------
    part furutaSystem {
        part sim  : PendulumSim;
        part ctrl : Controller;
        part mon  : Monitor;
        // AngleReading: sim→ctrl; Control: ctrl→sim (different names, no cycle)
        connect sim.armPort  to ctrl.armPort;
        // Balanced: ctrl→mon
        connect ctrl.statusPort to mon.statusPort;
    }
}
