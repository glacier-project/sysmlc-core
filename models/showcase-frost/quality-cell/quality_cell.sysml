package QualityCell {
    doc /* A quality-control station: the Cell state machine is the
         * interface between the plant simulation (the ice-fmi
         * QualityCell FMU, FMI 3.0 — a shape/pallet matcher whose
         * String verdict is "success"/"failed"/"none"/"error") and
         * the outside world.
         *
         * The outside is not modeled here — the Cell's extPort is left
         * unconnected: the Cell reports its verdict through it and
         * would accept an Abort from it, but no peer is composed. Only
         * the FMU side is wired.
         */

    private import ScalarValues::*;
    private import SI::*;
    private import FmuBinding::*;

    // Payload attribute names bind to the FMU's variable names 1:1.
    item def ShapeCheck {
        attribute shape1 : Integer;
        attribute shape2 : Integer;
        attribute shape3 : Integer;
        attribute pallet_position_1 : Integer;
        attribute pallet_position_2 : Integer;
        attribute pallet_position_3 : Integer;
    }
    item def Verdict { attribute result : String; }

    // Outside-facing signals (the outside itself is not modeled).
    item def CheckReport { attribute ok : Boolean; }
    item def Abort;

    // The FMU's signal surface: what it emits each communication point
    // (out) and what sets its inputs (in).
    port def SimPort {
        out item verdict : Verdict;
        in item check : ShapeCheck;
    }

    // The plant simulation, realized by the FMU archive; it emits a
    // Verdict at every 100 ms communication point.
    part def CellSim {
        metadata FmuImport {
            path = "QualityCell.fmu";
            stepSize = 0.1;
        }
        port simPort : SimPort;
    }

    // The Cell: mediates between the simulation and the outside.
    // Commands the FMU over simPort; reports (and would accept an
    // Abort) over extPort.
    state def CellBehavior {
        port simPort;
        port extPort;

        entry; then dispatching;

        state dispatching;
        state waiting;
        state passed;
        state aborted;

        // Dispatch one matching check to the simulation after startup.
        transition first dispatching
            accept after 0.05 [s]
            do send new ShapeCheck(1, 2, 3, 1, 2, 3) via simPort
            then waiting;

        // The sim reports every step ("none" until a check ran); wait
        // for a passing verdict, then report the outcome to the outside.
        transition first waiting
            accept v : Verdict via simPort
            if v.result == "success"
            do send new CheckReport(true) via extPort
            then passed;

        // The outside may abort a running check (never happens here).
        transition first waiting
            accept Abort via extPort
            then aborted;

        transition first passed then done;
        transition first aborted then done;
    }
    part def Cell {
        port simPort;
        port extPort;
        exhibit state : CellBehavior;
    }

    part qualityStation {
        part sim : CellSim;
        part cell : Cell;
        connect sim.simPort to cell.simPort;
    }
}
