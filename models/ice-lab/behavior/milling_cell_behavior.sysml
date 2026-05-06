package MillingCellBehavior {

    private import ScalarValues::*;
    private import EquipmentInterfaces::MillingEquipment;
    private import ISQ::DurationValue;
    private import SI::s;

    enum def MillingControllerState :> String {
        enum idle = "idle";
        enum acceptingCommand = "acceptingCommand";
        enum preparingLoad = "preparingLoad";
        enum loadingMachine = "loadingMachine";
        enum engraving = "engraving";
        enum preparingUnload = "preparingUnload";
        enum unloadingMachine = "unloadingMachine";
        enum completing = "completing";
        enum completed = "completed";
    }

    enum def ManipulatorState :> String {
        enum idle = "idle";
        enum movingToPallet = "movingToPallet";
        enum pickingFromPallet = "pickingFromPallet";
        enum movingToMachine = "movingToMachine";
        enum placingInMachine = "placingInMachine";
        enum pickingFromMachine = "pickingFromMachine";
        enum movingToPalletForReturn = "movingToPalletForReturn";
        enum placingOnPallet = "placingOnPallet";
    }

    enum def MillingMachineState :> String {
        enum idle = "idle";
        enum preparingForLoad = "preparingForLoad";
        enum loaded = "loaded";
        enum processing = "processing";
        enum preparingForUnload = "preparingForUnload";
        enum returningIdle = "returningIdle";
    }

    enum def DoorState :> String {
        enum closed = "closed";
        enum opening = "opening";
        enum open = "open";
        enum closing = "closing";
    }

    enum def ViseState :> String {
        enum open = "open";
        enum closing = "closing";
        enum clamped = "clamped";
        enum opening = "opening";
    }

    enum def SpindleState :> String {
        enum stopped = "stopped";
        enum running = "running";
    }

    enum def GadgetLocation :> String {
        enum onPallet = "onPallet";
        enum heldByManipulator = "heldByManipulator";
        enum inVise = "inVise";
    }

    state def MillingCellEngravingStates {
        in ref equipment : MillingEquipment;

        in attribute doorMotionDuration : DurationValue default 1 [s];
        in attribute pickDuration : DurationValue default 2 [s];
        in attribute placeDuration : DurationValue default 2 [s];
        in attribute clampDuration : DurationValue default 1 [s];
        in attribute engravingDuration : DurationValue default 4 [s];
        in attribute unloadPrepareDuration : DurationValue default 1 [s];
        in attribute completionPulseDuration : DurationValue default 1 [s];

        inout attribute controllerState : MillingControllerState;
        inout attribute currentText : String;

        inout attribute manipulatorState : ManipulatorState;

        inout attribute machineState : MillingMachineState;
        inout attribute doorState : DoorState;
        inout attribute viseState : ViseState;
        inout attribute spindleState : SpindleState;

        inout attribute gadgetLocation : GadgetLocation;
        inout attribute gadgetEngraved : Boolean;
        inout attribute engravedText : String;
        inout attribute palletPresent : Boolean;

        entry;
            then idle;

        state idle {
            entry action {
                assign controllerState := MillingControllerState::idle;
                assign currentText := "";
                assign manipulatorState := ManipulatorState::idle;
                assign machineState := MillingMachineState::idle;
                assign doorState := DoorState::closed;
                assign viseState := ViseState::open;
                assign spindleState := SpindleState::stopped;
                assign equipment.mesBusy := false;
                assign equipment.mesLastResult := false;
            }
        }

        transition acceptEngraveText
            first idle
            accept engraveCmd : MillingEquipment::EngraveText
            if palletPresent == true and
               gadgetLocation == GadgetLocation::onPallet and
               manipulatorState == ManipulatorState::idle and
               machineState == MillingMachineState::idle and
               doorState == DoorState::closed and
               viseState == ViseState::open and
               spindleState == SpindleState::stopped
            do action {
                assign controllerState :=
                    MillingControllerState::acceptingCommand;
                assign currentText := engraveCmd.text;
                assign engraveCmd.accepted := true;
                assign equipment.mesBusy := true;
                assign equipment.currentMission := "engraveText";
            }
            then acceptingCommand;

        state acceptingCommand;

        transition startPrepareLoad
            first acceptingCommand
            do action {
                assign controllerState := MillingControllerState::preparingLoad;
                assign machineState := MillingMachineState::preparingForLoad;
                assign doorState := DoorState::opening;
            }
            then preparingLoad;

        state preparingLoad;

        transition machineReadyForLoad
            first preparingLoad
            accept after doorMotionDuration
            do action {
                assign doorState := DoorState::open;
                assign controllerState :=
                    MillingControllerState::loadingMachine;
                assign manipulatorState := ManipulatorState::movingToPallet;
            }
            then loadingMachine;

        state loadingMachine;

        transition startPickFromPallet
            first loadingMachine
            accept after pickDuration
            if manipulatorState == ManipulatorState::movingToPallet
            do action {
                assign manipulatorState :=
                    ManipulatorState::pickingFromPallet;
            }
            then loadingMachine;

        transition gadgetPickedFromPallet
            first loadingMachine
            accept after pickDuration
            if manipulatorState == ManipulatorState::pickingFromPallet
            do action {
                assign gadgetLocation := GadgetLocation::heldByManipulator;
                assign manipulatorState := ManipulatorState::movingToMachine;
            }
            then loadingMachine;

        transition startPlaceInMachine
            first loadingMachine
            accept after placeDuration
            if manipulatorState == ManipulatorState::movingToMachine
            do action {
                assign manipulatorState :=
                    ManipulatorState::placingInMachine;
            }
            then loadingMachine;

        transition gadgetPlacedInVise
            first loadingMachine
            accept after placeDuration
            if manipulatorState == ManipulatorState::placingInMachine
            do action {
                assign gadgetLocation := GadgetLocation::inVise;
                assign manipulatorState := ManipulatorState::idle;
                assign machineState := MillingMachineState::loaded;
                assign viseState := ViseState::closing;
                assign doorState := DoorState::closing;
                assign controllerState := MillingControllerState::engraving;
            }
            then engraving;

        state engraving;

        transition startEngraving
            first engraving
            accept after clampDuration
            if machineState == MillingMachineState::loaded and
               doorState == DoorState::closing and
               viseState == ViseState::closing and
               spindleState == SpindleState::stopped
            do action {
                assign viseState := ViseState::clamped;
                assign doorState := DoorState::closed;
                assign machineState := MillingMachineState::processing;
                assign spindleState := SpindleState::running;
            }
            then engraving;

        transition engravingCompleted
            first engraving
            accept after engravingDuration
            if machineState == MillingMachineState::processing and
               spindleState == SpindleState::running
            do action {
                assign spindleState := SpindleState::stopped;
                assign gadgetEngraved := true;
                assign engravedText := currentText;
                assign controllerState :=
                    MillingControllerState::preparingUnload;
                assign machineState :=
                    MillingMachineState::preparingForUnload;
                assign doorState := DoorState::opening;
                assign viseState := ViseState::opening;
            }
            then preparingUnload;

        state preparingUnload;

        transition machineReadyForUnload
            first preparingUnload
            accept after unloadPrepareDuration
            do action {
                assign doorState := DoorState::open;
                assign viseState := ViseState::open;
                assign controllerState :=
                    MillingControllerState::unloadingMachine;
                assign manipulatorState :=
                    ManipulatorState::pickingFromMachine;
            }
            then unloadingMachine;

        state unloadingMachine;

        transition gadgetPickedFromMachine
            first unloadingMachine
            accept after pickDuration
            if manipulatorState == ManipulatorState::pickingFromMachine
            do action {
                assign gadgetLocation := GadgetLocation::heldByManipulator;
                assign manipulatorState :=
                    ManipulatorState::movingToPalletForReturn;
            }
            then unloadingMachine;

        transition startPlaceOnPallet
            first unloadingMachine
            accept after placeDuration
            if manipulatorState == ManipulatorState::movingToPalletForReturn
            do action {
                assign manipulatorState := ManipulatorState::placingOnPallet;
            }
            then unloadingMachine;

        transition gadgetPlacedOnPallet
            first unloadingMachine
            accept after placeDuration
            if manipulatorState == ManipulatorState::placingOnPallet
            do action {
                assign gadgetLocation := GadgetLocation::onPallet;
                assign manipulatorState := ManipulatorState::idle;
                assign controllerState := MillingControllerState::completing;
                assign machineState := MillingMachineState::returningIdle;
                assign doorState := DoorState::closing;
            }
            then completing;

        state completing;

        transition machineReturnedIdle
            first completing
            accept after doorMotionDuration
            do action {
                assign doorState := DoorState::closed;
                assign machineState := MillingMachineState::idle;
                assign controllerState := MillingControllerState::completed;
                assign equipment.mesBusy := false;
                assign equipment.mesLastResult := true;
                assign equipment.currentMission := "";
            }
            then completed;

        state completed;

        transition clearCompletedPulse
            first completed
            accept after completionPulseDuration
            then idle;
    }
}
