package SM06 {
    private import ScalarValues::*;

    state def MachineEffect {
        attribute counter : Integer := 0;
        entry;
            then idle;
        state idle;
        state armed;
        state running;
        transition first idle
        do action {
            assign counter := counter + 1;
        }
        then armed;
        transition first armed then running;
    }

    state def MachineEffectMulti {
        attribute a : Integer := 0;
        attribute b : Integer := 0;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle
        do action {
            assign a := 1;
            assign b := a + 2;
        }
        then running;
    }
}
