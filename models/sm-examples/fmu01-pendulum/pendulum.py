"""A damped pendulum FMU (FMI 3.0 co-simulation), built with pythonfmu3.

Rebuild the archive beside this file with:
    uvx --from pythonfmu3 pythonfmu3 build -f pendulum.py -d .
"""

import math

from pythonfmu3 import Fmi3Causality, Fmi3Slave, Float64


class Pendulum(Fmi3Slave):
    description = "A damped pendulum driven by a torque input"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theta = 0.5
        self.d_theta = 0.0
        self.u = 0.0
        self.register_variable(
            Float64("theta", causality=Fmi3Causality.output)
        )
        self.register_variable(
            Float64("d_theta", causality=Fmi3Causality.output)
        )
        self.register_variable(
            Float64("u", causality=Fmi3Causality.input, start=0.0)
        )

    def do_step(self, current_time, step_size):
        # gravity/length 9.81/0.5, viscous damping 0.2, torque input u.
        dd_theta = -19.62 * math.sin(self.theta) - 0.2 * self.d_theta + self.u
        self.d_theta += step_size * dd_theta
        self.theta += step_size * self.d_theta
        return True
