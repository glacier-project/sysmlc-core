package FurutaPendulum {
    private import ScalarValues::*;
    private import NumericalFunctions::*;
    private import TrigFunctions::*;

    item def AngleReading {
        attribute theta : Real;
    }

    state def PendulumController {
        in attribute catchAngle : Real default 0.5;
        in attribute dropAngle : Real default 1.2;

        inout attribute energy : Real := 0.0;

        entry;
            then swingUp;

        state swingUp;
        state catching;
        state stabilizing;

        transition first swingUp
            accept reading : AngleReading
            if abs(reading.theta) < catchAngle
            then catching;
        transition first catching
            accept reading : AngleReading
            if abs(reading.theta) < catchAngle
            do assign energy := cos(reading.theta)
            then stabilizing;
        transition first catching
            accept reading : AngleReading
            if abs(reading.theta) >= catchAngle
            then swingUp;
        transition first stabilizing
            accept reading : AngleReading
            if abs(reading.theta) >= dropAngle
            then swingUp;
    }
}
