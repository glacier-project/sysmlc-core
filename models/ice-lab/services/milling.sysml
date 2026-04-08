package Milling {
    doc /* CNC milling services (Cell 2, equipment ID: Milling_1).*/

    private import ScalarValues::*;
    private import EquipmentInterfaces::*;
    private import RecipePrimitives::*;

    action def StartMillingMission :> MachineService {
        doc /* Begin a CNC milling mission and return immediately.

             Calls the startMission method on the equipment. The caller
             must later call WaitMillingBusy to block until the milling
             cycle completes.

             Args:
               equipment: The milling equipment instance to operate on.
               mission_name: G-code program name registered on the CNC controller.

             Returns:
               actionDone: true if the PLC accepted the mission.
             */

        in ref equipment : MillingEquipment;
        in mission_name : String;
        out actionDone : Boolean;

        first start;

        then action callStartMission :> equipment.startMission {
            in :>> missionName = StartMillingMission::mission_name;
        }

        then done;

        bind actionDone = callStartMission.accepted;
    }

    action def StartEngraveText :> MachineService {
        doc /* Begin a text engraving operation on the CNC station and return immediately.

             Calls the engraveText method on the equipment. The caller
             must later call WaitMillingBusy to block until the engraving
             cycle completes.

             Args:
               equipment: The milling equipment instance to operate on.
               text: String to engrave on the workpiece.

             Returns:
               actionDone: true if the PLC accepted the command.
             */

        in ref equipment : MillingEquipment;
        in text : String;
        out actionDone : Boolean;

        first start;

        then action callEngraveText :> equipment.engraveText {
            in :>> text = StartEngraveText::text;
        }

        then done;

        bind actionDone = callEngraveText.accepted;
    }

    action def WaitMillingBusy :> MachineService {
        doc /* Block until a previously started milling or engraving operation completes.

             Polls the equipment's mesBusy flag until the CNC cycle finishes,
             then returns the mesLastResult value.

             Args:
               equipment: The milling equipment instance to monitor.

             Returns:
               result: true if the CNC cycle completed successfully.
             */

        in ref equipment : MillingEquipment;
        out result : Boolean;

        first start;

        then mWaitDone;
        merge mWaitDone;
        then decide;
            if equipment.mesBusy == false then afterWait;
            else mWaitDone;

        action afterWait;
        then done;

        bind result = equipment.mesLastResult;
    }
}
