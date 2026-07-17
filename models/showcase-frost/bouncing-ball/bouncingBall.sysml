package BouncingBallFmu {
    doc /*
         * Scaffolded by `sysmlc frostifier extract-fmu` from
         * bouncingBall.fmu. Attribute names bind to FMU variable
         * names 1:1 — rename items, ports, and defs freely, but
         * keep the attribute names. Split the single in/out items
         * into semantically named signals as needed; readable
         * `local` variables are scaffolded as outputs — prune
         * the ones you don't need.
         */

    private import ScalarValues::*;
    private import FmuBinding::*;

    item def BouncingBallOutputs {
        attribute h : Real { doc /* height, used as state */ }
        attribute v : Real { doc /* velocity of ball, used as state */ }
    }

    port def BouncingBallPort {
        out item outputs : BouncingBallOutputs;
    }

    part def BouncingBall {
        metadata FmuImport {
            path = "bouncingBall.fmu";
            stepSize = 0.1;
            stopTime = 3.0;
            // Readable non-identifier variables: published
            // on the Frost data model (Exposed/), no signal.
            exposedVariables = ("der(h)", "der(v)");
        }
        // FMU parameters and exact-initial states; the
        // literal values are applied as startup values
        // inside initialization mode.
        attribute h : Real = 1.0 { doc /* height, used as state */ }
        attribute v : Real = 0.0 { doc /* velocity of ball, used as state */ }
        attribute g : Real = 9.81 { doc /* acceleration of gravity */ }
        attribute e : Real = 0.7 { doc /* dimensionless parameter */ }
        port fmuPort : BouncingBallPort;
    }uv aa

    // FMU-only network: the ball's readings stay unrouted (no composed
    // peer) and are observable over the Frost protocol instead.
    part bounceSystem {
        part ball : BouncingBall;
    }
}
