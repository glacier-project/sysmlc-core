package RbKairos {
    doc /* Robotnik RB Kairos autonomous mobile robot services (equipment IDs: rbkairosA, rbkairosB).*/

    private import ScalarValues::*;
    private import EquipmentInterfaces::*;
    private import RecipePrimitives::*;

    action def StartRbKairosMission :> MachineService {
        doc /* Begin a navigation mission on an RB Kairos mobile robot.

             Invokes the startMission method and returns immediately.
             The caller must later call WaitOnControlBusy to block until
             the robot reaches its destination.

             Args:
               rbKairos: Reference to the robot instance (rbkairosA or rbkairosB).
               missionName: Named mission registered on the robot's navigation
                 controller (e.g. "GoToCell4", "GoToCharger").

             Returns:
               actionDone: true if the robot accepted the mission command.
             */

        in ref rbKairos : RbKairosEquipment;
        in missionName : String;
        out actionDone : Boolean;

        first start;

        then action callStartMission :> rbKairos.startMission {
            in :>> name = StartRbKairosMission::missionName;
        }

        then done;

        bind actionDone = callStartMission.accepted;
    }

    action def WaitOnControlBusy :> MachineService {
        doc /* Block until an RB Kairos mission completes and read the outcome.

             Waits until controlBusy goes false, then returns the
             lastMissionResult value.

             Args:
               rbKairos: Reference to the robot instance (rbkairosA or rbkairosB).

             Returns:
               result: true if the mission completed successfully.
             */

        in ref rbKairos : RbKairosEquipment;
        out result : Boolean;

        first start;

        then mWaitDone;
        merge mWaitDone;
        then decide;
            if rbKairos.controlBusy == false then afterWait;
            else mWaitDone;

        action afterWait;
        then done;

        bind result = rbKairos.lastMissionResult;
    }
}
