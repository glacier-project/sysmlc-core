package Warehouse {
    doc /* Automated tray storage system services (Cell 6, equipment ID: warehouse).*/

    private import ScalarValues::*;
    private import EquipmentInterfaces::*;
    private import RecipePrimitives::*;

    action def ShowMessage :> MachineService {
        doc /* Display an operator message on the warehouse HMI screen.

             Args:
               equipment: The warehouse equipment instance.
               msg: Text to display on the HMI screen.
             */

        in ref equipment : WarehouseEquipment;
        in msg : String;

        first start;

        then action callShowMessage :> equipment.showMessage {
            in :>> msg = ShowMessage::msg;
        }

        then done;
    }

    action def ExtractTray :> MachineService {
        doc /* Extract a tray from warehouse storage to the shared bay.

             Invokes the extractTray PLC method, then waits for the tray
             to arrive at the bay (trayInBay == trayNumber) and for the bay
             to become ready for pick/place operations
             (bayReadyForPickPlace == true).

             Args:
               equipment: The warehouse equipment instance.
               trayNumber: Warehouse slot number of the tray to extract.

             Returns:
               code: PLC return code (0 = success).
             */

        in ref equipment : WarehouseEquipment;
        in trayNumber : Integer;
        out code : Integer;

        first start;

        then action callExtractTray :> equipment.extractTray {
            in :>> num = ExtractTray::trayNumber;
        }

        then mWaitTray;
        merge mWaitTray;
        then decide;
            if equipment.trayInBay == trayNumber then mWaitBayReady;
            else mWaitTray;

        merge mWaitBayReady;
        then decide;
            if equipment.bayReadyForPickPlace == true then afterWait;
            else mWaitBayReady;

        action afterWait;
        then done;

        bind code = callExtractTray.code;
    }

    action def RejectTray :> MachineService {
        doc /* Return the current tray from the bay back to warehouse storage.

             Invokes sendBackTray, then waits until the bay mechanism
             finishes (bayBusy == false).

             Args:
               equipment: The warehouse equipment instance.

             Returns:
               code: PLC return code (0 = success).
             */

        in ref equipment : WarehouseEquipment;
        out code : Integer;

        first start;

        then action callSendBackTray :> equipment.sendBackTray;

        then mWaitDone;
        merge mWaitDone;
        then decide;
            if equipment.bayBusy == false then afterWait;
            else mWaitDone;

        action afterWait;
        then done;

        bind code = callSendBackTray.code;
    }
}
