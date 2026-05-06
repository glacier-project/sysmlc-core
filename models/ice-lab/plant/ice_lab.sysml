package PlantTopology {
    doc /* Physical plant structure of the ICE Laboratory production line,
         * organized according to the ISA-95 / IEC 62264 equipment hierarchy:
         * Enterprise → Site → Area → Production Line → Work Cell → Equipment.
         */

    private import ScalarValues::*;
    private import ISQ::DurationValue;
    private import SI::s;
    private import EquipmentInterfaces::*;
    private import OpcUaBinding::*;
    private import ISA95EquipmentHierarchy::*;
    private import FuncTesting::*;
    private import Milling::*;
    private import MillingCellBehavior::*;
    private import RoboticCell::*;
    private import ETensil::*;
    private import QualityControl::*;
    private import Warehouse::*;
    private import Conveyor::*;
    private import RbKairos::*;
    private import DemoLegoRecipe::*;

    // ========================================================================
    // Work cell definitions
    // ========================================================================

    part def Cell1_FunctionalTesting :> WorkCell {
        part funcTesting : FuncTestingEquipment {
            @OpcUaConnection { endpoint = "opc.tcp://10.197.11.11:4840/"; }
        }

        action testBoard : TestBoard {
            in ref :>> equipment = funcTesting;
        }
        action customizeFirmware : CustomizeFirmware {
            in ref :>> equipment = funcTesting;
        }
    }

    part def Cell2_Milling :> WorkCell {
        doc /* Cell 2 milling workcell.
             *
             * The controller part is the public OPC-UA facade. The manipulator
             * and millingMachine parts represent internal physical components
             * used by the inferred behavior model.
             */

        part controller : MillingEquipment subsets equipment {
            @OpcUaConnection { endpoint = "opc.tcp://10.197.12.11:4840/"; }
            attribute :>> status = MillingControllerState::idle;
            attribute :>> currentText = "";
            attribute :>> mesBusy = false;
            attribute :>> mesLastResult = false;
            attribute :>> currentMission = "";
        }
        part manipulator : MillingManipulator subsets equipment {
            attribute :>> status = ManipulatorState::idle;
        }
        part millingMachine : EmcoConceptMill105 subsets equipment {
            attribute :>> status = MillingMachineState::idle;
            attribute :>> doorState = DoorState::closed;
            attribute :>> viseState = ViseState::open;
            attribute :>> spindleState = SpindleState::stopped;
        }

        attribute gadgetLocation : GadgetLocation = GadgetLocation::onPallet;
        attribute gadgetEngraved : Boolean = false;
        attribute engravedText : String = "";
        attribute palletPresent : Boolean = false;

        action startMillingMission : StartMillingMission {
            in ref :>> equipment = controller;
        }
        action startEngraveText : StartEngraveText {
            in ref :>> equipment = controller;
        }
        action waitMillingBusy : WaitMillingBusy {
            in ref :>> equipment = controller;
        }

        exhibit state engravingStates : MillingCellEngravingStates {
            in ref :>> equipment = controller;
            inout :>> controllerState = controller.status;
            inout :>> currentText = controller.currentText;
            inout :>> manipulatorState = manipulator.status;
            inout :>> machineState = millingMachine.status;
            inout :>> doorState = millingMachine.doorState;
            inout :>> viseState = millingMachine.viseState;
            inout :>> spindleState = millingMachine.spindleState;
            inout :>> gadgetLocation = Cell2_Milling::gadgetLocation;
            inout :>> gadgetEngraved = Cell2_Milling::gadgetEngraved;
            inout :>> engravedText = Cell2_Milling::engravedText;
            inout :>> palletPresent = Cell2_Milling::palletPresent;
        }
    }

    part def Cell4_RoboticAssembly :> WorkCell {
        part roboticCell : RoboticCellEquipment {
            @OpcUaConnection { endpoint = "opc.tcp://10.197.14.21:4840/"; }
        }
        part eTensil : ETensilEquipment {
            @OpcUaConnection { endpoint = "opc.tcp://etensil-relay:4841/"; }
        }

        action pickFromPallet : PickFromPallet {
            in ref :>> equipment = roboticCell;
        }
        action moveAndPlace : MoveAndPlace {
            in ref :>> equipment = roboticCell;
        }
        action moveOverPallet : MoveOverPallet {
            in ref :>> equipment = roboticCell;
        }
        action placeToPallet : PlaceToPallet {
            in ref :>> equipment = roboticCell;
        }
        action submitRobotOperation : SubmitRobotOperation {
            in ref :>> equipment = roboticCell;
        }
        action abbPickBoardFromPallet : AbbPickBoardFromPallet {
            in ref :>> equipment = roboticCell;
        }
        action gadgetAssembly : GadgetAssembly {
            in ref :>> equipment = roboticCell;
        }
        action abbOperation : ABBOperation {
            in ref :>> equipment = roboticCell;
        }

        action doSingleScrew : EtensilDoSingleScrew {
            in ref :>> equipment = eTensil;
        }
        action doUntight : EtensilDoUntight {
            in ref :>> equipment = eTensil;
        }
    }

    part def Cell5_QualityControl :> WorkCell {
        part qualityControl : QualityControlEquipment {
            @OpcUaConnection { endpoint = "opc.tcp://10.197.15.11:4840/"; }
        }

        action checkQualityCovers : CheckQualityCovers {
            in ref :>> equipment = qualityControl;
        }
        action checkQualityLego : CheckQualityLego {
            in ref :>> equipment = qualityControl;
        }
    }

    part def Cell6_Warehouse :> WorkCell {
        part warehouse : WarehouseEquipment {
            @OpcUaConnection { endpoint = "opc.tcp://10.197.16.11:4840/"; }
        }

        action showMessage : ShowMessage {
            in ref :>> equipment = warehouse;
        }
        action extractTray : ExtractTray {
            in ref :>> equipment = warehouse;
        }
        action rejectTray : RejectTray {
            in ref :>> equipment = warehouse;
        }
    }

    part def Cell7_ConveyorSystem :> WorkCell {
        part conveyorBelt : ConveyorBeltEquipment {
            @OpcUaConnection { endpoint = "opc.tcp://10.197.17.11:59100/"; }
        }

        action releasePallet : ReleasePallet {
            in ref :>> equipment = conveyorBelt;
        }
        action movePalletToMainBelt : MovePalletToMainBelt {
            in ref :>> equipment = conveyorBelt;
        }
        action clearPartOnPallet : ClearPartOnPallet {
            in ref :>> equipment = conveyorBelt;
        }
        action reservePallet : ReservePallet {
            in ref :>> equipment = conveyorBelt;
        }
        action setPartOnPallet : SetPartOnPallet {
            in ref :>> equipment = conveyorBelt;
        }

        action callFreePallet : CallFreePalletToDestination {
            in ref :>> equipment = conveyorBelt;
        }
        action callFreePalletReserved : CallFreePalletToDestinationWithReservation {
            in ref :>> equipment = conveyorBelt;
        }
        action callFreePalletOfType : CallFreePalletOfTypeToDestination {
            in ref :>> equipment = conveyorBelt;
        }
        action callFreePalletOfTypeReserved : CallFreePalletOfTypeToDestinationWithReservation {
            in ref :>> equipment = conveyorBelt;
        }
        action setPalletToDestination : SetPalletToDestination {
            in ref :>> equipment = conveyorBelt;
        }
        action setPalletToDestinationReserved : SetPalletToDestinationWithReservation {
            in ref :>> equipment = conveyorBelt;
        }

        action waitAckLoadUnload : WaitAckLoadUnloadZone {
            in ref :>> equipment = conveyorBelt;
        }
        action waitAckBay : WaitAckBay {
            in ref :>> equipment = conveyorBelt;
        }

        action readPalletContent : ReadPalletContent {
            in ref :>> equipment = conveyorBelt;
        }

        action reserveFreePallet : ReserveFreePallet {
            in ref :>> equipment = conveyorBelt;
        }
        action reserveFreePalletOfType : ReserveFreePalletOfType {
            in ref :>> equipment = conveyorBelt;
        }
        action reserveFreePallet2 : ReserveFreePallet2 {
            in ref :>> equipment = conveyorBelt;
        }
        action reserveFreePalletOfType2 : ReserveFreePalletOfType2 {
            in ref :>> equipment = conveyorBelt;
        }
    }

    part def MobileLogistics :> WorkCell {
        part rbKairosA : RbKairosEquipment {
            @OpcUaConnection { endpoint = "opc.tcp://10.197.20.31:4840/"; }
        }
        part rbKairosB : RbKairosEquipment {
            @OpcUaConnection { endpoint = "opc.tcp://10.197.20.32:4840/"; }
        }

        action startMission : StartRbKairosMission;
        action waitOnControlBusy : WaitOnControlBusy;
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
                action :>> reserve references cell7.reserveFreePalletOfType2;
            }

            // Task 2: RBTC
            action :>> opRBTC {
                // Conveyor (Cell7)
                action :>> routePallet1 references cell7.setPalletToDestination;
                action :>> readShape1 references cell7.readPalletContent;
                action :>> clearPart1 references cell7.clearPartOnPallet;
                action :>> movePallet1 references cell7.movePalletToMainBelt;
                action :>> releasePallet1 references cell7.releasePallet;
                action :>> routePallet2 references cell7.setPalletToDestination;
                action :>> readShape2 references cell7.readPalletContent;
                action :>> clearPart2 references cell7.clearPartOnPallet;
                action :>> setPartShape2 references cell7.setPartOnPallet;
                action :>> setPartShape1 references cell7.setPartOnPallet;
                action :>> movePallet2 references cell7.movePalletToMainBelt;
                // Robotic (Cell4)
                action :>> pick references cell4.pickFromPallet;
                action :>> moveAndPlace references cell4.moveAndPlace;
            }

            // Task 3: QC
            action :>> opQC {
                action :>> routePallet references cell7.setPalletToDestination;
                action :>> checkQuality references cell5.checkQualityLego;
                action :>> movePallet references cell7.movePalletToMainBelt;
            }

            // Task 4: RESRVPALLET
            action :>> opRESRVPALLET {
                action :>> reserve references cell7.reserveFreePalletOfType2;
            }

            // Task 5: DISASSEMBLE
            action :>> opDISASSEMBLE {
                // Phase 1: Disassemble from pallet 2 (Cell7 conveyor + Cell4 robotic)
                action :>> routeToRobot1 references cell7.setPalletToDestination;
                action :>> pick references cell4.pickFromPallet;
                action :>> clearPos1 references cell7.clearPartOnPallet;
                action :>> moveOver references cell4.moveOverPallet;
                action :>> clearPos3 references cell7.clearPartOnPallet;
                action :>> setPartPos2 references cell7.setPartOnPallet;
                action :>> moveP2ToMain references cell7.movePalletToMainBelt;
                action :>> releaseP2 references cell7.releasePallet;
                // Phase 2: Place onto fresh pallet 1 (Cell7 conveyor + Cell4 robotic)
                action :>> routeToRobot2 references cell7.setPalletToDestination;
                action :>> place references cell4.placeToPallet;
                action :>> setPartOnP1 references cell7.setPartOnPallet;
                action :>> moveP1ToMain references cell7.movePalletToMainBelt;
                action :>> releaseP1 references cell7.releasePallet;
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
