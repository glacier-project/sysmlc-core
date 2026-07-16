package FMU01 {
    doc /* A pendulum plant (an imported FMI 3.0 FMU) stabilized by a
         * Controller state machine: the FMU publishes an AngleReading
         * every 5 ms communication point, the controller answers with
         * a Control command over the same connection.
         */

    private import ScalarValues::*;
    private import FmuBinding::*;

    item def AngleReading {
        attribute theta : Real;
        attribute d_theta : Real;
    }
    item def Control { attribute u : Real; }

    port def ArmPort {
        out item reading : AngleReading;
        in item control : Control;
    }

    part def Pendulum {
        metadata FmuImport {
            path = "pendulum.fmu";
            stepSize = 0.005;
        }
        port armPort : ArmPort;
    }

    state def ControllerBehavior {
        port ctrlPort;

        entry; then observing;

        state observing;
        state steadied;

        transition first observing
            accept r : AngleReading via ctrlPort
            do send new Control(0.0) via ctrlPort
            then steadied;

        transition first steadied then done;
    }
    part def Controller {
        port ctrlPort;
        exhibit state : ControllerBehavior;
    }

    part pendulumSystem {
        part pendulum : Pendulum;
        part controller : Controller;
        connect pendulum.armPort to controller.ctrlPort;
    }
}
