package PlantTopology {
    doc /* Physical plant structure of the ICE Laboratory production line,
         * organized according to the ISA-95 / IEC 62264 equipment hierarchy:
         * Enterprise → Site → Area → Production Line → Work Cell → Equipment.
         */

    private import ScalarValues::*;
    private import EquipmentInterfaces::*;
    private import ISA95EquipmentHierarchy::*;
    private import FuncTesting::*;
    private import Milling::*;
    private import RoboticCell::*;
    private import ETensil::*;
    private import QualityControl::*;
    private import Warehouse::*;
    private import Conveyor::*;
    private import RbKairos::*;
    private import RoboticCellStates::*;
    private import DemoLegoRecipe::*;

    // ========================================================================
    // Work cell definitions
    // ========================================================================

    part def Cell1_FunctionalTesting :> WorkCell {
        part funcTesting : FuncTestingEquipment;

        perform action testBoard : TestBoard;
        perform action customizeFirmware : CustomizeFirmware;
    }

    part def Cell2_Milling :> WorkCell {
        part milling : MillingEquipment;

        perform action startMillingMission : StartMillingMission;
        perform action startEngraveText : StartEngraveText;
        perform action waitMillingBusy : WaitMillingBusy;
    }

    part def Cell4_RoboticAssembly :> WorkCell {
        part roboticCell : RoboticCellEquipment;
        part eTensil : ETensilEquipment;

        perform action pickFromPallet : PickFromPallet;
        perform action moveAndPlace : MoveAndPlace;
        perform action moveOverPallet : MoveOverPallet;
        perform action placeToPallet : PlaceToPallet;
        perform action submitRobotOperation : SubmitRobotOperation;
        perform action abbPickBoardFromPallet : AbbPickBoardFromPallet;
        perform action gadgetAssembly : GadgetAssembly;
        perform action abbOperation : ABBOperation;

        perform action doSingleScrew : EtensilDoSingleScrew;
        perform action doUntight : EtensilDoUntight;

        exhibit state plcStates : RoboticCellStates {
            in ref :>> equipment = roboticCell;
        }
    }

    part def Cell5_QualityControl :> WorkCell {
        part qualityControl : QualityControlEquipment;

        perform action checkQualityCovers : CheckQualityCovers;
        perform action checkQualityLego : CheckQualityLego;
    }

    part def Cell6_Warehouse :> WorkCell {
        part warehouse : WarehouseEquipment;

        perform action showMessage : ShowMessage;
        perform action extractTray : ExtractTray;
        perform action rejectTray : RejectTray;
    }

    part def Cell7_ConveyorSystem :> WorkCell {
        part conveyorBelt : ConveyorBeltEquipment;

        perform action releasePallet : ReleasePallet;
        perform action movePalletToMainBelt : MovePalletToMainBelt;
        perform action clearPartOnPallet : ClearPartOnPallet;
        perform action reservePallet : ReservePallet;
        perform action setPartOnPallet : SetPartOnPallet;

        perform action callFreePallet : CallFreePalletToDestination;
        perform action callFreePalletReserved : CallFreePalletToDestinationWithReservation;
        perform action callFreePalletOfType : CallFreePalletOfTypeToDestination;
        perform action callFreePalletOfTypeReserved : CallFreePalletOfTypeToDestinationWithReservation;
        perform action setPalletToDestination : SetPalletToDestination;
        perform action setPalletToDestinationReserved : SetPalletToDestinationWithReservation;

        perform action waitAckLoadUnload : WaitAckLoadUnloadZone;
        perform action waitAckBay : WaitAckBay;

        perform action readPalletContent : ReadPalletContent;

        perform action reserveFreePallet : ReserveFreePallet;
        perform action reserveFreePalletOfType : ReserveFreePalletOfType;
        perform action reserveFreePallet2 : ReserveFreePallet2;
        perform action reserveFreePalletOfType2 : ReserveFreePalletOfType2;
    }

    part def MobileLogistics :> WorkCell {
        part rbKairosA : RbKairosEquipment {
            attribute :>> opcUaEndpoint = "opc.tcp://10.197.20.31:4840/";
        }
        part rbKairosB : RbKairosEquipment {
            attribute :>> opcUaEndpoint = "opc.tcp://10.197.20.32:4840/";
        }

        perform action startMission : StartRbKairosMission;
        perform action waitOnControlBusy : WaitOnControlBusy;
    }

    // ========================================================================
    // Production line
    // ========================================================================

    part def ICEProductionLine :> ProductionLine {

        // Work cells
        part cell1 : Cell1_FunctionalTesting subsets work_cells;
        part cell2 : Cell2_Milling subsets work_cells;
        part cell4 : Cell4_RoboticAssembly subsets work_cells;
        part cell5 : Cell5_QualityControl subsets work_cells;
        part cell6 : Cell6_Warehouse subsets work_cells;
        part cell7 : Cell7_ConveyorSystem subsets work_cells;
        part mobileLogistics : MobileLogistics subsets work_cells;

        perform action demoLego : DemoLego {
            in ref :>> conveyorEquipment = cell7.conveyorBelt;
            in ref :>> roboticCellEquipment = cell4.roboticCell;
            in ref :>> qualityControlEquipment = cell5.qualityControl;

            // Task 1: LD
            action :>> opLD {
                perform action :>> reserve;
                allocate reserve to cell7.reserveFreePalletOfType2;
            }

            // Task 2: RBTC
            action :>> opRBTC {
                // Conveyor (Cell7)
                perform action :>> routePallet1;
                perform action :>> readShape1;
                perform action :>> clearPart1;
                perform action :>> movePallet1;
                perform action :>> releasePallet1;
                perform action :>> routePallet2;
                perform action :>> readShape2;
                perform action :>> clearPart2;
                perform action :>> setPartShape2;
                perform action :>> setPartShape1;
                perform action :>> movePallet2;
                // Robotic (Cell4)
                perform action :>> pick;
                perform action :>> moveAndPlace;

                allocate routePallet1 to cell7.setPalletToDestination;
                allocate readShape1 to cell7.readPalletContent;
                allocate routePallet2 to cell7.setPalletToDestination;
                allocate readShape2 to cell7.readPalletContent;
                allocate clearPart1 to cell7.clearPartOnPallet;
                allocate clearPart2 to cell7.clearPartOnPallet;
                allocate movePallet1 to cell7.movePalletToMainBelt;
                allocate movePallet2 to cell7.movePalletToMainBelt;
                allocate releasePallet1 to cell7.releasePallet;
                allocate setPartShape1 to cell7.setPartOnPallet;
                allocate setPartShape2 to cell7.setPartOnPallet;
                allocate pick to cell4.pickFromPallet;
                allocate moveAndPlace to cell4.moveAndPlace;
            }

            // Task 3: QC
            action :>> opQC {
                perform action :>> routePallet;
                perform action :>> checkQuality;
                perform action :>> movePallet;

                allocate routePallet to cell7.setPalletToDestination;
                allocate checkQuality to cell5.checkQualityLego;
                allocate movePallet to cell7.movePalletToMainBelt;
            }

            // Task 4: RESRVPALLET
            action :>> opRESRVPALLET {
                perform action :>> reserve;
                allocate reserve to cell7.reserveFreePalletOfType2;
            }

            // Task 5: DISASSEMBLE
            action :>> opDISASSEMBLE {
                // Phase 1: Disassemble from pallet 2 (Cell7 conveyor + Cell4 robotic)
                perform action :>> routeToRobot1;
                perform action :>> pick;
                perform action :>> clearPos1;
                perform action :>> moveOver;
                perform action :>> clearPos3;
                perform action :>> setPartPos2;
                perform action :>> moveP2ToMain;
                perform action :>> releaseP2;
                // Phase 2: Place onto fresh pallet 1 (Cell7 conveyor + Cell4 robotic)
                perform action :>> routeToRobot2;
                perform action :>> place;
                perform action :>> setPartOnP1;
                perform action :>> moveP1ToMain;
                perform action :>> releaseP1;

                allocate routeToRobot1 to cell7.setPalletToDestination;
                allocate routeToRobot2 to cell7.setPalletToDestination;
                allocate pick to cell4.pickFromPallet;
                allocate place to cell4.placeToPallet;
                allocate moveOver to cell4.moveOverPallet;
                allocate clearPos1 to cell7.clearPartOnPallet;
                allocate clearPos3 to cell7.clearPartOnPallet;
                allocate setPartPos2 to cell7.setPartOnPallet;
                allocate setPartOnP1 to cell7.setPartOnPallet;
                allocate moveP2ToMain to cell7.movePalletToMainBelt;
                allocate moveP1ToMain to cell7.movePalletToMainBelt;
                allocate releaseP2 to cell7.releasePallet;
                allocate releaseP1 to cell7.releasePallet;
            }
        }

        // Conveyor serves workcells (material transport connections)
        connect cell1 to cell7;
        connect cell2 to cell7;
        connect cell4 to cell7;
        connect cell5 to cell7;

        // Mobile robots bridge warehouse and conveyor load/unload zone
        connect cell6 to mobileLogistics;
        connect mobileLogistics to cell7;
    }

    // ========================================================================
    // Upper hierarchy: Area → Site → Enterprise
    // ========================================================================

    part def ICELaboratory :> Area {
        part productionLine : ICEProductionLine subsets production_lines;
    }

    part def DIMI :> Site {
        part iceLab : ICELaboratory subsets areas;
    }

    part def UniVR :> Enterprise {
        part dimi : DIMI subsets sites;
    }

    part uniVR : UniVR;
}
