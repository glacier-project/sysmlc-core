package FuncTesting {
    doc /* SPEA flying-probe functional test station services (Cell 1, equipment ID: FuncTesting_1).*/

    private import ScalarValues::*;
    private import EquipmentInterfaces::*;
    private import RecipePrimitives::*;

    action def CustomizeFirmware :> MachineService {
        doc /* Download and customize firmware on the flying-probe test station.

             Transfers a firmware image to the test station and applies a
             board-specific customization (e.g. serial number or MAC address).

             Args:
               equipment: The functional test equipment instance.
               sourceFilename: Path or name of the base firmware image file
                 on the test station's local storage.
               customID: Board-specific identifier embedded into the firmware
                 during customization (typically a serial number).
             */

        in ref equipment : FuncTestingEquipment;
        in sourceFilename : String;
        in customID : String;

        first start;

        then action callDownloadFirmware :> equipment.downloadFirmware {
            in :>> sourceFilename = CustomizeFirmware::sourceFilename;
            in :>> customID = CustomizeFirmware::customID;
        }

        then done;
    }

    action def TestBoard :> MachineService {
        doc /* Run a three-phase functional test on a board.

             Protocol: (1) BoardIn -- position the board on the probe fixture;
             (2) StartTest -- execute the electrical test program;
             (3) BoardOut -- release the board from the fixture. Each phase
             calls the equipment method, then waits for busy to clear. If
             BoardIn or BoardOut returns "error", the service short-circuits
             and sets resultTest to "error". On success, resultTest carries
             the StartTest result string (e.g. "pass", "fail", or a diagnostic code).

             Args:
               equipment: The functional test equipment instance.
               serialNumber: Board serial number passed to the StartTest phase
                 for test-report traceability.

             Returns:
               resultTest: Test outcome string from StartTest on success,
                 or "error" if any phase fails.
             */

        in ref equipment : FuncTestingEquipment;
        in serialNumber : String;
        out resultTest : String;

        first start;

        // --- Phase 1: BoardIn ---
        then action callBoardIn :> equipment.boardIn;

        then mWaitBoardIn;
        merge mWaitBoardIn;
        then decide;
            if equipment.busy == false then checkBoardIn;
            else mWaitBoardIn;

        action checkBoardIn;
        then decide;
            if equipment.lastResult == "error" then handleBoardInError;
            else callStartTest;

        action handleBoardInError {
            assign resultTest := "error";
        }
        then mBoardIn;

        // --- Phase 2: StartTest ---
        action callStartTest :> equipment.startTest {
            in :>> serialNumber = TestBoard::serialNumber;
        }

        then mWaitStartTest;
        merge mWaitStartTest;
        then decide;
            if equipment.busy == false then saveTestResult;
            else mWaitStartTest;

        action saveTestResult {
            assign resultTest := equipment.lastResult;
        }

        // --- Phase 3: BoardOut ---
        then action callBoardOut :> equipment.boardOut;

        then mWaitBoardOut;
        merge mWaitBoardOut;
        then decide;
            if equipment.busy == false then checkBoardOut;
            else mWaitBoardOut;

        action checkBoardOut;
        then decide;
            if equipment.lastResult == "success" then afterTest;
            else handleBoardOutError;

        action handleBoardOutError {
            assign resultTest := "error";
        }
        then mBoardOut;

        action afterTest;
        then mBoardOut;

        merge mBoardOut;
        then mBoardIn;

        merge mBoardIn;
        then done;
    }
}

