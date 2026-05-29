package SM05 {
    private import ScalarValues::*;

    attribute def Point {
        attribute x : Real = 0.5;
    }

    attribute def Inner {
        attribute z : Real = 0.25;
    }

    attribute def Box {
        attribute inner : Inner;
    }

    state def MachineChainGuard {
        attribute pt : Point;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if pt.x > 0.0 then running;
    }

    state def MachineChainNested {
        attribute box : Box;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle if box.inner.z > 0.0 then running;
    }

    state def MachineChainAssign {
        attribute pt : Point;
        attribute reached : Real := 0.0;
        entry;
            then idle;
        state idle {
            entry assign reached := pt.x;
        }
        state running;
        transition first idle then running;
    }
}
