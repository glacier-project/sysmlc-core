package DemoLegoRecipe {
    doc /* DEMO_LEGO production recipe: Lego assembly with 5 tasks
         * (LD → RBTC → QC → RESRVPALLET → DISASSEMBLE).*/

    private import ScalarValues::*;
    private import SequenceFunctions::*;
    private import DomainEnums::*;
    private import EquipmentInterfaces::*;
    private import Conveyor::*;
    private import RoboticCell::*;
    private import QualityControl::*;
    private import RecipePrimitives::*;

    // ========================================================================
    // Task 1: LD (Load) — Reserve 2 pallets
    // ========================================================================

    action def TaskLD :> Task {
        doc /* Reserve two pallets with content configuration for Lego assembly. */

        in ref conveyorEquipment : ConveyorBeltEquipment;
        out palletID1 : Integer = reserve.palletIds#(1);
        out palletID2 : Integer = reserve.palletIds#(2);

        first start;

        then perform action reserve : ReserveFreePalletOfType2 {
            in constant :>> palletNumber = 2;
            in constant :>> contentPos1 = PalletContentFilter::empty;
            in constant :>> contentPos2 = PalletContentFilter::anyNonEmpty;
            in constant :>> contentPos3 = PalletContentFilter::empty;
            in constant :>> palletType = PalletType::generic;
            in ref :>> equipment = TaskLD::conveyorEquipment;
        }

        then done;
    }

    // ========================================================================
    // Task 2: RBTC (Robotic Cell) — Pick, rearrange, and place parts
    // ========================================================================

    action def TaskRBTC :> Task {
        doc /* Route pallets to robotic cell, pick parts, rearrange between
             * pallets using robot buffer, and update pallet content tracking.
             */

        in palletID1 : Integer;
        in palletID2 : Integer;
        in ref conveyorEquipment : ConveyorBeltEquipment;
        in ref roboticCellEquipment : RoboticCellEquipment;
        out shape1 : Integer;
        out shape2 : Integer;
        out buf1 : Integer;

        first start;

        // --- Phase 1: Route pallet 1, pick part from position 2 ---

        then perform action routePallet1 : SetPalletToDestination {
            in :>> palletNumber = TaskRBTC::palletID1;
            in constant :>> destination = ConveyorDestination::bay3_roboticCell;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
            in ref :>> palletAtDestination = TaskRBTC::conveyorEquipment.destinationPalletId_3_1;
        }

        then perform action readShape1 : ReadPalletContent {
            in :>> palletNumber = TaskRBTC::palletID1;
            in constant :>> position = PalletSlot::pos2;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
        }

        then perform action pick : PickFromPallet {
            in constant :>> posPick = PalletSlot::pos2;
            in :>> shape = readShape1.result;
            in ref :>> equipment = TaskRBTC::roboticCellEquipment;
        }

        then perform action clearPart1 : ClearPartOnPallet {
            in :>> palletNumber = TaskRBTC::palletID1;
            in constant :>> position = PalletSlot::pos2;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
        }

        then perform action movePallet1 : MovePalletToMainBelt {
            in :>> palletNumber = TaskRBTC::palletID1;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
        }

        then perform action releasePallet1 : ReleasePallet {
            in :>> palletNumber = TaskRBTC::palletID1;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
        }

        // --- Phase 2: Route pallet 2, rearrange parts ---

        then perform action routePallet2 : SetPalletToDestination {
            in :>> palletNumber = TaskRBTC::palletID2;
            in constant :>> destination = ConveyorDestination::bay3_roboticCell;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
            in ref :>> palletAtDestination = TaskRBTC::conveyorEquipment.destinationPalletId_3_1;
        }

        then perform action readShape2 : ReadPalletContent {
            in :>> palletNumber = TaskRBTC::palletID2;
            in constant :>> position = PalletSlot::pos2;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
        }

        then perform action moveAndPlace : MoveAndPlace {
            in constant :>> posPickOnPallet = PalletSlot::pos2;
            in constant :>> posPlaceOnPallet = PalletSlot::pos3;
            in :>> posPickOnBuffer = pick.bufferPos;
            in constant :>> posPlaceFromBufferToPallet = PalletSlot::pos1;
            in ref :>> equipment = TaskRBTC::roboticCellEquipment;
        }

        then perform action clearPart2 : ClearPartOnPallet {
            in :>> palletNumber = TaskRBTC::palletID2;
            in constant :>> position = PalletSlot::pos2;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
        }

        then perform action setPartShape2 : SetPartOnPallet {
            in :>> palletNumber = TaskRBTC::palletID2;
            in constant :>> position = PalletSlot::pos3;
            in :>> partCode = readShape2.result;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
        }

        then perform action setPartShape1 : SetPartOnPallet {
            in :>> palletNumber = TaskRBTC::palletID2;
            in constant :>> position = PalletSlot::pos1;
            in :>> partCode = readShape1.result;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
        }

        then perform action movePallet2 : MovePalletToMainBelt {
            in :>> palletNumber = TaskRBTC::palletID2;
            in ref :>> equipment = TaskRBTC::conveyorEquipment;
        }

        then done;

        bind shape1 = readShape1.result;
        bind shape2 = readShape2.result;
        bind buf1 = pick.bufferPos;
    }

    // ========================================================================
    // Task 3: QC (Quality Control) — Visual inspection
    // ========================================================================

    action def TaskQC :> Task {
        doc /* Route pallet to quality control station and verify Lego assembly. */

        in palletID2 : Integer;
        in shape1 : Integer;
        in shape2 : Integer;
        in ref conveyorEquipment : ConveyorBeltEquipment;
        in ref qualityControlEquipment : QualityControlEquipment;
        out qc : Boolean;

        first start;

        then perform action routePallet : SetPalletToDestination {
            in :>> palletNumber = TaskQC::palletID2;
            in constant :>> destination = ConveyorDestination::bay4_qualityControl;
            in ref :>> equipment = TaskQC::conveyorEquipment;
            in ref :>> palletAtDestination = TaskQC::conveyorEquipment.destinationPalletId_4_2;
        }

        then perform action checkQuality : CheckQualityLego {
            in :>> shape1 = TaskQC::shape1;
            in constant :>> shape2 = 0;
            in :>> shape3 = TaskQC::shape2;
            in ref :>> equipment = TaskQC::qualityControlEquipment;
        }

        then perform action movePallet : MovePalletToMainBelt {
            in :>> palletNumber = TaskQC::palletID2;
            in ref :>> equipment = TaskQC::conveyorEquipment;
        }

        then done;

        bind qc = checkQuality.result;
    }

    // ========================================================================
    // Task 4: RESRVPALLET — Reserve a fresh pallet for disassembly
    // ========================================================================

    action def TaskRESRVPALLET :> Task {
        doc /* Reserve one empty pallet for the disassembly phase. */

        in ref conveyorEquipment : ConveyorBeltEquipment;
        out palletID1 : Integer = reserve.palletIds#(1);

        first start;

        then perform action reserve : ReserveFreePalletOfType2 {
            in constant :>> palletNumber = 1;
            in constant :>> contentPos1 = PalletContentFilter::empty;
            in constant :>> contentPos2 = PalletContentFilter::empty;
            in constant :>> contentPos3 = PalletContentFilter::empty;
            in constant :>> palletType = PalletType::generic;
            in ref :>> equipment = TaskRESRVPALLET::conveyorEquipment;
        }

        then done;
    }

    // ========================================================================
    // Task 5: DISASSEMBLE — Reverse the assembly
    // ========================================================================

    action def TaskDISASSEMBLE :> Task {
        doc /* Disassemble Lego parts: pick from assembled pallet, rearrange,
             * then place onto a fresh pallet.
             */

        in palletID1 : Integer;
        in palletID2 : Integer;
        in shape1 : Integer;
        in shape2 : Integer;
        in ref conveyorEquipment : ConveyorBeltEquipment;
        in ref roboticCellEquipment : RoboticCellEquipment;

        first start;

        // --- Phase 1: Disassemble from pallet 2 ---

        then perform action routeToRobot1 : SetPalletToDestination {
            in :>> palletNumber = TaskDISASSEMBLE::palletID2;
            in constant :>> destination = ConveyorDestination::bay3_roboticCell;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
            in ref :>> palletAtDestination = TaskDISASSEMBLE::conveyorEquipment.destinationPalletId_3_1;
        }

        then perform action pick : PickFromPallet {
            in constant :>> posPick = PalletSlot::pos1;
            in :>> shape = TaskDISASSEMBLE::shape1;
            in ref :>> equipment = TaskDISASSEMBLE::roboticCellEquipment;
        }

        then perform action clearPos1 : ClearPartOnPallet {
            in :>> palletNumber = TaskDISASSEMBLE::palletID2;
            in constant :>> position = PalletSlot::pos1;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
        }

        then perform action moveOver : MoveOverPallet {
            in constant :>> posPick = PalletSlot::pos3;
            in constant :>> posPlace = PalletSlot::pos2;
            in ref :>> equipment = TaskDISASSEMBLE::roboticCellEquipment;
        }

        then perform action clearPos3 : ClearPartOnPallet {
            in :>> palletNumber = TaskDISASSEMBLE::palletID2;
            in constant :>> position = PalletSlot::pos3;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
        }

        then perform action setPartPos2 : SetPartOnPallet {
            in :>> palletNumber = TaskDISASSEMBLE::palletID2;
            in constant :>> position = PalletSlot::pos2;
            in :>> partCode = TaskDISASSEMBLE::shape2;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
        }

        then perform action moveP2ToMain : MovePalletToMainBelt {
            in :>> palletNumber = TaskDISASSEMBLE::palletID2;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
        }

        then perform action releaseP2 : ReleasePallet {
            in :>> palletNumber = TaskDISASSEMBLE::palletID2;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
        }

        // --- Phase 2: Place part onto fresh pallet 1 ---

        then perform action routeToRobot2 : SetPalletToDestination {
            in :>> palletNumber = TaskDISASSEMBLE::palletID1;
            in constant :>> destination = ConveyorDestination::bay3_roboticCell;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
            in ref :>> palletAtDestination = TaskDISASSEMBLE::conveyorEquipment.destinationPalletId_3_1;
        }

        then perform action place : PlaceToPallet {
            in :>> posPickOnBuffer = pick.bufferPos;
            in constant :>> posPlaceOnPallet = PalletSlot::pos2;
            in ref :>> equipment = TaskDISASSEMBLE::roboticCellEquipment;
        }

        then perform action setPartOnP1 : SetPartOnPallet {
            in :>> palletNumber = TaskDISASSEMBLE::palletID1;
            in constant :>> position = PalletSlot::pos2;
            in :>> partCode = TaskDISASSEMBLE::shape1;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
        }

        then perform action moveP1ToMain : MovePalletToMainBelt {
            in :>> palletNumber = TaskDISASSEMBLE::palletID1;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
        }

        then perform action releaseP1 : ReleasePallet {
            in :>> palletNumber = TaskDISASSEMBLE::palletID1;
            in ref :>> equipment = TaskDISASSEMBLE::conveyorEquipment;
        }

        then done;
    }

    // ========================================================================
    // Top-level Recipe: DemoLego
    // ========================================================================

    action def DemoLego :> Recipe {
        doc /* DEMO_LEGO recipe: assemble Lego parts from two pallets,
             * inspect quality, then disassemble back to original configuration.
             */

        in ref conveyorEquipment : ConveyorBeltEquipment;
        in ref roboticCellEquipment : RoboticCellEquipment;
        in ref qualityControlEquipment : QualityControlEquipment;


        first start;

        then action opLD : TaskLD {
            in ref :>> conveyorEquipment = DemoLego::conveyorEquipment;
        }

        then action opRBTC : TaskRBTC {
            in :>> palletID1 = opLD.palletID1;
            in :>> palletID2 = opLD.palletID2;
            in ref :>> conveyorEquipment = DemoLego::conveyorEquipment;
            in ref :>> roboticCellEquipment = DemoLego::roboticCellEquipment;
        }

        then action opQC : TaskQC {
            in :>> palletID2 = opLD.palletID2;
            in :>> shape1 = opRBTC.shape1;
            in :>> shape2 = opRBTC.shape2;
            in ref :>> conveyorEquipment = DemoLego::conveyorEquipment;
            in ref :>> qualityControlEquipment = DemoLego::qualityControlEquipment;
        }

        then action opRESRVPALLET : TaskRESRVPALLET {
            in ref :>> conveyorEquipment = DemoLego::conveyorEquipment;
        }

        then action opDISASSEMBLE : TaskDISASSEMBLE {
            in :>> palletID1 = opRESRVPALLET.palletID1;
            in :>> palletID2 = opLD.palletID2;
            in :>> shape1 = opRBTC.shape1;
            in :>> shape2 = opRBTC.shape2;
            in ref :>> conveyorEquipment = DemoLego::conveyorEquipment;
            in ref :>> roboticCellEquipment = DemoLego::roboticCellEquipment;
        }

        then done;
    }
}
