package RoboticCellStates {
    doc /* PLC state machine for the robotic assembly cell (WC04).
         * Models the Siemens S7-1200 PLC lifecycle that orchestrates
         * the ABB YuMi and KUKA LBR iiwa robots.
         *
         * Exhibited on Cell4_RoboticAssembly in PlantTopology.
         */

    private import ScalarValues::*;
    private import EquipmentInterfaces::RoboticCellEquipment;
    private import EquipmentInterfaces::RoboticCellCmdPort;
    private import EquipmentInterfaces::RoboticCellStatePort;
    private import DomainEnums::RoboticCellState;
    private import RecipePrimitives::MachineFunction;

    state def RoboticCellStates {
        doc /* PLC lifecycle state machine for the robotic cell.
             * Guard expressions reference OPC-UA monitored variables
             * on the equipment instance. State changes are published
             * via the equipment's statePort.
             */

        in ref equipment : RoboticCellEquipment;

        entry; then uninitialized;

        state uninitialized {
            entry send RoboticCellState::UNINITIALIZED via equipment.statePort;
        }
        transition initComplete
            first uninitialized
            if equipment.cellInitialized == true
            then idle;

        state idle {
            entry send RoboticCellState::IDLE via equipment.statePort;
        }
        transition onPickFromPallet
            first idle
            accept RoboticCellEquipment::PickFromPallet via equipment.cmdPort
            then running;
        transition onPlaceToPallet
            first idle
            accept RoboticCellEquipment::PlaceToPallet via equipment.cmdPort
            then running;
        transition onMoveAndPlace
            first idle
            accept RoboticCellEquipment::MoveAndPlace via equipment.cmdPort
            then running;
        transition onMoveOverPallet
            first idle
            accept RoboticCellEquipment::MoveOverPallet via equipment.cmdPort
            then running;
        transition onAbbPickBoardFromPallet
            first idle
            accept RoboticCellEquipment::AbbPickBoardFromPallet via equipment.cmdPort
            then running;
        transition onGadgetAssembly
            first idle
            accept RoboticCellEquipment::GadgetAssembly via equipment.cmdPort
            then running;
        transition onSubmitRobotOperation
            first idle
            accept RoboticCellEquipment::SubmitRobotOperation via equipment.cmdPort
            then running;
        transition onClearBuffer
            first idle
            accept RoboticCellEquipment::ClearBuffer via equipment.cmdPort
            then running;

        state running {
            entry send RoboticCellState::RUNNING via equipment.statePort;
        }
        transition operationDone
            first running
            if equipment.plcOperationDone == true
            then completed;
        transition operationError
            first running
            if equipment.plcOperationError == true
            then error;

        state completed {
            entry send RoboticCellState::DONE via equipment.statePort;
        }
        transition completedToIdle
            first completed
            then idle;

        state error {
            entry send RoboticCellState::ERROR via equipment.statePort;
        }
        transition errorToIdle
            first error
            then idle;
    }
}
