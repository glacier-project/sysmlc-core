package DomainEnums {
    doc /* Enumeration types for the ICE Laboratory domain.
         These enumerations capture fixed value sets that recur across multiple
         service and recipe packages.
         */

    private import ScalarValues::*;

    enum def PalletSlot :> Integer {
        doc /* Physical slot positions on a conveyor pallet.*/
        pos1 = 1;
        pos2 = 2;
        pos3 = 3;
    }

    enum def ReservationKind :> Integer {
        doc /* Pallet reservation types used by the conveyor PLC.

             Values:
               unreserved (0): Pallet is free, no reservation held.
               transport (1): Short-lived lock while the pallet is in transit
                 to a destination.
               processing (2): Longer-lived lock while a workcell is operating
                 on the pallet.
             */
        unreserved = 0;
        transport = 1;
        processing = 2;
    }

    enum def BayLightState :> Integer {
        doc /* State of the signal light at a conveyor bay.*/
        off = 0;
        signaling = 2;
    }

    enum def PalletType :> Integer {
        doc /* Physical pallet jig types on the conveyor.

             Values:
               generic (0): Generic flat pallet (no special jig).
               coverSupport (1): Jig for gadget covers.
               iceTrackerSupport (2): Jig for ICE-tracker boards.
             */
        generic = 0;
        coverSupport = 1;
        iceTrackerSupport = 2;
    }

    enum def PalletContentFilter :> Integer {
        doc /* Sentinel values for pallet content matching in CheckPalletMatch
             and ReserveFreePallet* services.

             Values:
               dontCare (-1): Skip checking this position/type.
               anyNonEmpty (-2): Match any non-zero content.
               empty (0): Slot is empty.
             */
        dontCare = -1;
        anyNonEmpty = -2;
        empty = 0;
    }

    enum def RoboticCellState {
        doc /* Observable PLC states for the robotic assembly cell.
             * Published via the state port on each state entry.
             */
        enum UNINITIALIZED;
        enum IDLE;
        enum RUNNING;
        enum DONE;
        enum ERROR;
    }

    enum def ConveyorDestination :> Integer {
        doc /* Byte codes identifying physical bay positions on the conveyor loop.
             Each value is the PLC address sent to setPalletDestination.

             Values:
               mainBelt (0): Circulate on the main belt without stopping.
               bay1_loadUnload (9): Bay 1 — manual load/unload zone.
               bay2_milling (19): Bay 2 — CNC milling station (Milling_1).
               bay3_roboticCell (25): Bay 3 — robotic assembly cell (roboticCell).
               bay4_qualityControl (34): Bay 4 — quality control camera (qualityControl).
               bay4_qualityControlAlt (35): Bay 4 — alternate QC stop position.
               bay5_warehouse (40): Bay 5 — warehouse tray exchange zone.
             */
        mainBelt = 0;
        bay1_loadUnload = 9;
        bay2_milling = 19;
        bay3_roboticCell = 25;
        bay4_qualityControl = 34;
        bay4_qualityControlAlt = 35;
        bay5_warehouse = 40;
    }
}
