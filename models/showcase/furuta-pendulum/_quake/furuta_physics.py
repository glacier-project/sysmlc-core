"""Pure forward-Euler physics for the Furuta pendulum showcase.

Ported faithfully from the lf-lang playground at commit e2f5b35:
  examples/C/src/modal_models/FurutaPendulum/PendulumSimulation.lf
  examples/C/src/modal_models/FurutaPendulum/PendulumController.lf

Reference paper:
  J. Liu, J. Eker, J. W. Janneck, and E. A. Lee, "Realistic simulations of
  embedded control systems," IFAC Proceedings Volumes, vol. 35, no. 1,
  pp. 391-396, 2002.  (Ptolemy II model by Johan Eker.)

State convention (matches the LF reference):
  theta   - pendulum angle; 0 = straight up (inverted equilibrium)
  d_theta - pendulum angular velocity
  phi     - horizontal arm angle
  d_phi   - arm angular velocity

This is the quake variant of the parent folder's `furuta_physics.py`. It
differs in one respect: it defines `PendulumState` and `AngleReading` as local
dataclasses instead of importing them from a generated `furutaSystem_types`
companion. The quake backend runs the statechart in-process, so nothing
generates that companion; owning the types keeps this module self-contained.
  `step` receives a `PendulumState` and returns a new `PendulumState`.
  The torque functions receive an `AngleReading`.
Neither function mutates its input.

Port subtlety — x3_dot bug in the LF source
--------------------------------------------
In PendulumSimulation.lf the first term of x3_dot contains
``pow(cos(self->x[1]), 2.0)`` where x[1] is d_theta (angular velocity).
Physically that term must be ``cos(theta)^2``; using cos(d_theta) would
mix radians of angle with rad/s and break dimensional consistency.  The
Ptolemy II original (Liu et al. 2002) and the standard Furuta derivation
both use cos(theta).  This is a transcription error in the LF port.
We correct it here: ``cos(x[0])`` = ``cos(theta)``.
A comment marks exactly where the fix is applied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PendulumState:
    """Simulator state: pendulum and arm angles with their velocities."""

    theta: float
    d_theta: float
    phi: float
    d_phi: float


@dataclass
class AngleReading:
    """Sensor reading the simulator publishes to the controller."""

    theta: float
    d_theta: float
    phi: float
    d_phi: float


# ---------------------------------------------------------------------------
# Physical / integration constants (from PendulumSimulation.lf)
# ---------------------------------------------------------------------------

#: Gravitational acceleration [m/s²]
G: float = 9.81

#: Inertia / coupling coefficients (Liu et al. 2002 notation)
ALPHA: float = 0.00260569
BETA: float = 0.05165675
GAMMA: float = 9.7055e-4
EPSILON: float = 0.08103060

#: Default forward-Euler step size [s] (== sample_period in the LF reactor)
H: float = 0.005

# ---------------------------------------------------------------------------
# Controller constants (from PendulumController.lf)
# ---------------------------------------------------------------------------

#: Natural frequency used in energy calculation
W0: float = 6.3

#: Swing-up energy multiplier
K: float = 0.5

#: Swing-up control magnitude bound
N: float = 0.5

#: |theta| threshold to leave SwingUp → Catch  [rad]
REGION1: float = 0.1

#: |theta| threshold to leave Stabilize → SwingUp  [rad]
REGION2: float = 0.2

#: |d_phi| threshold to leave Catch → Stabilize  [rad/s]
MAX_SPEED: float = 0.05

# Catch-mode linear-feedback gains  (ci1..ci4 in PendulumController.lf)
CI1: float = -1.04945717118225
CI2: float = -0.20432286791216
CI3: float = -0.00735846749875
CI4: float = -0.00735846749875

# Stabilize-mode linear-feedback gains  (si1..si4 in PendulumController.lf)
SI1: float = -1.70871686211144
SI2: float = -0.30395427746831
SI3: float = -0.03254225945714
SI4: float = -0.05808270221773

#: Arm angle set-point used by Catch mode [rad] (phi2 in PendulumController.lf)
PHI2: float = -7.0124562

#: Arm angle set-point used by Stabilize mode; updated at mode entry in LF.
#: Module-level default matches the LF reactor state initialiser (phi0 = 0.0).
PHI0: float = 0.0


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _sign(x: float) -> float:
    """Return the sign of x as -1.0, 0.0, or 1.0."""
    return float((x > 0.0) - (x < 0.0))


def _energy(theta: float, d_theta: float) -> float:
    """Mechanical energy proxy used by SwingUp and catch/stabilize modes.

    From PendulumController.lf::
        E = 0.5 * d_theta^2 / w0^2 + cos(th) - 1.0
    """
    return 0.5 * d_theta * d_theta / (W0 * W0) + math.cos(theta) - 1.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def restrict_angle(theta: float) -> float:
    """Wrap *theta* into (-pi, pi].

    Faithful port of ``restrictAngle`` from PendulumController.lf::

        return (fmod(fabs(theta) + PI, 2*PI) - PI) * sign(theta);
    """
    pi = math.pi
    return (math.fmod(math.fabs(theta) + pi, 2 * pi) - pi) * _sign(theta)


def step(x: PendulumState, u: float, dt: float) -> PendulumState:
    """One forward-Euler integration step of the Furuta pendulum dynamics.

    Integrates the equations of motion under arm torque *u* for a time
    interval *dt* seconds.  Returns a **new** ``PendulumState`` with
    attributes ``theta``, ``d_theta``, ``phi``, ``d_phi``.  The input
    object *x* is never mutated.

    Equations ported verbatim from PendulumSimulation.lf (reaction on
    timer ``t``), except the ``cos(x[1])`` → ``cos(x[0])`` fix noted in
    the module docstring.

    Reference C expressions (x0=theta, x1=d_theta, x2=phi, x3=d_phi)::

        D = alpha*beta + (alpha*sin(x0))^2 - (gamma*cos(x0))^2

        x0_dot = x1

        x1_dot = (1/D) * (
              (alpha*beta + (alpha*sin(x0))^2) * x3^2 * sin(x0)*cos(x0)
            - (gamma*x1)^2 * sin(x0)*cos(x0)
            + 2*alpha*gamma * x1*x3 * sin(x0)*cos(x0)^2
            - gamma*cos(x0) * g * u          # torque term
            + (alpha*beta + (alpha*sin(x0))^2) * epsilon/alpha * sin(x0)
        )

        x2_dot = x3

        x3_dot = (1/D) * (
            - gamma*alpha * x3^2 * sin(x0)*cos(x0)^2   # ← LF had cos(x1); fixed
            - gamma*epsilon * sin(x0)*cos(x0)
            + gamma*alpha * x1^2 * sin(x0)
            - 2*alpha^2 * x1*x3 * sin(x0)*cos(x0)
            + alpha*g*u
        )

    Args:
        x:  ``PendulumState`` with float attributes ``theta``, ``d_theta``,
            ``phi``, ``d_phi``.
        u:  Arm torque input [N·m].
        dt: Integration step size [s].

    Returns:
        New ``PendulumState(theta, d_theta, phi, d_phi)``.
    """
    x0 = x.theta
    x1 = x.d_theta
    x3 = x.d_phi

    sin0 = math.sin(x0)
    cos0 = math.cos(x0)

    # Common denominator
    denom = ALPHA * BETA + (ALPHA * sin0) ** 2 - (GAMMA * cos0) ** 2

    ab_asq = ALPHA * BETA + (ALPHA * sin0) ** 2  # (alpha*beta + (alpha*sin θ)²)

    x0_dot = x1

    x1_dot = (1.0 / denom) * (
        ab_asq * (x3**2) * sin0 * cos0
        - (GAMMA * x1) ** 2 * sin0 * cos0
        + 2.0 * ALPHA * GAMMA * x1 * x3 * sin0 * (cos0**2)
        - GAMMA * cos0 * G * u
        + ab_asq * EPSILON / ALPHA * sin0
    )

    x2_dot = x3

    x3_dot = (1.0 / denom) * (
        # NOTE: LF source had cos(x[1]) here (i.e. cos(d_theta)), which is a
        # transcription error.  Corrected to cos(x[0]) = cos(theta).
        -GAMMA * ALPHA * (x3**2) * sin0 * (cos0**2)
        - GAMMA * EPSILON * sin0 * cos0
        + GAMMA * ALPHA * (x1**2) * sin0
        - 2.0 * (ALPHA**2) * x1 * x3 * sin0 * cos0
        + ALPHA * G * u
    )

    return PendulumState(
        theta=x.theta + x0_dot * dt,
        d_theta=x.d_theta + x1_dot * dt,
        phi=x.phi + x2_dot * dt,
        d_phi=x.d_phi + x3_dot * dt,
    )


def swingup_torque(r: AngleReading) -> float:
    """Energy-pumping swing-up control torque.

    Ported from ``PendulumController.lf`` SwingUp mode::

        th  = restrictAngle(theta)
        E   = 0.5 * d_theta^2 / w0^2 + cos(th) - 1.0
        c   = sign(d_theta * cos(th))
        out = sign(E) * MIN(|k*E|, n) * c

    Args:
        r: ``AngleReading`` with ``theta`` and ``d_theta`` attributes.

    Returns:
        Swing-up control torque [N·m].
    """
    th = restrict_angle(r.theta)
    e = _energy(th, r.d_theta)
    c = _sign(r.d_theta * math.cos(th))
    return _sign(e) * min(math.fabs(K * e), N) * c


def catch_torque(r: AngleReading, phi2: float = PHI2) -> float:
    """Linear-feedback catch control torque.

    Ported from ``PendulumController.lf`` Catch mode::

        th  = restrictAngle(theta)
        out = -(th*ci1 + d_theta*ci2 + (phi - phi2)*ci3 + d_phi*ci4)

    Args:
        r:    ``AngleReading`` with ``theta``, ``d_theta``, ``phi``, ``d_phi``.
        phi2: Arm angle reference for Catch mode (default: PHI2 = -7.0124562).

    Returns:
        Catch control torque [N·m].
    """
    th = restrict_angle(r.theta)
    return -1.0 * (
        th * CI1 + r.d_theta * CI2 + (r.phi - phi2) * CI3 + r.d_phi * CI4
    )


def stabilize_torque(r: AngleReading, phi0: float = PHI0) -> float:
    """Inverted-balance control torque.

    Ported from ``PendulumController.lf`` Stabilize mode::

        th  = restrictAngle(theta)
        out = -(th*si1 + d_theta*si2 + (phi - phi0)*si3 + d_phi*si4)

    Args:
        r:    ``AngleReading`` with ``theta``, ``d_theta``, ``phi``, ``d_phi``.
        phi0: Arm angle reference captured at Stabilize entry
              (default: PHI0 = 0.0, the LF state initialiser).

    Returns:
        Stabilize control torque [N·m].
    """
    th = restrict_angle(r.theta)
    return -1.0 * (
        th * SI1 + r.d_theta * SI2 + (r.phi - phi0) * SI3 + r.d_phi * SI4
    )
