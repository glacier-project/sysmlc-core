#include "statix_extern.h"
#include "furuta_pendulum/pendulum_controller.h"
#include "furuta_pendulum/pendulum_simulation.h"
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ---------------------------------------------------------------------------
 * Physical / integration constants
 * --------------------------------------------------------------------------- */
static const double G = 9.81;
static const double ALPHA = 0.00260569;
static const double BETA = 0.05165675;
static const double GAMMA = 9.7055e-4;
static const double EPSILON = 0.08103060;

/* ---------------------------------------------------------------------------
 * Controller constants
 * --------------------------------------------------------------------------- */
static const double W0 = 6.3;
static const double K = 0.5;
static const double N = 0.5;

static const double CI1 = -1.04945717118225;
static const double CI2 = -0.20432286791216;
static const double CI3 = -0.00735846749875;
static const double CI4 = -0.00735846749875;

static const double SI1 = -1.70871686211144;
static const double SI2 = -0.30395427746831;
static const double SI3 = -0.03254225945714;
static const double SI4 = -0.05808270221773;

static const double PHI2 = -7.0124562;
static const double PHI0 = 0.0;

/* ---------------------------------------------------------------------------
 * Private helpers
 * --------------------------------------------------------------------------- */
static double _sign(double x)
{
    return (double)((x > 0.0) - (x < 0.0));
}

static double restrict_angle(double theta)
{
    return (fmod(fabs(theta) + M_PI, 2.0 * M_PI) - M_PI) * _sign(theta);
}

static double _energy(double theta, double d_theta)
{
    return 0.5 * d_theta * d_theta / (W0 * W0) + cos(theta) - 1.0;
}

/* ---------------------------------------------------------------------------
 * Public API / Extern Implementations
 * --------------------------------------------------------------------------- */

/* FurutaPendulum::step */
furuta_pendulum_pendulum_simulation_pendulum_state_t furuta_pendulum_step(
    furuta_pendulum_pendulum_simulation_pendulum_state_t x,
    double u,
    double dt)
{
    double x0 = x.theta;
    double x1 = x.d_theta;
    double x3 = x.d_phi;

    double sin0 = sin(x0);
    double cos0 = cos(x0);

    /* Common denominator */
    double denom = ALPHA * BETA + pow(ALPHA * sin0, 2.0) - pow(GAMMA * cos0, 2.0);
    double ab_asq = ALPHA * BETA + pow(ALPHA * sin0, 2.0);

    double x0_dot = x1;
    double x1_dot = (1.0 / denom) * (
        ab_asq * (x3 * x3) * sin0 * cos0
        - pow(GAMMA * x1, 2.0) * sin0 * cos0
        + 2.0 * ALPHA * GAMMA * x1 * x3 * sin0 * (cos0 * cos0)
        - GAMMA * cos0 * G * u
        + ab_asq * EPSILON / ALPHA * sin0
    );

    double x2_dot = x3;
    double x3_dot = (1.0 / denom) * (
        -GAMMA * ALPHA * (x3 * x3) * sin0 * (cos0 * cos0)
        - GAMMA * EPSILON * sin0 * cos0
        + GAMMA * ALPHA * (x1 * x1) * sin0
        - 2.0 * (ALPHA * ALPHA) * x1 * x3 * sin0 * cos0
        + ALPHA * G * u
    );

    furuta_pendulum_pendulum_simulation_pendulum_state_t next_x;
    next_x.theta = x.theta + x0_dot * dt;
    next_x.d_theta = x.d_theta + x1_dot * dt;
    next_x.phi = x.phi + x2_dot * dt;
    next_x.d_phi = x.d_phi + x3_dot * dt;
    return next_x;
}

/* FurutaPendulum::swingup_torque */
double furuta_pendulum_swingup_torque(furuta_pendulum_pendulum_controller_angle_reading_t r)
{
    double th = restrict_angle(r.theta);
    double e = _energy(th, r.d_theta);
    double c = _sign(r.d_theta * cos(th));
    double val = fabs(K * e);
    double limit_val = val < N ? val : N;
    return _sign(e) * limit_val * c;
}

/* FurutaPendulum::catch_torque */
double furuta_pendulum_catch_torque(furuta_pendulum_pendulum_controller_angle_reading_t r)
{
    double th = restrict_angle(r.theta);
    return -1.0 * (th * CI1 + r.d_theta * CI2 + (r.phi - PHI2) * CI3 + r.d_phi * CI4);
}

/* FurutaPendulum::stabilize_torque */
double furuta_pendulum_stabilize_torque(furuta_pendulum_pendulum_controller_angle_reading_t r)
{
    double th = restrict_angle(r.theta);
    return -1.0 * (th * SI1 + r.d_theta * SI2 + (r.phi - PHI0) * SI3 + r.d_phi * SI4);
}
