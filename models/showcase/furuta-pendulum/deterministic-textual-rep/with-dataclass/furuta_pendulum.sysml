// Quake variant of models/showcase/furuta-pendulum. Identical to that model
// except the controller's transitions carry complementary guards so exactly
// one is enabled per step (see the swingUp/catching/stabilizing branches).
// SysML leaves the selection among same-source enabled transitions undefined,
// so the showcase model runs only under LF's extra-spec declaration-order
// priority; these guards encode that same priority explicitly, making the
// model deterministic under any conformant tool (quake included). The
// companion furuta_physics.py here is self-contained (owns its dataclasses),
// so no generated types module is needed.
package FurutaPendulum {
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import SI::*;

    // -----------------------------------------------------------------------
    // Data types
    // -----------------------------------------------------------------------

    // Internal state type: composite attribute (attribute def so the backend
    // recognises it as a structured type and emits a PendulumState dataclass
    // into the generated furutaSystem_types companion module).
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
    // Pure functions implemented inline as Python textual representations.
    // The shared scaffolding (import, constants, private helpers) lives in
    // one rep on the package; each calc def carries only its own function.
    // -----------------------------------------------------------------------

    rep scaffolding language "Python"
        /*
         * import math
         * from dataclasses import dataclass
         *
         * @dataclass
         * class PendulumState:
         *     """Simulator state: pendulum and arm angles with their velocities."""
         *
         *     theta: float
         *     d_theta: float
         *     phi: float
         *     d_phi: float
         *
         * @dataclass
         * class AngleReading:
         *     """Sensor reading the simulator publishes to the controller."""
         *
         *     theta: float
         *     d_theta: float
         *     phi: float
         *     d_phi: float
         *
         * # Inertia / coupling coefficients (Liu et al. 2002 notation)
         * ALPHA = 0.00260569
         * BETA = 0.05165675
         * GAMMA = 9.7055e-4
         * EPSILON = 0.08103060
         *
         * # Gravitational acceleration [m/s^2]
         * G = 9.81
         *
         * # Natural frequency used in energy calculation
         * W0 = 6.3
         *
         * # Swing-up energy multiplier
         * K = 0.5
         *
         * # Swing-up control magnitude bound
         * N = 0.5
         *
         * # Catch-mode linear-feedback gains
         * CI1 = -1.04945717118225
         * CI2 = -0.20432286791216
         * CI3 = -0.00735846749875
         * CI4 = -0.00735846749875
         *
         * # Arm angle set-point used by Catch mode [rad]
         * PHI2 = -7.0124562
         *
         * # Stabilize-mode linear-feedback gains
         * SI1 = -1.70871686211144
         * SI2 = -0.30395427746831
         * SI3 = -0.03254225945714
         * SI4 = -0.05808270221773
         *
         * # Arm angle set-point used by Stabilize mode [rad]
         * PHI0 = 0.0
         *
         * def _sign(x):
         *     return float((x > 0.0) - (x < 0.0))
         *
         * def _energy(theta, d_theta):
         *     return 0.5 * d_theta * d_theta / (W0 * W0) + math.cos(theta) - 1.0
         */

    calc def step             {
        in x : PendulumState;
        in u : Real;
        in dt : Real;
        return : PendulumState;

        rep impl language "Python"
            /*
             * def step(x, u, dt):
             *
             *     x0 = x.theta
             *     x1 = x.d_theta
             *     x3 = x.d_phi
             *
             *     sin0 = math.sin(x0)
             *     cos0 = math.cos(x0)
             *
             *     # Common denominator
             *     denom = ALPHA * BETA + (ALPHA * sin0) ** 2 - (GAMMA * cos0) ** 2
             *
             *     ab_asq = ALPHA * BETA + (ALPHA * sin0) ** 2
             *
             *     x0_dot = x1
             *
             *     x1_dot = (1.0 / denom) * (
             *         ab_asq * (x3 ** 2) * sin0 * cos0
             *         - (GAMMA * x1) ** 2 * sin0 * cos0
             *         + 2.0 * ALPHA * GAMMA * x1 * x3 * sin0 * (cos0 ** 2)
             *         - GAMMA * cos0 * G * u
             *         + ab_asq * EPSILON / ALPHA * sin0
             *     )
             *
             *     x2_dot = x3
             *
             *     # NOTE: the original LF source used cos(d_theta) here, a transcription
             *     # error. Corrected to cos(theta) = cos0, matching the standard Furuta
             *     # derivation and the Ptolemy II reference model.
             *     x3_dot = (1.0 / denom) * (
             *         -GAMMA * ALPHA * (x3 ** 2) * sin0 * (cos0 ** 2)
             *         - GAMMA * EPSILON * sin0 * cos0
             *         + GAMMA * ALPHA * (x1 ** 2) * sin0
             *         - 2.0 * (ALPHA ** 2) * x1 * x3 * sin0 * cos0
             *         + ALPHA * G * u
             *     )
             *
             *     return PendulumState(
             *         theta=x.theta + x0_dot * dt,
             *         d_theta=x.d_theta + x1_dot * dt,
             *         phi=x.phi + x2_dot * dt,
             *         d_phi=x.d_phi + x3_dot * dt,
             *     )
             */
    }

    calc def swingup_torque {
        in r : AngleReading;
        return : Real;

        rep impl language "Python"
            /*
             * def swingup_torque(r):
             *     th = restrict_angle(r.theta)
             *     e = _energy(th, r.d_theta)
             *     c = _sign(r.d_theta * math.cos(th))
             *     return _sign(e) * min(math.fabs(K * e), N) * c
             */
    }

    calc def catch_torque {
        in r : AngleReading;
        return : Real;

        rep impl language "Python"
            /*
             * def catch_torque(r):
             *     th = restrict_angle(r.theta)
             *     return -1.0 * (
             *         th * CI1 + r.d_theta * CI2 + (r.phi - PHI2) * CI3 + r.d_phi * CI4
             *     )
             */
    }

    calc def stabilize_torque {
        in r : AngleReading;
        return : Real;

        rep impl language "Python"
            /*
             * def stabilize_torque(r):
             *     th = restrict_angle(r.theta)
             *     return -1.0 * (
             *         th * SI1 + r.d_theta * SI2 + (r.phi - PHI0) * SI3 + r.d_phi * SI4
             *     )
             */
    }

    calc def restrict_angle {
        in theta : Real;
        return : Real;

        rep impl language "Python"
            /*
             * def restrict_angle(theta):
             *     pi = math.pi
             *     return (math.fmod(math.fabs(theta) + pi, 2 * pi) - pi) * _sign(theta)
             */
    }

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

        // Complement of the guard above: not near the top, so compute
        // swing-up torque, send, stay in swingUp
        transition first swingUp
            accept r : AngleReading via armPort
            if abs(r.theta) >= 0.1
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

        // Guard: pendulum dropped, and arm not yet stopped so this yields
        // to the transition above → send u, back to swing-up
        transition first catching
            accept r : AngleReading via armPort
            if abs(r.theta) > 0.2 and abs(r.d_phi) >= 0.05
            then sendCatchingToSwingUp;
        transition first sendCatchingToSwingUp then swingUp;

        // Complement of the two guards above: arm still moving and pendulum
        // near the top, so compute catch torque, send, stay in catching
        transition first catching
            accept r : AngleReading via armPort
            if abs(r.d_phi) >= 0.05 and abs(r.theta) <= 0.2
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

        // Complement of the guard above: pendulum still near the top, so
        // compute stabilizing torque, send, stay in stabilizing
        transition first stabilizing
            accept r : AngleReading via armPort
            if abs(r.theta) <= 0.2
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
