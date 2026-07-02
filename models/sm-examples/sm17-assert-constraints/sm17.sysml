package SM17 {
    private import ScalarValues::*;
    private import TrigFunctions::*;

    item def Tick;

    state def MachineScoped {
        attribute level : Real := 1.0;
        assert constraint positive { level > 0.0 }

        entry; then idle;
        state idle {
            assert constraint capped { level <= 2.0 }
        }
    }

    state def MachineCounterLimit {
        attribute counter : Integer := 0;
        attribute maxCount : Integer := 1;
        assert constraint belowLimit { counter <= maxCount }

        entry; then idle;
        state idle;
        transition first idle accept Tick
            do assign counter := counter + 1
            then idle;
    }

    state def MachineNegated {
        attribute level : Real := 1.0;
        assert not constraint tooHigh { level > 2.0 }

        entry; then idle;
        state idle;
        transition first idle accept Tick do assign level := 3.0 then idle;
    }

    state def MachineFunctionViolation {
        attribute x : Real := 3.2;
        assert constraint cosineNonPositive {
            TrigFunctions::cos(x) <= 0.0
        }

        entry; then idle;
        state idle;
        state running;
        transition first idle accept Tick do assign x := 0.0 then running;
    }
}
