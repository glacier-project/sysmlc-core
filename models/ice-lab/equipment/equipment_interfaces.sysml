package EquipmentInterfaces {
    doc /* OPC-UA machine function interfaces exposed by each equipment in the ICE Laboratory.
         * Each equipment is modeled as a part def. OPC-UA machine functions are modeled as
         * action defs owned by the equipment, with typed parameters.
         * OPC-UA monitored variables are modeled as attributes.
         * OPC-UA node identifiers are attached via @OpcUaMethod / @OpcUaVariable.
         * OPC-UA connection endpoints are attached to concrete equipment usages.
         */

    private import ScalarValues::*;
    private import OpcUaBinding::*;
    private import RecipePrimitives::MachineFunction;
    private import DomainTypes::*;
    private import DomainEnums::RoboticCellState;
    private import ISA95EquipmentHierarchy::ProductionEquipment;

    // ========================================================================
    // WC01 — Functional Testing (SPEA Flying Probe 4050S2)
    // ========================================================================
    part def FuncTestingEquipment :> ProductionEquipment {
        doc /* SPEA board test station */

        // --- OPC-UA Variables ---

        attribute busy : Boolean {
            @OpcUaVariable { nodeId = "ns=2;s=Busy"; }
        }
        attribute currentMission : String {
            @OpcUaVariable { nodeId = "ns=2;s=CurrentMission"; }
        }
        attribute lastResult : String {
            @OpcUaVariable { nodeId = "ns=2;s=LastResult"; }
        }

        // --- OPC-UA Methods ---

        action def BoardIn :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=BoardIn";
                parentNodeId = "ns=2;i=5001";
            }
            out accepted : Boolean;
        }

        action def BoardOut :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=BoardOut";
                parentNodeId = "ns=2;i=5001";
            }
            out accepted : Boolean;
        }

        action def StartTest :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=StartTest";
                parentNodeId = "ns=2;i=5001";
            }
            in serialNumber : String;
            out accepted : Boolean;
        }

        action def DownloadFirmware :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=DownloadFirmware";
                parentNodeId = "ns=2;i=5001";
            }
            in sourceFilename : String;
            in customID : String;
            out destFilename : String;
        }

        action def ShowMessage :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=ShowMessage";
                parentNodeId = "ns=2;i=5001";
            }
            in text : String;
            out accepted : Boolean;
        }

        // --- Perform Actions ---

        perform action boardIn : BoardIn;
        perform action boardOut : BoardOut;
        perform action startTest : StartTest;
        perform action downloadFirmware : DownloadFirmware;
        perform action showMessage : ShowMessage;
    }

    // ========================================================================
    // WC02 — Subtractive Manufacturing (Emco Concept Mill 105)
    // ========================================================================

    part def MillingEquipment :> ProductionEquipment {
        doc /* CNC milling machine. */

        // --- OPC-UA Variables ---

        attribute mesBusy : Boolean {
            @OpcUaVariable { nodeId = "ns=2;s=OPCUA.MES.MESBusy"; }
        }
        attribute mesLastResult : Boolean {
            @OpcUaVariable { nodeId = "ns=2;s=OPCUA.MES.MESLastResult"; }
        }
        attribute currentMission : String {
            @OpcUaVariable { nodeId = "ns=2;s=OPCUA.MES.CurrentMission"; }
        }

        // --- OPC-UA Methods ---

        action def StartMission :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=OPCUA.MES.Methods.StartMission.StartMission";
                parentNodeId = "ns=2;s=OPCUA.MES.Methods.StartMission";
            }
            in missionName : String;
            out accepted : Boolean;
        }

        action def EngraveText :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=OPCUA.MES.Methods.EngraveText.EngraveText";
                parentNodeId = "ns=2;s=OPCUA.MES.Methods.EngraveText";
            }
            in text : String;
            out accepted : Boolean;
        }

        // --- Perform Actions ---

        perform action startMission : StartMission;
        perform action engraveText : EngraveText;
    }

    // ========================================================================
    // WC04 — Assembly / Disassembly (KUKA LBR iiwa 14, ABB YuMi, Siemens PLC)
    // ========================================================================

    port def RoboticCellCmdPort {
        doc /* Command interface: receives OPC-UA method calls. */
        in cmd : MachineFunction;
    }

    port def RoboticCellStatePort {
        doc /* State notification interface: publishes current PLC state. */
        out cellState : RoboticCellState;
    }

    part def RoboticCellEquipment :> ProductionEquipment {
        doc /* Siemens PLC coordinating ABB and KUKA robots. */

        // --- OPC-UA Variables: Cell Control ---

        attribute plcOperationRunning : Boolean {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_ROBOTS\".\"plcOperationRunning\""; }
        }
        attribute plcOperationDone : Boolean {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_ROBOTS\".\"plcOperationDone\""; }
        }
        attribute plcOperationError : Boolean {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_ROBOTS\".\"plcOperationError\""; }
        }
        attribute cellInitialized : Boolean {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_OPCUA\".\"CellControl\".\"cellInitialized\""; }
        }

        // --- OPC-UA Variables: Robot Activity ---

        attribute abbProgramRunning : Boolean {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_ROBOTS\".\"ABB\".\"programRunning\""; }
        }
        attribute kukaProgramRunning : Boolean {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_ROBOTS\".\"Kuka\".\"programRunning\""; }
        }

        // --- OPC-UA Variables: Buffer Positions ---

        attribute abbBufferPosition0 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"ABBPositions\"[0]"; }
        }
        attribute abbBufferPosition1 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"ABBPositions\"[1]"; }
        }
        attribute abbBufferPosition2 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"ABBPositions\"[2]"; }
        }
        attribute abbBufferPosition3 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"ABBPositions\"[3]"; }
        }
        attribute abbBufferPosition4 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"ABBPositions\"[4]"; }
        }
        attribute abbBufferPosition5 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"ABBPositions\"[5]"; }
        }

        attribute abbRightBufferPosition0 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"ABBRightPositions\"[0]"; }
        }
        attribute abbRightBufferPosition1 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"ABBRightPositions\"[1]"; }
        }
        attribute abbRightBufferPosition2 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"ABBRightPositions\"[2]"; }
        }

        attribute kukaBufferPosition0 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"KUKAPositions\"[0]"; }
        }
        attribute kukaBufferPosition1 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"KUKAPositions\"[1]"; }
        }
        attribute kukaBufferPosition2 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"KUKAPositions\"[2]"; }
        }
        attribute kukaBufferPosition3 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"KUKAPositions\"[3]"; }
        }
        attribute kukaBufferPosition4 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"KUKAPositions\"[4]"; }
        }
        attribute kukaBufferPosition5 : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_BUFFER\".\"KUKAPositions\"[5]"; }
        }

        // --- OPC-UA Variables: Statistics ---

        attribute abbTaskCount : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_STATISTICS\".\"ABB_TASK_COUNT\""; }
        }
        attribute kukaTaskCount : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"DB_STATISTICS\".\"KUKA_TASK_COUNT\""; }
        }

        // --- OPC-UA Variables: ABB Mission ---

        attribute abbProgramID : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"ABB_programID\""; }
        }
        attribute abbPickAreaID : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"ABB_pickAreaID\""; }
        }
        attribute abbPickPosX : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"ABB_pickPosX\""; }
        }
        attribute abbPickPosY : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"ABB_pickPosY\""; }
        }
        attribute abbPlaceAreaID : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"ABB_placeAreaID\""; }
        }
        attribute abbPlacePosX : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"ABB_placePosX\""; }
        }
        attribute abbPlacePosY : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"ABB_placePosY\""; }
        }
        attribute abbItemColorID : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"ABB_itemColorID\""; }
        }

        // --- OPC-UA Variables: KUKA Mission ---

        attribute kukaProgramID : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"KUKA_programID\""; }
        }
        attribute kukaPickAreaID : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"KUKA_pickAreaID\""; }
        }
        attribute kukaPickPosX : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"KUKA_pickPosX\""; }
        }
        attribute kukaPickPosY : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"KUKA_pickPosY\""; }
        }
        attribute kukaPlaceAreaID : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"KUKA_placeAreaID\""; }
        }
        attribute kukaPlacePosX : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"KUKA_placePosX\""; }
        }
        attribute kukaPlacePosY : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"KUKA_placePosY\""; }
        }
        attribute kukaAppStart : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"KUKA_appStart\""; }
        }
        attribute kukaAppEnable : Integer {
            @OpcUaVariable { nodeId = "ns=3;s=\"KUKA_appEnable\""; }
        }

        // --- OPC-UA Methods ---

        action def PickFromPallet :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=3;s=\"OPC_UA_PICK_FROM_PALLET_DB\".Method";
                parentNodeId = "ns=3;s=\"OPC_UA_PICK_FROM_PALLET_DB\"";
            }
            in posPick : Integer;
            in itemShape : Integer;
            out result : Boolean;
            out palletPosition : Integer;
            out errorCode : Integer;
        }

        action def PlaceToPallet :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=3;s=\"OPC_UA_PLACE_TO_PALLET_DB\".Method";
                parentNodeId = "ns=3;s=\"OPC_UA_PLACE_TO_PALLET_DB\"";
            }
            in posPickOnBuffer : Integer;
            in posPlaceOnPallet : Integer;
            out result : Boolean;
            out errorCode : Integer;
        }

        action def MoveAndPlace :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=3;s=\"OPC_UA_MOVE_AND_PLACE_DB\".Method";
                parentNodeId = "ns=3;s=\"OPC_UA_MOVE_AND_PLACE_DB\"";
            }
            in posPickOnPallet : Integer;
            in posPlaceOnPallet : Integer;
            in posPickOnBuffer : Integer;
            in posPlaceFromBufferToPallet : Integer;
            out result : Boolean;
            out errorCode : Integer;
        }

        action def MoveOverPallet :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=3;s=\"OPC_UA_MOVE_OVER_PALLET_DB\".Method";
                parentNodeId = "ns=3;s=\"OPC_UA_MOVE_OVER_PALLET_DB\"";
            }
            in posPick : Integer;
            in posPlace : Integer;
            out result : Boolean;
            out errorCode : Integer;
        }

        action def AbbPickBoardFromPallet :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=3;s=\"OPC_UA_ABB_PICK_BOARD_FROM_PALLET_DB\".Method";
                parentNodeId = "ns=3;s=\"OPC_UA_ABB_PICK_BOARD_FROM_PALLET_DB\"";
            }
            out result : Boolean;
            out boardPosition : Integer;
            out errorCode : Integer;
        }

        action def GadgetAssembly :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=3;s=\"OPC_UA_GADGET_ASSEMBLY_DB\".Method";
                parentNodeId = "ns=3;s=\"OPC_UA_GADGET_ASSEMBLY_DB\"";
            }
            in phaseNumber : Integer;
            in boardPosition : Integer;
            out result : Boolean;
            out errorCode : Integer;
        }

        action def SubmitRobotOperation :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=3;s=\"OPC_UA_SUBMIT_ROBOT_OPERATION_DB\".Method";
                parentNodeId = "ns=3;s=\"OPC_UA_SUBMIT_ROBOT_OPERATION_DB\"";
            }
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
        }

        action def ClearBuffer :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=3;s=\"OPC_UA_CLEAR_BUFFER_DB\".Method";
                parentNodeId = "ns=3;s=\"OPC_UA_CLEAR_BUFFER_DB\"";
            }
        }

        // --- Perform Actions ---

        perform action pickFromPallet : PickFromPallet;
        perform action placeToPallet : PlaceToPallet;
        perform action moveAndPlace : MoveAndPlace;
        perform action moveOverPallet : MoveOverPallet;
        perform action abbPickBoardFromPallet : AbbPickBoardFromPallet;
        perform action gadgetAssembly : GadgetAssembly;
        perform action submitRobotOperation : SubmitRobotOperation;
        perform action clearBuffer : ClearBuffer;

        // --- Behavioral Ports ---

        port cmdPort : RoboticCellCmdPort;
        port statePort : RoboticCellStatePort;
    }

    // ========================================================================
    // WC04 — Assembly / Disassembly (Fiam eTensil E8MC4A-900)
    // ========================================================================

    part def ETensilEquipment :> ProductionEquipment {
        doc /* Electric screwdriver */

        // --- OPC-UA Variables ---

        attribute busy : Boolean {
            @OpcUaVariable { nodeId = "ns=2;s=eTensil.MES.busy"; }
        }
        attribute lastOperationResult : Boolean {
            @OpcUaVariable { nodeId = "ns=2;s=eTensil.MES.last_operation_result"; }
        }

        // --- OPC-UA Methods ---

        action def DoSingleScrew :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=eTensil.MES.do_single_screw";
                parentNodeId = "ns=2;s=eTensil.MES";
            }
            out accepted : Boolean;
        }

        action def DoUntight :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=eTensil.MES.do_untight";
                parentNodeId = "ns=2;s=eTensil.MES";
            }
            in timeMs : Real;
            out accepted : Boolean;
        }

        action def LockETensil :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=eTensil.MES.lock_eTensil";
                parentNodeId = "ns=2;s=eTensil.MES";
            }
            in lock : Boolean;
            out isDone : Boolean;
        }

        // --- Perform Actions ---

        perform action doSingleScrew : DoSingleScrew;
        perform action doUntight : DoUntight;
        perform action lockETensil : LockETensil;
    }

    // ========================================================================
    // WC05 — Quality Control (QC-PC Vision System)
    // ========================================================================

    part def QualityControlEquipment :> ProductionEquipment {
        doc /* Vision-based quality control camera for inspection. */

        // --- OPC-UA Variables ---

        attribute busy : Boolean {
            @OpcUaVariable { nodeId = "ns=2;s=Cell5.Status.Busy"; }
        }
        attribute lastResult : Boolean {
            @OpcUaVariable { nodeId = "ns=2;s=Cell5.Status.LastResult"; }
        }
        attribute currentMission : String {
            @OpcUaVariable { nodeId = "ns=2;s=Cell5.Status.CurrentMission"; }
        }

        // --- OPC-UA Methods ---

        action def CheckQualityCovers :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=Cell5.Methods.CheckQualityCovers";
                parentNodeId = "ns=2;s=Cell5.Methods";
            }
            in color : String;
            out result : Boolean;
        }

        action def CheckQualityLego :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=Cell5.Methods.CheckQualityLego";
                parentNodeId = "ns=2;s=Cell5.Methods";
            }
            in shape1 : Integer;
            in shape2 : Integer;
            in shape3 : Integer;
            out result : Boolean;
        }

        // --- Perform Actions ---

        perform action checkQualityCovers : CheckQualityCovers;
        perform action checkQualityLego : CheckQualityLego;
    }

    // ========================================================================
    // WC06 — Automated Vertical Storage (Ferretto Group Vertimag)
    // ========================================================================

    part def WarehouseEquipment :> ProductionEquipment {
        doc /* Automated tray storage. */

        // --- OPC-UA Variables ---

        attribute trayInBay : Integer {
            @OpcUaVariable { nodeId = "ns=2;s=Warehouse.Status.trayInBay"; }
        }
        attribute bayBusy : Boolean {
            @OpcUaVariable { nodeId = "ns=2;s=Warehouse.Status.bayBusy"; }
        }
        attribute bayReadyForPickPlace : Boolean {
            @OpcUaVariable { nodeId = "ns=2;s=Warehouse.Status.bayReadyForPickPlace"; }
        }

        // --- OPC-UA Methods ---

        action def ExtractTray :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=Warehouse.SocketLink.extractTray";
                parentNodeId = "ns=2;s=Warehouse.SocketLink";
            }
            in num : Integer;
            out code : Integer;
        }

        action def SendBackTray :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=Warehouse.SocketLink.sendBack";
                parentNodeId = "ns=2;s=Warehouse.SocketLink";
            }
            out code : Integer;
        }

        action def ShowMessage :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=Warehouse.showMessage";
                parentNodeId = "ns=2;s=Warehouse";
            }
            in msg : String;
        }

        // --- Perform Actions ---

        perform action extractTray : ExtractTray;
        perform action sendBackTray : SendBackTray;
        perform action showMessage : ShowMessage;
    }

    // ========================================================================
    // WC07 — Inter-WorkCell Transport (Bosch Rexroth TS 2plus)
    // ========================================================================

    part def ConveyorBeltEquipment :> ProductionEquipment {
        doc /* Siemens PLC controlling the closed-loop conveyor belt.*/

        // --- OPC-UA Variables ---

        attribute destinationPalletId_1_1 : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Destinations/destination_palletid_1_1"; }
        }
        attribute destinationPalletId_2_3 : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Destinations/destination_palletid_2_3"; }
        }
        attribute destinationPalletId_3_1 : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Destinations/destination_palletid_3_1"; }
        }
        attribute destinationPalletId_4_2 : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Destinations/destination_palletid_4_2"; }
        }
        attribute destinationPalletId_4_3 : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Destinations/destination_palletid_4_3"; }
        }
        attribute destinationPalletId_5 : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Destinations/destination_palletid_5"; }
        }

        attribute bay2Light : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/BayLights/bay2Light"; }
        }
        attribute bay3Light : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/BayLights/bay3Light"; }
        }
        attribute bay4Light : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/BayLights/bay4Light"; }
        }
        attribute bay5Light : Integer {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/BayLights/bay5Light"; }
        }

        attribute ackBay2 : Boolean {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Buttons/ackBay2"; }
        }
        attribute ackBay3 : Boolean {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Buttons/ackBay3"; }
        }
        attribute ackBay4 : Boolean {
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Buttons/ackBay4"; }
        }
        attribute ackLoadUnloadZone : Boolean {
            doc /* Operator acknowledgment button for Load/Unload zone (bay 5). */
            @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorDataExchange/Buttons/ackLoadUnloadZone"; }
        }

        // --- Pallet Status ---

        attribute pallet1 : PalletStatus {
            attribute :>> palletNumber = 1;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet1/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet1/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet1/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet1/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet1/type"; }
            }
        }

        attribute pallet2 : PalletStatus {
            attribute :>> palletNumber = 2;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet2/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet2/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet2/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet2/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet2/type"; }
            }
        }

        attribute pallet3 : PalletStatus {
            attribute :>> palletNumber = 3;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet3/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet3/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet3/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet3/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet3/type"; }
            }
        }

        attribute pallet4 : PalletStatus {
            attribute :>> palletNumber = 4;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet4/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet4/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet4/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet4/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet4/type"; }
            }
        }

        attribute pallet5 : PalletStatus {
            attribute :>> palletNumber = 5;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet5/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet5/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet5/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet5/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet5/type"; }
            }
        }

        attribute pallet6 : PalletStatus {
            attribute :>> palletNumber = 6;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet6/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet6/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet6/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet6/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet6/type"; }
            }
        }

        attribute pallet7 : PalletStatus {
            attribute :>> palletNumber = 7;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet7/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet7/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet7/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet7/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet7/type"; }
            }
        }

        attribute pallet8 : PalletStatus {
            attribute :>> palletNumber = 8;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet8/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet8/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet8/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet8/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet8/type"; }
            }
        }

        attribute pallet9 : PalletStatus {
            attribute :>> palletNumber = 9;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet9/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet9/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet9/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet9/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet9/type"; }
            }
        }

        attribute pallet10 : PalletStatus {
            attribute :>> palletNumber = 10;
            attribute :>> reserved {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet10/reserved"; }
            }
            attribute :>> contentPosition1 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet10/contentPosition1"; }
            }
            attribute :>> contentPosition2 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet10/contentPosition2"; }
            }
            attribute :>> contentPosition3 {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet10/contentPosition3"; }
            }
            attribute :>> palletType {
                @OpcUaVariable { nodeId = "Objects/ConveyorHMI/ConveyorObjects/Pallets/Pallet10/type"; }
            }
        }

        // Collected sequence for iteration
        attribute pallets : PalletStatus[10] = (pallet1, pallet2, pallet3, pallet4, pallet5, pallet6, pallet7, pallet8, pallet9, pallet10);

        // --- OPC-UA Methods ---

        action def SetPalletDestination :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=25ddc5dc-e471-ab51-b57d-f0845f33f662";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in palletNumber : Integer;
            in destination : Integer;
            out result : Boolean;
        }

        action def SetPalletDestinationWithReservation :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=e1326cd9-e7c9-5a34-7c52-8a4899f49e3d";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in palletNumber : Integer;
            in destination : Integer;
            in reservationId : Integer;
            out result : Boolean;
        }

        action def CallFreePalletTo :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=bfa3e392-c6a3-aa27-c419-583fa3dc323c";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in destination : Integer;
            out result : Boolean;
            out palletNumber : Integer;
        }

        action def CallFreePalletToWithReservation :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=ec775657-4f5f-35cb-c5fe-035d1b0cd79b";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in destination : Integer;
            in reservationId : Integer;
            out result : Boolean;
            out palletNumber : Integer;
        }

        action def CallFreePalletOfTypeTo :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=96dca0ef-7a3c-13fb-5d6c-f248569fe0c5";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in destination : Integer;
            in palletType : Integer;
            out result : Boolean;
            out palletNumber : Integer;
        }

        action def CallFreePalletOfTypeToWithReservation :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=1704f4b3-8242-a404-17f1-16bd6b0e9f2c";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in destination : Integer;
            in palletType : Integer;
            in reservationId : Integer;
            out result : Boolean;
            out palletNumber : Integer;
        }

        action def ReservePallet :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=cddee93f-3db9-ad50-39f3-c19f181ca6a1";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in palletNumber : Integer;
            in reservationId : Integer;
            out result : Boolean;
        }

        action def ReleasePallet :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=334afc82-90f9-150c-810f-790d0c5ecbe7";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in palletNumber : Integer;
            out result : Boolean;
        }

        action def SetPartOnPallet :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=37ed45b6-29c4-6c4d-edb0-88b45decbdbf";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in palletNumber : Integer;
            in position : Integer;
            in partCode : Integer;
            out result : Boolean;
        }

        action def ClearPartOnPallet :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=7;g=07d2ba87-a6a1-5ba2-47e4-df8197ccfdc0";
                parentNodeId = "ns=7;g=0c3140a2-b72c-c4a8-cc1a-f6787c6f8ae5";
            }
            in palletNumber : Integer;
            in position : Integer;
            out result : Boolean;
        }

        // --- Perform Actions ---

        perform action setPalletDestination : SetPalletDestination;
        perform action setPalletDestinationWithReservation : SetPalletDestinationWithReservation;
        perform action callFreePalletTo : CallFreePalletTo;
        perform action callFreePalletToWithReservation : CallFreePalletToWithReservation;
        perform action callFreePalletOfTypeTo : CallFreePalletOfTypeTo;
        perform action callFreePalletOfTypeToWithReservation : CallFreePalletOfTypeToWithReservation;
        perform action reservePallet : ReservePallet;
        perform action releasePallet : ReleasePallet;
        perform action setPartOnPallet : SetPartOnPallet;
        perform action clearPartOnPallet : ClearPartOnPallet;
    }

    // ========================================================================
    // WC07 — Inter-WorkCell Transport (Robotnik RB-Kairos5 A/B)
    // ========================================================================

    part def RbKairosEquipment :> ProductionEquipment {
        doc /* Robotnik RB Kairos autonomous mobile robot with UR5 arm.*/

        // --- OPC-UA Variables ---

        attribute controlBusy : Boolean {
            @OpcUaVariable { nodeId = "Objects/RBKairos/Mission_Methods/Control_Busy"; }
        }
        attribute lastMissionResult : Boolean {
            @OpcUaVariable { nodeId = "Objects/RBKairos/Mission_Methods/Last_Mission_Result"; }
        }
        attribute ongoingMissionName : String {
            @OpcUaVariable { nodeId = "Objects/RBKairos/Mission_Methods/Ongoing_Mission_Name"; }
        }

        // --- OPC-UA Methods ---

        action def StartMission :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=RBKairos.Mission_Methods.start_mission";
                parentNodeId = "ns=2;s=RBKairos.Mission_Methods";
            }
            in name : String;
            out accepted : Boolean;
        }

        action def PreemptRunningMission :> MachineFunction {
            @OpcUaMethod {
                nodeId = "ns=2;s=RBKairos.Mission_Methods.preempt_running_mission";
                parentNodeId = "ns=2;s=RBKairos.Mission_Methods";
            }
            out accepted : Boolean;
        }

        // --- Perform Actions ---

        perform action startMission : StartMission;
        perform action preemptRunningMission : PreemptRunningMission;
    }
}
