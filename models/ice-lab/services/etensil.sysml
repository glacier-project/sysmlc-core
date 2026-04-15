package ETensil {
    doc /* Electric screwdriver services (equipment ID: eTensil).*/

    private import ScalarValues::*;
    private import EquipmentInterfaces::*;
    private import RecipePrimitives::*;

    action def EtensilDoSingleScrew :> MachineService {
        doc /* Drive a single screw to torque specification.

             Invokes the doSingleScrew method, then waits until the
             screwdriver finishes (busy == false).

             Args:
               equipment: The eTensil equipment instance.

             Returns:
               actionDone: true if the PLC accepted the command.
             */

        in ref equipment : ETensilEquipment;
        out actionDone : Boolean;

        first start;

        then perform action callDoSingleScrew references equipment.doSingleScrew;

        then mWaitDone;
        merge mWaitDone;
        then decide;
            if equipment.busy == false then afterWait;
            else mWaitDone;

        action afterWait;
        then done;

        bind actionDone = callDoSingleScrew.accepted;
    }

    action def EtensilDoUntight :> MachineService {
        doc /* Reverse-drive (unscrew) for a specified duration.

             Invokes the doUntight method, then waits until the
             screwdriver finishes (busy == false).

             Args:
               equipment: The eTensil equipment instance.
               timeMs: Reverse-drive duration in milliseconds.

             Returns:
               actionDone: true if the PLC accepted the command.
             */

        in ref equipment : ETensilEquipment;
        in timeMs : Real;
        out actionDone : Boolean;

        first start;

        then perform action callDoUntight references equipment.doUntight {
            in :>> timeMs = EtensilDoUntight::timeMs;
        }

        then mWaitDone;
        merge mWaitDone;
        then decide;
            if equipment.busy == false then afterWait;
            else mWaitDone;

        action afterWait;
        then done;

        bind actionDone = callDoUntight.accepted;
    }
}
