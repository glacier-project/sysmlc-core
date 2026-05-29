package SM03 {
    private import ScalarValues::*;

    state def MachineLiteralTrue {
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if true then running;
    }

    state def MachineLiteralFalse {
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if false then running;
    }

    state def MachineRef {
        attribute enabled : Boolean := true;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if enabled then running;
    }

    state def MachineNot {
        attribute enabled : Boolean := false;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if not enabled then running;
    }

    state def MachineUnaryMinus {
        attribute x : Integer := 1;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if -x < 0 then running;
    }

    state def MachineAnd {
        attribute a : Boolean := true;
        attribute b : Boolean := true;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if a and b then running;
    }

    state def MachineOr {
        attribute a : Boolean := true;
        attribute b : Boolean := false;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if a or b then running;
    }

    state def MachineEq {
        attribute x : Integer := 1;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x == 1 then running;
    }

    state def MachineNeq {
        attribute x : Integer := 1;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x != 0 then running;
    }

    state def MachineLt {
        attribute x : Integer := 1;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x < 2 then running;
    }

    state def MachineLe {
        attribute x : Integer := 1;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x <= 1 then running;
    }

    state def MachineGt {
        attribute x : Integer := 1;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x > 0 then running;
    }

    state def MachineGe {
        attribute x : Integer := 1;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x >= 1 then running;
    }

    state def MachineArithPlus {
        attribute x : Integer := 1;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x + 1 > 1 then running;
    }

    state def MachineArithMinus {
        attribute x : Integer := 2;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x - 1 > 0 then running;
    }

    state def MachineArithMul {
        attribute x : Integer := 2;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x * 2 > 1 then running;
    }

    state def MachineArithDiv {
        attribute x : Integer := 4;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x / 2 > 1 then running;
    }

    state def MachineRealLiteral {
        attribute x : Real := 1.0;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x > 0.5 then running;
    }

    state def MachineLogicalChain {
        attribute a : Boolean := true;
        attribute b : Boolean := true;
        attribute c : Boolean := false;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if a and b or c then running;
    }

    state def MachineLowerPrecLhs {
        attribute a : Boolean := true;
        attribute b : Boolean := false;
        attribute c : Boolean := true;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if (a or b) and c then running;
    }

    state def MachineLeftAssocRhs {
        attribute x : Integer := 5;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if x - (1 - 2) > 0 then running;
    }
}
