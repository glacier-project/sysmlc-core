package QualityCellFmu {
    doc /*
         * Scaffolded by `sysmlc frostifier extract-fmu` from
         * QualityCell.fmu. Attribute names bind to FMU variable
         * names 1:1 — rename items, ports, and defs freely, but
         * keep the attribute names. Split the single in/out items
         * into semantically named signals as needed; readable
         * `local` variables are scaffolded as outputs — prune
         * the ones you don't need.
         */

    private import ScalarValues::*;
    private import FmuBinding::*;

    item def QualityCellInputs {
        attribute quality_input : String = "";
        attribute shape1 : Integer = 0;
        attribute shape2 : Integer = 0;
        attribute shape3 : Integer = 0;
        attribute pallet_position_1 : Integer = 0;
        attribute pallet_position_2 : Integer = 0;
        attribute pallet_position_3 : Integer = 0;
    }

    item def QualityCellOutputs {
        attribute target_time : Real;
        attribute result : String;
        attribute error : Boolean;
    }

    port def QualityCellPort {
        out item outputs : QualityCellOutputs;
        in item inputs : QualityCellInputs;
    }

    part def QualityCell {
        metadata FmuImport {
            path = "QualityCell.fmu";
            // TODO stepSize = ...; (seconds — the archive has no DefaultExperiment stepSize to fall back to)
        }
        // FMU parameters and exact-initial states; the
        // literal values are applied as startup values
        // inside initialization mode.
        attribute target_time : Real = -1.0;
        port fmuPort : QualityCellPort;
    }
}
