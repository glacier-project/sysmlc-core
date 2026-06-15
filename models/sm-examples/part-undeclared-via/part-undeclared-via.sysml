// The behavior accepts `via wire`, but the part def declares no such port.
// SysML-correct strict validation must reject this (the inlined machine's
// `via` ports must resolve against the part def's declared ports, §5.2).
package PartUV {
    item def Ping;

    state def Beh {
        port wire;
        entry; then s;
        state s;
        state t;
        transition first s accept Ping via wire then t;
    }

    part def P { exhibit state : Beh; }   // no `port wire` declared

    part sys {
        part p : P;
    }
}
