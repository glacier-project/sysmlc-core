package ShapeCheckCellFmu {
    doc /* Scaffolded by `sysmlc frostifier extract-fmu` from
         * ShapeCheckCell.fmu. Attribute names bind to FMU variable
         * names 1:1 — rename items, ports, and defs freely, but
         * keep the attribute names. Split the single in/out items
         * into semantically named signals as needed; readable
         * `local` variables are scaffolded as outputs — prune
         * the ones you don't need.
         */

    private import ScalarValues::*;
    private import FmuBinding::*;

    item def ShapeCheckCellInputs {
        attribute shape1 : Integer = 0;
        attribute shape2 : Integer = 0;
        attribute shape3 : Integer = 0;
        attribute pallet_position_1 : Integer = 0;
        attribute pallet_position_2 : Integer = 0;
        attribute pallet_position_3 : Integer = 0;
    }

    item def ShapeCheckCellOutputs {
        attribute result : Boolean;
    }

    port def ShapeCheckCellPort {
        out item outputs : ShapeCheckCellOutputs;
        in item inputs : ShapeCheckCellInputs;
    }

    part def ShapeCheckCell {
        metadata FmuImport {
            path = "ShapeCheckCell.fmu";
            // TODO stepSize = ...; (seconds — the archive has no DefaultExperiment stepSize to fall back to)
        }
        port fmuPort : ShapeCheckCellPort;
    }
}
