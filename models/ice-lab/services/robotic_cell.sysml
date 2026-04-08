package RoboticCell {
    doc /* Robotic assembly cell services (Cell 4, equipment ID: roboticCell).*/

    private import ScalarValues::*;
    private import EquipmentInterfaces::*;
    private import RecipePrimitives::*;

    action def WaitRoboticCellDone {
        doc /* Two-phase poll on plcOperationDone shared by all robotic cell services.
             * Phase 1: wait for plcOperationDone == false (PLC acknowledged the command).
             * Phase 2: wait for plcOperationDone == true (operation finished).
             */

        in ref equipment : RoboticCellEquipment;

        first start;

        then mWaitStarted;
        merge mWaitStarted;
        then decide;
            if equipment.plcOperationDone == false then mWaitDone;
            else mWaitStarted;

        merge mWaitDone;
        then decide;
            if equipment.plcOperationDone == true then afterWait;
            else mWaitDone;

        action afterWait;
        then done;
    }

    action def PickFromPallet :> MachineService {
        doc /* Pick a part from a pallet position into the robot buffer.

             Invokes the pickFromPallet method, then waits for PLC completion
             via WaitRoboticCellDone. The PLC selects an available buffer slot
             automatically.

             Args:
               equipment: The robotic cell equipment instance.
               posPick: Pallet position to pick from (1-3).
               shape: Shape code identifying the part type, so the robot
                 selects the correct gripper program.

             Returns:
               result: true if the PLC accepted the command.
               bufferPos: Buffer slot (0-4) where the part was placed.
               errorCode: 0 on success, non-zero on robot fault.
             */

        in ref equipment : RoboticCellEquipment;
        in posPick : Integer;
        in shape : Integer;
        out result : Boolean;
        out bufferPos : Integer;
        out errorCode : Integer;

        first start;

        then action callPickFromPallet :> equipment.pickFromPallet {
            in :>> posPick = PickFromPallet::posPick;
            in :>> itemShape = PickFromPallet::shape;
        }

        then action waitDone : WaitRoboticCellDone {
            in ref :>> equipment = PickFromPallet::equipment;
        }
        then done;

        bind result = callPickFromPallet.result;
        bind bufferPos = callPickFromPallet.palletPosition;
        bind errorCode = callPickFromPallet.errorCode;
    }

    action def MoveAndPlace :> MachineService {
        doc /* Composite move: rearrange parts between pallet positions and buffer in one operation.

             Invokes the moveAndPlace method, then waits for PLC completion
             via WaitRoboticCellDone. Executes up to four sub-moves in a single
             PLC cycle. Set any position parameter to 0 to skip that sub-move.

             Args:
               equipment: The robotic cell equipment instance.
               posPickOnPallet: Pallet position to pick from (1-3, or 0 to skip).
               posPlaceOnPallet: Pallet position to place onto (1-3, or 0 to skip).
               posPickOnBuffer: Buffer slot to pick from (0-4, or 0 to skip).
               posPlaceFromBufferToPallet: Pallet position to place a buffer part
                 onto (1-3, or 0 to skip).

             Returns:
               result: true if the PLC accepted the command.
               errorCode: 0 on success, non-zero on robot fault.
             */

        in ref equipment : RoboticCellEquipment;
        in posPickOnPallet : Integer;
        in posPlaceOnPallet : Integer;
        in posPickOnBuffer : Integer;
        in posPlaceFromBufferToPallet : Integer;
        out result : Boolean;
        out errorCode : Integer;

        first start;

        then action callMoveAndPlace :> equipment.moveAndPlace {
            in :>> posPickOnPallet = MoveAndPlace::posPickOnPallet;
            in :>> posPlaceOnPallet = MoveAndPlace::posPlaceOnPallet;
            in :>> posPickOnBuffer = MoveAndPlace::posPickOnBuffer;
            in :>> posPlaceFromBufferToPallet = MoveAndPlace::posPlaceFromBufferToPallet;
        }

        then action waitDone : WaitRoboticCellDone {
            in ref :>> equipment = MoveAndPlace::equipment;
        }
        then done;

        bind result = callMoveAndPlace.result;
        bind errorCode = callMoveAndPlace.errorCode;
    }

    action def MoveOverPallet :> MachineService {
        doc /* Move a part directly from one pallet position to another.

             Invokes the moveOverPallet method, then waits for PLC completion
             via WaitRoboticCellDone.

             Args:
               equipment: The robotic cell equipment instance.
               posPick: Source pallet position (1-3).
               posPlace: Destination pallet position (1-3).

             Returns:
               result: true if the PLC accepted the command.
               errorCode: 0 on success, non-zero on robot fault.
             */

        in ref equipment : RoboticCellEquipment;
        in posPick : Integer;
        in posPlace : Integer;
        out result : Boolean;
        out errorCode : Integer;

        first start;

        then action callMoveOverPallet :> equipment.moveOverPallet {
            in :>> posPick = MoveOverPallet::posPick;
            in :>> posPlace = MoveOverPallet::posPlace;
        }

        then action waitDone : WaitRoboticCellDone {
            in ref :>> equipment = MoveOverPallet::equipment;
        }
        then done;

        bind result = callMoveOverPallet.result;
        bind errorCode = callMoveOverPallet.errorCode;
    }

    action def PlaceToPallet :> MachineService {
        doc /* Place a part from a buffer slot onto a pallet position.

             Invokes the placeToPallet method, then waits for PLC completion
             via WaitRoboticCellDone.

             Args:
               equipment: The robotic cell equipment instance.
               posPickOnBuffer: Buffer slot to pick from (0-4).
               posPlaceOnPallet: Pallet position to place onto (1-3).

             Returns:
               result: true if the PLC accepted the command.
               errorCode: 0 on success, non-zero on robot fault.
             */

        in ref equipment : RoboticCellEquipment;
        in posPickOnBuffer : Integer;
        in posPlaceOnPallet : Integer;
        out result : Boolean;
        out errorCode : Integer;

        first start;

        then action callPlaceToPallet :> equipment.placeToPallet {
            in :>> posPickOnBuffer = PlaceToPallet::posPickOnBuffer;
            in :>> posPlaceOnPallet = PlaceToPallet::posPlaceOnPallet;
        }

        then action waitDone : WaitRoboticCellDone {
            in ref :>> equipment = PlaceToPallet::equipment;
        }
        then done;

        bind result = callPlaceToPallet.result;
        bind errorCode = callPlaceToPallet.errorCode;
    }

    action def SubmitRobotOperation :> MachineService {
        doc /* Submit a low-level robot operation with full coordinate parameters.

             Invokes the submitRobotOperation method, then waits for PLC
             completion via WaitRoboticCellDone. This is the most general robot
             command -- higher-level services (ABBOperation, PickFromPallet, etc.)
             delegate to this with pre-filled defaults.

             Args:
               equipment: The robotic cell equipment instance.
               programID: Robot program selector (e.g. 2 = ABB pick-and-place).
               robotID: Robot selector (1 = ABB, 2 = KUKA).
               srcAreaId: Source area identifier (area-specific meaning).
               srcAreaPosX: X coordinate within the source area.
               srcAreaPosY: Y coordinate within the source area.
               dstAreaId: Destination area identifier.
               dstAreaPosX: X coordinate within the destination area.
               dstAreaPosY: Y coordinate within the destination area.
               argExtra: Program-specific extra argument (0 if unused).

             Returns:
               result: true if the PLC accepted the command.
               errorCode: 0 on success, non-zero on robot fault.
             */

        in ref equipment : RoboticCellEquipment;
        in programID : Integer;
        in robotID : Integer;
        in srcAreaId : Integer;
        in srcAreaPosX : Integer;
        in srcAreaPosY : Integer;
        in dstAreaId : Integer;
        in dstAreaPosX : Integer;
        in dstAreaPosY : Integer;
        in argExtra : Integer;
        out result : Boolean;
        out errorCode : Integer;

        first start;

        then action callSubmitRobotOp :> equipment.submitRobotOperation {
            in :>> programID = SubmitRobotOperation::programID;
            in :>> robotID = SubmitRobotOperation::robotID;
            in :>> srcAreaId = SubmitRobotOperation::srcAreaId;
            in :>> srcAreaPosX = SubmitRobotOperation::srcAreaPosX;
            in :>> srcAreaPosY = SubmitRobotOperation::srcAreaPosY;
            in :>> dstAreaId = SubmitRobotOperation::dstAreaId;
            in :>> dstAreaPosX = SubmitRobotOperation::dstAreaPosX;
            in :>> dstAreaPosY = SubmitRobotOperation::dstAreaPosY;
            in :>> argExtra = SubmitRobotOperation::argExtra;
        }

        then action waitDone : WaitRoboticCellDone {
            in ref :>> equipment = SubmitRobotOperation::equipment;
        }
        then done;

        bind result = callSubmitRobotOp.result;
        bind errorCode = callSubmitRobotOp.errorCode;
    }

    action def AbbPickBoardFromPallet :> MachineService {
        doc /* Pick a board from the pallet using the ABB robot.

             Invokes the abbPickBoardFromPallet method, then waits for PLC
             completion via WaitRoboticCellDone. The PLC auto-detects which
             pallet position holds the board.

             Args:
               equipment: The robotic cell equipment instance.

             Returns:
               result: true if the PLC accepted the command.
               errorCode: 0 on success, non-zero on robot fault.
               boardPos: Pallet position (1-3) from which the board was picked.
             */

        in ref equipment : RoboticCellEquipment;
        out result : Boolean;
        out errorCode : Integer;
        out boardPos : Integer;

        first start;

        then action callAbbPickBoard :> equipment.abbPickBoardFromPallet;

        then action waitDone : WaitRoboticCellDone {
            in ref :>> equipment = AbbPickBoardFromPallet::equipment;
        }
        then done;

        bind result = callAbbPickBoard.result;
        bind boardPos = callAbbPickBoard.boardPosition;
        bind errorCode = callAbbPickBoard.errorCode;
    }

    action def GadgetAssembly :> MachineService {
        doc /* Execute one phase of the gadget assembly sequence.

             Invokes the gadgetAssembly method, then waits for PLC completion
             via WaitRoboticCellDone. The full assembly consists of four phases
             called in order:
               1 -- Place board on jig and close clamp.
               2 -- Drive screw at position 1.
               3 -- Drive screw at position 2.
               4 -- Open clamp and finish assembly.

             Args:
               equipment: The robotic cell equipment instance.
               phaseNumber: Assembly phase to execute (1-4).
               boardPosition: Pallet position (1-3) where the board resides,
                 used by the PLC to select the correct jig coordinates.

             Returns:
               result: true if the PLC accepted the command.
               errorCode: 0 on success, non-zero on robot fault.
             */

        in ref equipment : RoboticCellEquipment;
        in phaseNumber : Integer;
        in boardPosition : Integer;
        out result : Boolean;
        out errorCode : Integer;

        first start;

        then action callGadgetAssembly :> equipment.gadgetAssembly {
            in :>> phaseNumber = GadgetAssembly::phaseNumber;
            in :>> boardPosition = GadgetAssembly::boardPosition;
        }

        then action waitDone : WaitRoboticCellDone {
            in ref :>> equipment = GadgetAssembly::equipment;
        }
        then done;

        bind result = callGadgetAssembly.result;
        bind errorCode = callGadgetAssembly.errorCode;
    }

    action def ABBOperation :> MachineService {
        doc /* Convenience wrapper for ABB robot pick-and-place with inline completion wait.

             Delegates to submitRobotOperation with hardcoded programID=2
             (ABB pick-and-place) and robotID=1 (ABB), then waits for PLC
             completion via WaitRoboticCellDone.

             Args:
               equipment: The robotic cell equipment instance.
               srcAreaId: Source area identifier.
               srcAreaPosX: X position in the source area.
               dstAreaId: Destination area identifier.
               dstAreaPosX: X position in the destination area.

             Returns:
               result: true if the PLC accepted the command.
               errorCode: 0 on success, non-zero on robot fault.
             */

        in ref equipment : RoboticCellEquipment;
        in srcAreaId : Integer;
        in srcAreaPosX : Integer;
        in dstAreaId : Integer;
        in dstAreaPosX : Integer;
        out result : Boolean;
        out errorCode : Integer;

        first start;

        then action callSubmitRobotOp :> equipment.submitRobotOperation {
            in constant :>> programID = 2;
            in constant :>> robotID = 1;
            in :>> srcAreaId = ABBOperation::srcAreaId;
            in :>> srcAreaPosX = ABBOperation::srcAreaPosX;
            in constant :>> srcAreaPosY = 0;
            in :>> dstAreaId = ABBOperation::dstAreaId;
            in :>> dstAreaPosX = ABBOperation::dstAreaPosX;
            in constant :>> dstAreaPosY = 0;
            in constant :>> argExtra = 0;
        }

        then action waitDone : WaitRoboticCellDone {
            in ref :>> equipment = ABBOperation::equipment;
        }
        then done;

        bind result = callSubmitRobotOp.result;
        bind errorCode = callSubmitRobotOp.errorCode;
    }
}
