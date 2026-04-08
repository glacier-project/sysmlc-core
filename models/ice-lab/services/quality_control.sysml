package QualityControl {
    doc /* Vision-based quality inspection services (Cell 5, equipment ID: qualityControl).*/

    private import ScalarValues::*;
    private import EquipmentInterfaces::*;
    private import RecipePrimitives::*;

    action def CheckQualityCovers :> MachineService {
        doc /* Inspect assembled covers against an expected color.

             The vision system photographs the product and compares the detected
             cover color to the expected value.

             Args:
               equipment: The quality control equipment instance.
               color: Expected color string (e.g. "red", "blue", "green").

             Returns:
               result: true if the detected color matches, false otherwise.
             */

        in ref equipment : QualityControlEquipment;
        in color : String;
        out result : Boolean;

        first start;

        then action callCheck :> equipment.checkQualityCovers {
            in :>> color = CheckQualityCovers::color;
        }

        then done;

        bind result = callCheck.result;
    }

    action def CheckQualityLego :> MachineService {
        doc /* Inspect a Lego brick assembly against expected shape codes.

             The vision system verifies that the bricks at pallet positions 1-3
             match the expected shape identifiers.

             Args:
               equipment: The quality control equipment instance.
               shape1: Expected brick shape code at pallet position 1.
               shape2: Expected brick shape code at pallet position 2.
               shape3: Expected brick shape code at pallet position 3.

             Returns:
               result: true if all three positions match, false otherwise.
             */

        in ref equipment : QualityControlEquipment;
        in shape1 : Integer;
        in shape2 : Integer;
        in shape3 : Integer;
        out result : Boolean;

        first start;

        then action callCheck :> equipment.checkQualityLego {
            in :>> shape1 = CheckQualityLego::shape1;
            in :>> shape2 = CheckQualityLego::shape2;
            in :>> shape3 = CheckQualityLego::shape3;
        }

        then done;

        bind result = callCheck.result;
    }
}
